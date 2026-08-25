"""
Events API — real-time event ingestion, webhook handlers, and SSE stream.

Enhanced with:
  - Dedicated handlers for txn.captured, settlement.processed, bank_stmt.uploaded
  - Event-driven targeted reconciliation
  - Richer SSE broadcast data
"""

import asyncio
import json
from datetime import datetime
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, Request, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from sqlalchemy.orm.attributes import flag_modified
from sse_starlette.sse import EventSourceResponse

from app.database import get_db, async_session
from app.models import Transaction, Settlement, BankStatement, Exception_, ReconciliationRun, Event
from app.schemas import EventIn, EventOut
from app.utils.audit import log_audit

router = APIRouter()

# In-memory event bus for SSE (simple asyncio.Queue per connection)
_sse_subscribers: list[asyncio.Queue] = []
_debounce_task: asyncio.Task | None = None


def broadcast_sse(event_type: str, data: dict):
    """Push an SSE event to all connected clients."""
    message = {"event": event_type, "data": json.dumps(data, default=str)}
    for queue in _sse_subscribers:
        try:
            queue.put_nowait(message)
        except asyncio.QueueFull:
            pass  # drop events for slow clients


@router.post("/", response_model=EventOut)
async def ingest_event(
    body: EventIn,
    db: AsyncSession = Depends(get_db),
):
    """Receive a real-time financial event (webhook-style)."""
    event = Event(
        event_type=body.event_type,
        payload=body.payload,
        status="pending",
    )
    db.add(event)
    await db.flush()

    await log_audit(
        db, "event", str(event.id),
        action="event_received",
        actor="system",
        new_state={"event_type": body.event_type},
    )

    # Broadcast to SSE subscribers
    broadcast_sse("event.received", {
        "event_id": event.id,
        "event_type": body.event_type,
    })

    # Process the event based on type
    try:
        await _process_event(db, event, body)
        event.status = "processed"
        event.processed_at = datetime.utcnow()
    except Exception as e:
        event.attempts += 1
        if event.attempts >= 3:
            event.status = "failed"
        # Log but don't crash
        await log_audit(
            db, "event", str(event.id),
            action="event_processing_error",
            actor="system",
            new_state={"error": str(e), "attempts": event.attempts},
        )

    # Trigger debounced pipeline
    _trigger_debounced_pipeline()

    await db.flush()
    return event


async def _process_event(db: AsyncSession, event: Event, body: EventIn):
    """Route event to the appropriate handler based on event_type."""
    handlers = {
        "txn.captured": _handle_txn_captured,
        "transaction.created": _handle_txn_captured,
        "settlement.processed": _handle_settlement_processed,
        "bank_stmt.uploaded": _handle_bank_stmt_uploaded,
        "exception.detected": _handle_exception_detected,
    }

    handler = handlers.get(body.event_type)
    if handler:
        await handler(db, body.payload, event.id)
        broadcast_sse("event.processed", {
            "event_id": event.id,
            "event_type": body.event_type,
            "status": "processed",
        })

def _trigger_debounced_pipeline():
    global _debounce_task
    if _debounce_task and not _debounce_task.done():
        _debounce_task.cancel()
    _debounce_task = asyncio.create_task(_debounced_pipeline_task())

async def _debounced_pipeline_task():
    try:
        await asyncio.sleep(4.0)  # 4 second debounce
        from app.database import async_session
        from app.services.reconciliation_engine import run_reconciliation
        from app.services.ai_investigator import investigate_all_exceptions
        
        async with async_session() as db:
            broadcast_sse("pipeline.step", {"step": "reconciliation", "status": "started"})
            run = await run_reconciliation(db, trigger_type="webhook_debounce")
            
            investigations = await investigate_all_exceptions(db, run.id)
            
            # Compile results
            auto_resolved = sum(1 for inv in investigations if inv.resolution_type == "auto")
            escalated = sum(1 for inv in investigations if inv.resolution_type is None)
            human_review = sum(
                1 for inv in investigations
                if inv.recommended_action == "escalate" and inv.resolution_type is None
            )

            # Financial metrics
            exc_result = await db.execute(select(Exception_).where(Exception_.run_id == run.id))
            exceptions = exc_result.scalars().all()
            
            total_exception_amount = sum(e.amount_at_risk for e in exceptions)
            auto_resolved_amount = sum(e.amount_at_risk for e in exceptions if e.status == "resolved")
            human_review_amount = sum(e.amount_at_risk for e in exceptions if e.status != "resolved")
            match_rate = run.matched / run.total_records if run.total_records else 0

            run.summary["financial_impact"] = {
                "total_exception_amount": total_exception_amount,
                "auto_resolved_amount": auto_resolved_amount,
                "human_review_amount": human_review_amount,
                "match_rate": round(match_rate, 4),
            }
            flag_modified(run, "summary")
            await db.commit()

            broadcast_sse("pipeline.completed", {
                "run_id": run.id,
                "total_records": run.total_records,
                "matched": run.matched,
                "exceptions": run.exceptions_count,
                "auto_resolved": auto_resolved,
                "escalated": escalated,
                "human_review": human_review,
                "duration_ms": run.duration_ms,
            })
    except asyncio.CancelledError:
        pass
    except Exception as e:
        print(f"Error in debounced pipeline: {e}")



