"""
Razorpay integration service — OAuth 2.0, webhook verification, payment sync.
"""

import hashlib
import hmac
import time
from datetime import datetime, timezone
from typing import Optional

import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.config import settings
from app.models import Transaction, Settlement, Merchant
from app.utils.audit import log_audit


# ---------------------------------------------------------------------------
# Webhook Signature Verification
# ---------------------------------------------------------------------------

def verify_webhook_signature(body: bytes, signature: str, secret: str) -> bool:
    """
    Verify Razorpay webhook signature using HMAC-SHA256.

    Razorpay sends the signature in the `X-Razorpay-Signature` header.
    The expected signature is HMAC-SHA256(webhook_secret, request_body).
    """
    if not secret or not signature:
        return False

    expected = hmac.new(
        secret.encode("utf-8"),
        body,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(expected, signature)


# ---------------------------------------------------------------------------
# OAuth 2.0 Flow
# ---------------------------------------------------------------------------

RAZORPAY_AUTH_URL = "https://auth.razorpay.com/authorize"
RAZORPAY_TOKEN_URL = "https://auth.razorpay.com/token"


def get_oauth_authorize_url(redirect_uri: str, state: str) -> str:
    """Generate the Razorpay OAuth authorization URL."""
    params = {
        "response_type": "code",
        "client_id": settings.razorpay_key_id,
        "redirect_uri": redirect_uri,
        "scope": "read_write",
        "state": state,
    }
    query = "&".join(f"{k}={v}" for k, v in params.items())
    return f"{RAZORPAY_AUTH_URL}?{query}"


async def exchange_oauth_code(code: str, redirect_uri: str) -> dict:
    """Exchange an OAuth authorization code for access + refresh tokens."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            RAZORPAY_TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "client_id": settings.razorpay_key_id,
                "client_secret": settings.razorpay_key_secret,
            },
        )
        response.raise_for_status()
        return response.json()


async def refresh_oauth_token(refresh_token: str) -> dict:
    """Refresh an expired OAuth access token."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            RAZORPAY_TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": settings.razorpay_key_id,
                "client_secret": settings.razorpay_key_secret,
            },
        )
        response.raise_for_status()
        return response.json()


# ---------------------------------------------------------------------------
# Payment / Settlement Sync
# ---------------------------------------------------------------------------

RAZORPAY_API_BASE = "https://api.razorpay.com/v1"


async def _get_razorpay_client(merchant: Optional[Merchant] = None) -> httpx.AsyncClient:
    """Get an authenticated httpx client for Razorpay API calls."""
    if merchant and merchant.oauth_access_token:
        headers = {"Authorization": f"Bearer {merchant.oauth_access_token}"}
    elif settings.razorpay_key_id and settings.razorpay_key_secret:
        # Basic auth fallback
        import base64
        creds = base64.b64encode(
            f"{settings.razorpay_key_id}:{settings.razorpay_key_secret}".encode()
        ).decode()
        headers = {"Authorization": f"Basic {creds}"}
    else:
        raise ConnectionError("No Razorpay credentials configured")

    return httpx.AsyncClient(
        base_url=RAZORPAY_API_BASE,
        headers=headers,
        timeout=30.0,
    )


async def sync_payments(
    db: AsyncSession,
    merchant_id: Optional[str] = None,
    from_timestamp: Optional[int] = None,
    count: int = 100,
) -> dict:
    """
    Fetch recent payments from Razorpay and upsert into the database.
    Returns sync stats.
    """
    try:
        if not settings.razorpay_live_demo:
            return {"error": "Razorpay integration is disabled in demo mode", "fetched": 0, "synced": 0}
            
        merchant = None
        if merchant_id:
            result = await db.execute(select(Merchant).where(Merchant.id == merchant_id))
            merchant = result.scalar_one_or_none()

        client = await _get_razorpay_client(merchant)

        params = {"count": count}
        if from_timestamp:
            params["from"] = from_timestamp

        async with client:
            response = await client.get("/payments", params=params)
            response.raise_for_status()
            data = response.json()

        payments = data.get("items", [])
        synced = 0

        for payment in payments:
            txn_data = {
                "id": payment["id"],
                "type": "payment",
                "order_id": payment.get("order_id"),
                "amount": payment["amount"],
                "currency": payment.get("currency", "INR"),
                "status": payment["status"],
                "fee": payment.get("fee", 0),
                "tax": payment.get("tax", 0),
                "method": payment.get("method"),
                "description": payment.get("description"),
                "notes": payment.get("notes", {}),
                "captured_at": datetime.fromtimestamp(payment["captured_at"], tz=timezone.utc) if payment.get("captured_at") else None,
                "created_at": datetime.fromtimestamp(payment["created_at"], tz=timezone.utc) if payment.get("created_at") else None,
                "source": "razorpay_sync",
                "merchant_id": merchant_id,
            }

            stmt = insert(Transaction).values(txn_data).on_conflict_do_nothing(index_elements=["id"])
            result = await db.execute(stmt)
            if result.rowcount:
                synced += 1

        await log_audit(
            db, "razorpay_sync", "payments",
            action="payments_synced",
            actor="system",
            new_state={"fetched": len(payments), "synced": synced},
        )

        return {"fetched": len(payments), "synced": synced}

    except ConnectionError:
        return {"error": "No Razorpay credentials configured", "fetched": 0, "synced": 0}
    except Exception as e:
        return {"error": str(e), "fetched": 0, "synced": 0}


async def sync_settlements(
    db: AsyncSession,
    merchant_id: Optional[str] = None,
    from_timestamp: Optional[int] = None,
    count: int = 100,
) -> dict:
    """
    Fetch recent settlements from Razorpay and upsert into the database.
    """
    try:
        if not settings.razorpay_live_demo:
            return {"error": "Razorpay integration is disabled in demo mode", "fetched": 0, "synced": 0}
            
        merchant = None
        if merchant_id:
            result = await db.execute(select(Merchant).where(Merchant.id == merchant_id))
            merchant = result.scalar_one_or_none()

        client = await _get_razorpay_client(merchant)

        params = {"count": count}
        if from_timestamp:
            params["from"] = from_timestamp

        async with client:
            response = await client.get("/settlements", params=params)
            response.raise_for_status()
            data = response.json()

        settlements = data.get("items", [])
        synced = 0

        for setl in settlements:
            setl_data = {
                "id": setl["id"],
                "amount": setl["amount"],
                "fees": setl.get("fees", 0),
                "tax": setl.get("tax", 0),
                "utr": setl.get("utr"),
                "status": setl["status"],
                "created_at": datetime.fromtimestamp(setl["created_at"], tz=timezone.utc) if setl.get("created_at") else None,
                "merchant_id": merchant_id,
            }

            stmt = insert(Settlement).values(setl_data).on_conflict_do_nothing(index_elements=["id"])
            result = await db.execute(stmt)
            if result.rowcount:
                synced += 1

        await log_audit(
            db, "razorpay_sync", "settlements",
            action="settlements_synced",
            actor="system",
            new_state={"fetched": len(settlements), "synced": synced},
        )

        return {"fetched": len(settlements), "synced": synced}

    except ConnectionError:
        return {"error": "No Razorpay credentials configured", "fetched": 0, "synced": 0}
    except Exception as e:
        return {"error": str(e), "fetched": 0, "synced": 0}
