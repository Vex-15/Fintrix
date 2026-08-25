"""
Webhooks API — Razorpay webhook receiver with signature verification.
"""

import json
from fastapi import APIRouter, Request, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.config import settings
from app.models import Event, Merchant
from app.services.razorpay import verify_webhook_signature
from app.utils.audit import log_audit
from app.routers.events import broadcast_sse, _process_event
from app.schemas import EventIn

from sqlalchemy import select
from datetime import datetime

router = APIRouter()


@router.post("/razorpay")
async def razorpay_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Receive Razorpay webhook events with HMAC-SHA256 signature verification.

    Razorpay sends:
    - X-Razorpay-Signature header with HMAC
    - JSON body with event_type and payload
    """
    body = await request.body()
    signature = request.headers.get("X-Razorpay-Signature", "")

    # Determine which secret to use (per-merchant or global)
    webhook_secret = settings.razorpay_webhook_secret

    # Try to find merchant-specific secret from payload
    try:
        payload = json.loads(body)
        account_id = payload.get("account_id")
        if account_id:
            result = await db.execute(
                select(Merchant).where(Merchant.razorpay_account_id == account_id)
            )
            merchant = result.scalar_one_or_none()
            if merchant and merchant.webhook_secret:
                webhook_secret = merchant.webhook_secret
    except (json.JSONDecodeError, Exception):
        payload = {}

    # Verify signature (skip if no secret configured — dev mode)
    if webhook_secret and signature:
        if not verify_webhook_signature(body, signature, webhook_secret):
            await log_audit(
                db, "webhook", "razorpay",
                action="signature_verification_failed",
                actor="system",
                new_state={"signature": signature[:20] + "..."},
            )
            raise HTTPException(status_code=400, detail="Invalid webhook signature")
    elif webhook_secret and not signature:
        raise HTTPException(status_code=400, detail="Missing X-Razorpay-Signature header")

    # Parse the Razorpay event
    event_type = payload.get("event", "unknown")
    entity = payload.get("payload", {})

    # Map Razorpay event types to internal event types
    event_type_map = {
        "payment.captured": "txn.captured",
        "payment.authorized": "txn.captured",
        "payment.failed": "transaction.failed",
        "refund.created": "refund.created",
        "settlement.processed": "settlement.processed",
        "order.paid": "order.paid",
    }

    internal_type = event_type_map.get(event_type, event_type)

    # Extract entity data based on event type
    entity_data = {}
    if "payment" in entity:
        p = entity["payment"].get("entity", {})
        entity_data = {
            "id": p.get("id"),
            "type": "payment",
            "amount": p.get("amount", 0),
            "currency": p.get("currency", "INR"),
            "status": p.get("status"),
            "fee": p.get("fee", 0),
            "tax": p.get("tax", 0),
            "method": p.get("method"),
            "order_id": p.get("order_id"),
            "description": p.get("description"),
        }
    elif "settlement" in entity:
        s = entity["settlement"].get("entity", {})
        entity_data = {
            "id": s.get("id"),
            "amount": s.get("amount", 0),
            "fees": s.get("fees", 0),
            "tax": s.get("tax", 0),
            "utr": s.get("utr"),
        }
    elif "refund" in entity:
        r = entity["refund"].get("entity", {})
        entity_data = {
            "id": r.get("id"),
            "type": "refund",
            "amount": r.get("amount", 0),
            "payment_id": r.get("payment_id"),
        }

    # Store the event
    event = Event(
        event_type=internal_type,
        payload=entity_data,
        status="pending",
    )
    db.add(event)
    await db.flush()

    await log_audit(
        db, "webhook", str(event.id),
        action="razorpay_webhook_received",
        actor="razorpay",
        new_state={
            "razorpay_event": event_type,
            "internal_type": internal_type,
            "entity_id": entity_data.get("id"),
        },
    )

    # Process the event through the existing pipeline
    try:
        event_in = EventIn(event_type=internal_type, payload=entity_data)
        await _process_event(db, event, event_in)
        event.status = "processed"
        event.processed_at = datetime.utcnow()
    except Exception as e:
        event.attempts += 1
        if event.attempts >= 3:
            event.status = "failed"
        await log_audit(
            db, "webhook", str(event.id),
            action="webhook_processing_error",
            actor="system",
            new_state={"error": str(e)},
        )

    await db.flush()

    broadcast_sse("webhook.received", {
        "event_id": event.id,
        "razorpay_event": event_type,
        "internal_type": internal_type,
    })

    return {"status": "ok", "event_id": event.id}


@router.post("/razorpay/test")
async def test_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Test webhook endpoint — accepts events without signature verification.
    Only for development/testing.
    """
    body = await request.body()
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    event = Event(
        event_type=payload.get("event_type", "test"),
        payload=payload.get("payload", payload),
        status="processed",
        processed_at=datetime.utcnow(),
    )
    db.add(event)
    await db.flush()

    return {"status": "ok", "event_id": event.id, "note": "Test mode — no signature verification"}