async def _handle_txn_captured(db: AsyncSession, payload: dict, event_id: int):
    """Handle a new captured transaction event."""
    from sqlalchemy.dialects.postgresql import insert

    txn_data = {
        "id": payload.get("id", f"evt_txn_{event_id}"),
        "type": payload.get("type", "payment"),
        "order_id": payload.get("order_id"),
        "amount": payload.get("amount", 0),
        "currency": payload.get("currency", "INR"),
        "status": payload.get("status", "captured"),
        "fee": payload.get("fee", 0),
        "tax": payload.get("tax", 0),
        "settlement_id": payload.get("settlement_id"),
        "method": payload.get("method"),
        "description": payload.get("description"),
        "captured_at": datetime.utcnow(),
        "created_at": datetime.utcnow(),
        "source": "webhook",
    }

    stmt = insert(Transaction).values(txn_data).on_conflict_do_nothing(index_elements=["id"])
    await db.execute(stmt)

    await log_audit(
        db, "transaction", txn_data["id"],
        action="ingested_via_webhook",
        actor="system",
        new_state={"event_id": event_id, "amount": txn_data["amount"]},
    )

    broadcast_sse("txn.ingested", {
        "transaction_id": txn_data["id"],
        "amount": txn_data["amount"],
        "type": txn_data["type"],
    })


async def _handle_settlement_processed(db: AsyncSession, payload: dict, event_id: int):
    """Handle a processed settlement event."""
    from sqlalchemy.dialects.postgresql import insert

    setl_data = {
        "id": payload.get("id", f"evt_setl_{event_id}"),
        "amount": payload.get("amount", 0),
        "fees": payload.get("fees", 0),
        "tax": payload.get("tax", 0),
        "utr": payload.get("utr"),
        "status": "processed",
        "created_at": datetime.utcnow(),
    }

    stmt = insert(Settlement).values(setl_data).on_conflict_do_nothing(index_elements=["id"])
    await db.execute(stmt)

    await log_audit(
        db, "settlement", setl_data["id"],
        action="ingested_via_webhook",
        actor="system",
        new_state={"event_id": event_id, "amount": setl_data["amount"]},
    )

    broadcast_sse("settlement.ingested", {
        "settlement_id": setl_data["id"],
        "amount": setl_data["amount"],
        "utr": setl_data["utr"],
    })


async def _handle_bank_stmt_uploaded(db: AsyncSession, payload: dict, event_id: int):
    """Handle a bank statement upload event."""
    from datetime import date as date_type

    entry_date = payload.get("entry_date")
    if isinstance(entry_date, str):
        entry_date = datetime.strptime(entry_date, "%Y-%m-%d").date()
    elif not entry_date:
        entry_date = datetime.utcnow().date()

    bank_entry = BankStatement(
        bank_account=payload.get("bank_account", "UNKNOWN"),
        entry_date=entry_date,
        description=payload.get("description"),
        reference=payload.get("reference"),
        credit=payload.get("credit", 0),
        debit=payload.get("debit", 0),
        balance=payload.get("balance"),
    )
    db.add(bank_entry)
    await db.flush()

    await log_audit(
        db, "bank_statement", str(bank_entry.id),
        action="ingested_via_webhook",
        actor="system",
        new_state={"event_id": event_id, "credit": bank_entry.credit},
    )

    broadcast_sse("bank_stmt.ingested", {
        "bank_stmt_id": bank_entry.id,
        "credit": bank_entry.credit,
        "reference": bank_entry.reference,
    })


async def _handle_exception_detected(db: AsyncSession, payload: dict, event_id: int):
    """Handle an externally detected exception event."""
    broadcast_sse("exception.external", {
        "event_id": event_id,
        "payload": payload,
    })


@router.get("/stream")
async def event_stream(request: Request):
    """SSE endpoint: streams reconciliation updates to the frontend."""
    queue: asyncio.Queue = asyncio.Queue(maxsize=100)
    _sse_subscribers.append(queue)

    async def generate() -> AsyncGenerator:
        try:
            # Send initial connection event
            yield {"event": "connected", "data": json.dumps({"status": "connected"})}

            while True:
                # Check if client disconnected
                if await request.is_disconnected():
                    break

                try:
                    message = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield message
                except asyncio.TimeoutError:
                    # Send keepalive ping
                    yield {"event": "ping", "data": json.dumps({"ts": datetime.utcnow().isoformat()})}

        finally:
            _sse_subscribers.remove(queue)

    return EventSourceResponse(generate())


@router.post("/investigate-all")
async def investigate_all(
    run_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Trigger AI investigation for all detected exceptions in a run."""
    from app.services.ai_investigator import investigate_all_exceptions

    broadcast_sse("investigation.started", {"run_id": run_id})

    investigations = await investigate_all_exceptions(db, run_id)

    results = []
    for inv in investigations:
        results.append({
            "exception_id": inv.exception_id,
            "root_cause": inv.root_cause,
            "confidence": inv.confidence,
            "recommended_action": inv.recommended_action,
            "resolution_type": inv.resolution_type,
            "model_used": inv.model_used,
            "latency_ms": inv.latency_ms,
        })

        # Broadcast each investigation result
        broadcast_sse("investigation.completed", {
            "exception_id": inv.exception_id,
            "confidence": inv.confidence,
            "action": inv.recommended_action,
        })

    broadcast_sse("investigation.all_completed", {
        "run_id": run_id,
        "total": len(results),
    })

    return {
        "run_id": run_id,
        "investigations_completed": len(results),
        "results": results,
    }


@router.post("/run-full-pipeline")
async def run_full_pipeline(
    db: AsyncSession = Depends(get_db),
):
    """
    Run the complete pipeline: Reconcile → Investigate → Resolve/Escalate.
    This is the main demo endpoint.
    """
    from app.services.reconciliation_engine import run_reconciliation
    from app.services.ai_investigator import investigate_all_exceptions

    # Step 1: Reconcile
    broadcast_sse("pipeline.step", {"step": "reconciliation", "status": "started"})
    run = await run_reconciliation(db, trigger_type="manual")
    broadcast_sse("pipeline.step", {
        "step": "reconciliation",
        "status": "completed",
        "matched": run.matched,
        "mismatched": run.mismatched,
        "unmatched": run.unmatched,
        "exceptions": run.exceptions_count,
        "duration_ms": run.duration_ms,
    })

    # Step 2: Investigate exceptions
    broadcast_sse("pipeline.step", {"step": "investigation", "status": "started"})
    investigations = await investigate_all_exceptions(db, run.id)
    broadcast_sse("pipeline.step", {
        "step": "investigation",
        "status": "completed",
        "investigated": len(investigations),
    })

    # Compile results
    auto_resolved = sum(1 for inv in investigations if inv.resolution_type == "auto")
    escalated = sum(1 for inv in investigations if inv.resolution_type is None)
    human_review = sum(
        1 for inv in investigations
        if inv.recommended_action == "escalate" and inv.resolution_type is None
    )

    # Fetch exceptions to calculate financial metrics
    exc_result = await db.execute(
        select(Exception_).where(Exception_.run_id == run.id)
    )
    exceptions = exc_result.scalars().all()
    
    total_exception_amount = sum(e.amount_at_risk for e in exceptions)
    auto_resolved_amount = sum(e.amount_at_risk for e in exceptions if e.status == "resolved")
    human_review_amount = sum(e.amount_at_risk for e in exceptions if e.status != "resolved")
    match_rate = run.matched / run.total_records if run.total_records else 0

    run.summary["financial_impact"] = {
        "total_exception_amount": total_exception_amount,
        "auto_resolved_amount": auto_resolved_amount,
        "human_review_amount": human_review_amount,
        "match_rate": round(match_rate, 4),
    }
    # We must mark it as modified for SQLAlchemy's JSON type
    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(run, "summary")
    await db.flush()

    broadcast_sse("pipeline.completed", {
        "run_id": run.id,
        "total_records": run.total_records,
        "matched": run.matched,
        "exceptions": run.exceptions_count,
        "auto_resolved": auto_resolved,
        "escalated": escalated,
        "human_review": human_review,
        "duration_ms": run.duration_ms,
    })

    return {
        "run_id": run.id,
        "reconciliation": {
            "total_records": run.total_records,
            "matched": run.matched,
            "mismatched": run.mismatched,
            "unmatched": run.unmatched,
            "exceptions": run.exceptions_count,
            "duration_ms": run.duration_ms,
        },
        "investigation": {
            "total_investigated": len(investigations),
            "auto_resolved": auto_resolved,
            "escalated": escalated,
            "human_review": human_review,
        },
        "summary": run.summary,
    }


@router.get("/pending")
async def get_pending_events(
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
):
    """Get recent pending/failed events for monitoring."""
    result = await db.execute(
        select(Event)
        .where(Event.status.in_(["pending", "failed"]))
        .order_by(desc(Event.created_at))
        .limit(limit)
    )
    events = result.scalars().all()
    return [
        {
            "id": e.id,
            "event_type": e.event_type,
            "status": e.status,
            "attempts": e.attempts,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        }
        for e in events
    ]
