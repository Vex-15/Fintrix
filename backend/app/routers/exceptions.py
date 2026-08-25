"""
Exceptions API — view, investigate, and act on reconciliation exceptions.

Enhanced with:
  - Deep investigation endpoint (txn vs bank comparison, evidence, timeline)
  - Bulk action endpoint for mass resolution/escalation
  - Entity-specific audit timeline
  - Notes/comments per exception
"""

from datetime import datetime
from fastapi import APIRouter, Depends, Path, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models import (
    Exception_, Investigation, Transaction, Settlement,
    BankStatement, AuditLog, ReconciliationResult, ExceptionNote, User,
)
from app.schemas import ExceptionOut, ExceptionActionRequest, ExceptionNoteCreate, ExceptionNoteOut
from app.utils.audit import log_audit
from app.services.auth import get_current_user, get_current_user_optional

router = APIRouter()


@router.get("/", response_model=list[ExceptionOut])
async def list_exceptions(
    status: str | None = None,
    severity: str | None = None,
    type: str | None = None,
    run_id: int | None = None,
    limit: int = Query(default=100, le=500),
    db: AsyncSession = Depends(get_db),
):
    """List exceptions, optionally filtered by status, severity, type, or run."""
    query = (
        select(Exception_)
        .options(selectinload(Exception_.investigation))
        .order_by(desc(Exception_.created_at))
        .limit(limit)
    )

    if status:
        query = query.where(Exception_.status == status)
    if severity:
        query = query.where(Exception_.severity == severity)
    if type:
        query = query.where(Exception_.type == type)
    if run_id is not None:
        query = query.where(Exception_.run_id == run_id)

    result = await db.execute(query)
    return result.scalars().all()


@router.get("/summary")
async def exceptions_summary(
    run_id: int | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Get counts grouped by type and status."""
    # By type
    type_query = select(Exception_.type, func.count(Exception_.id)).group_by(Exception_.type)
    status_query = select(Exception_.status, func.count(Exception_.id)).group_by(Exception_.status)
    severity_query = select(Exception_.severity, func.count(Exception_.id)).group_by(Exception_.severity)

    if run_id is not None:
        type_query = type_query.where(Exception_.run_id == run_id)
        status_query = status_query.where(Exception_.run_id == run_id)
        severity_query = severity_query.where(Exception_.run_id == run_id)

    by_type = dict((await db.execute(type_query)).all())
    by_status = dict((await db.execute(status_query)).all())
    by_severity = dict((await db.execute(severity_query)).all())

    return {
        "by_type": by_type,
        "by_status": by_status,
        "by_severity": by_severity,
        "total": sum(by_status.values()),
    }


@router.get("/clusters")
async def get_exception_clusters(db: AsyncSession = Depends(get_db)):
    """
    Cluster unresolved exceptions by pattern (type or settlement_id).
    Aggregates financial impact for each cluster.
    """
    result = await db.execute(
        select(Exception_).where(Exception_.status.in_(["detected", "investigating", "escalated"]))
    )
    exceptions = result.scalars().all()
    
    clusters = {}
    for exc in exceptions:
        # Determine a clustering key
        cluster_key = exc.type
        if exc.type == "amount_mismatch" and exc.context and "settlement_id" in exc.context:
            cluster_key = f"amount_mismatch_setl_{exc.context['settlement_id']}"
            
        if cluster_key not in clusters:
            clusters[cluster_key] = {
                "pattern": cluster_key,
                "count": 0,
                "total_impact": 0,
                "exception_ids": []
            }
        
        clusters[cluster_key]["count"] += 1
        clusters[cluster_key]["total_impact"] += exc.amount_at_risk
        clusters[cluster_key]["exception_ids"].append(exc.id)
        
    # Sort clusters by total impact descending
    cluster_list = list(clusters.values())
    cluster_list.sort(key=lambda x: x["total_impact"], reverse=True)
    
    return cluster_list


@router.get("/{exception_id}", response_model=ExceptionOut)
async def get_exception(
    exception_id: int = Path(...),
    db: AsyncSession = Depends(get_db),
):
    """Get a single exception with its investigation (if any)."""
    result = await db.execute(
        select(Exception_)
        .options(selectinload(Exception_.investigation))
        .where(Exception_.id == exception_id)
    )
    exc = result.scalar_one_or_none()
    if not exc:
        raise HTTPException(status_code=404, detail="Exception not found")
    return exc


# ---------------------------------------------------------------------------
# Deep Investigation Endpoint
# ---------------------------------------------------------------------------

@router.get("/{exception_id}/deep-investigation")
async def get_deep_investigation(
    exception_id: int = Path(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Deep investigation view: transaction vs bank record comparison,
    AI root-cause report, evidence, related records, investigation timeline.
    """
    # Load exception with investigation
    result = await db.execute(
        select(Exception_)
        .options(selectinload(Exception_.investigation))
        .where(Exception_.id == exception_id)
    )
    exc = result.scalar_one_or_none()
    if not exc:
        raise HTTPException(status_code=404, detail="Exception not found")

    ctx = exc.context or {}

    # --- Gather transaction records ---
    transaction_records = []
    txn_ids = []
    if "transaction_id" in ctx:
        txn_ids.append(ctx["transaction_id"])
    if "original_id" in ctx:
        txn_ids.append(ctx["original_id"])
    if "duplicate_id" in ctx:
        txn_ids.append(ctx["duplicate_id"])
    if "payment_ids" in ctx:
        txn_ids.extend(ctx["payment_ids"])
    if "refund_ids" in ctx:
        txn_ids.extend(ctx["refund_ids"])

    if txn_ids:
        txn_result = await db.execute(
            select(Transaction).where(Transaction.id.in_(txn_ids))
        )
        for txn in txn_result.scalars().all():
            transaction_records.append({
                "id": txn.id,
                "type": txn.type,
                "order_id": txn.order_id,
                "amount": txn.amount,
                "currency": txn.currency,
                "status": txn.status,
                "fee": txn.fee,
                "tax": txn.tax,
                "settlement_id": txn.settlement_id,
                "method": txn.method,
                "description": txn.description,
                "captured_at": txn.captured_at.isoformat() if txn.captured_at else None,
                "created_at": txn.created_at.isoformat() if txn.created_at else None,
                "source": txn.source,
            })

    # --- Gather settlement record ---
    settlement_record = None
    setl_id = ctx.get("settlement_id")
    if setl_id:
        setl_result = await db.execute(
            select(Settlement).where(Settlement.id == setl_id)
        )
        setl = setl_result.scalar_one_or_none()
        if setl:
            settlement_record = {
                "id": setl.id,
                "amount": setl.amount,
                "fees": setl.fees,
                "tax": setl.tax,
                "utr": setl.utr,
                "status": setl.status,
                "created_at": setl.created_at.isoformat() if setl.created_at else None,
            }

    # --- Gather bank record (by UTR or bank_stmt_id) ---
    bank_record = None
    utr = ctx.get("utr")
    if utr:
        bank_result = await db.execute(
            select(BankStatement).where(BankStatement.reference == utr)
        )
        bank = bank_result.scalar_one_or_none()
        if bank:
            bank_record = {
                "id": bank.id,
                "bank_account": bank.bank_account,
                "entry_date": bank.entry_date.isoformat() if bank.entry_date else None,
                "description": bank.description,
                "reference": bank.reference,
                "credit": bank.credit,
                "debit": bank.debit,
                "balance": bank.balance,
            }

    # --- Reconciliation result ---
    recon_result_data = None
    if exc.result_id:
        rr_result = await db.execute(
            select(ReconciliationResult).where(ReconciliationResult.id == exc.result_id)
        )
        rr = rr_result.scalar_one_or_none()
        if rr:
            recon_result_data = {
                "match_type": rr.match_type,
                "match_status": rr.match_status,
                "match_score": rr.match_score,
                "expected_amount": rr.expected_amount,
                "actual_amount": rr.actual_amount,
                "difference": rr.difference,
                "match_details": rr.match_details,
            }

    # --- Investigation report ---
    investigation_report = None
    if exc.investigation:
        inv = exc.investigation
        investigation_report = {
            "id": inv.id,
            "root_cause": inv.root_cause,
            "evidence": inv.evidence,
            "confidence": inv.confidence,
            "recommended_action": inv.recommended_action,
            "explanation": inv.explanation,
            "resolution_type": inv.resolution_type,
            "resolved_by": inv.resolved_by,
            "model_used": inv.model_used,
            "prompt_tokens": inv.prompt_tokens,
            "response_tokens": inv.response_tokens,
            "latency_ms": inv.latency_ms,
            "chain_of_thought": inv.chain_of_thought,
            "agent_decision_trace": inv.agent_decision_trace,
            "user_feedback": inv.user_feedback,
            "created_at": inv.created_at.isoformat() if inv.created_at else None,
        }

    # --- Audit timeline for this exception ---
    timeline_result = await db.execute(
        select(AuditLog)
        .where(AuditLog.entity_type == "exception", AuditLog.entity_id == str(exception_id))
        .order_by(AuditLog.timestamp)
    )
    timeline = [
        {
            "id": log.id,
            "timestamp": log.timestamp.isoformat() if log.timestamp else None,
            "action": log.action,
            "actor": log.actor,
            "old_state": log.old_state,
            "new_state": log.new_state,
        }
        for log in timeline_result.scalars().all()
    ]

    # --- Notes ---
    notes_result = await db.execute(
        select(ExceptionNote)
        .where(ExceptionNote.exception_id == exception_id)
        .order_by(ExceptionNote.created_at)
    )
    notes = [
        {
            "id": n.id,
            "user_id": n.user_id,
            "content": n.content,
            "created_at": n.created_at.isoformat() if n.created_at else None,
        }
        for n in notes_result.scalars().all()
    ]

    # --- Comparison data (transaction vs bank) ---
    comparison = None
    if transaction_records and (bank_record or settlement_record):
        txn_total = sum(t["amount"] for t in transaction_records if t["type"] == "payment")
        txn_fees = sum(t["fee"] for t in transaction_records if t["type"] == "payment")
        txn_tax = sum(t["tax"] for t in transaction_records if t["type"] == "payment")
        txn_refunds = sum(t["amount"] for t in transaction_records if t["type"] == "refund")
        txn_net = txn_total - txn_fees - txn_tax - txn_refunds

        comparison = {
            "transaction_side": {
                "gross_amount": txn_total,
                "fees": txn_fees,
                "tax": txn_tax,
                "refunds": txn_refunds,
                "net_amount": txn_net,
                "record_count": len(transaction_records),
            },
            "settlement_side": {
                "amount": settlement_record["amount"] if settlement_record else None,
                "fees": settlement_record["fees"] if settlement_record else None,
                "tax": settlement_record["tax"] if settlement_record else None,
                "utr": settlement_record["utr"] if settlement_record else None,
            } if settlement_record else None,
            "bank_side": {
                "credit": bank_record["credit"] if bank_record else None,
                "reference": bank_record["reference"] if bank_record else None,
                "entry_date": bank_record["entry_date"] if bank_record else None,
            } if bank_record else None,
            "discrepancy": {
                "type": exc.type,
                "amount_at_risk": exc.amount_at_risk,
                "severity": exc.severity,
            },
        }

    return {
        "exception": {
            "id": exc.id,
            "run_id": exc.run_id,
            "type": exc.type,
            "severity": exc.severity,
            "status": exc.status,
            "amount_at_risk": exc.amount_at_risk,
            "context": exc.context,
            "created_at": exc.created_at.isoformat() if exc.created_at else None,
            "resolved_at": exc.resolved_at.isoformat() if exc.resolved_at else None,
        },
        "transaction_records": transaction_records,
        "settlement_record": settlement_record,
        "bank_record": bank_record,
        "reconciliation_result": recon_result_data,
        "investigation": investigation_report,
        "comparison": comparison,
        "timeline": timeline,
        "notes": notes,
    }


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------

@router.post("/{exception_id}/action")
async def act_on_exception(
    exception_id: int = Path(...),
    body: ExceptionActionRequest = ...,
    db: AsyncSession = Depends(get_db),
):
    """
    Approve, reject, or escalate an exception.

    - approve: Accept the AI's recommendation and resolve
    - reject: Reject the AI's recommendation, mark as needs further review
    - escalate: Manually escalate to human review
    """
    result = await db.execute(
        select(Exception_).where(Exception_.id == exception_id)
    )
    exc = result.scalar_one_or_none()
    if not exc:
        raise HTTPException(status_code=404, detail="Exception not found")

    old_status = exc.status

    if body.action == "approve":
        exc.status = "resolved"
        exc.resolved_at = datetime.utcnow()

        # Update investigation if exists
        inv_result = await db.execute(
            select(Investigation).where(Investigation.exception_id == exception_id)
        )
        inv = inv_result.scalar_one_or_none()
        if inv:
            inv.resolution_type = "manual"
            inv.resolved_by = "human_reviewer"

    elif body.action == "reject":
        exc.status = "detected"  # Reset to detected for re-investigation

    elif body.action == "escalate":
        exc.status = "escalated"

    else:
        raise HTTPException(status_code=400, detail=f"Invalid action: {body.action}")

    await log_audit(
        db, "exception", str(exception_id),
        action=f"manual_{body.action}",
        actor="human",
        old_state={"status": old_status},
        new_state={"status": exc.status, "reason": body.reason},
    )

    await db.flush()

    return {
        "exception_id": exception_id,
        "action": body.action,
        "new_status": exc.status,
        "reason": body.reason,
    }


@router.post("/{exception_id}/feedback")
async def add_feedback(
    exception_id: int = Path(...),
    body: dict = ...,
    db: AsyncSession = Depends(get_db),
):
    """
    Provide human feedback (helpful/unhelpful) on an AI investigation decision.
    """
    feedback = body.get("feedback")
    if feedback not in ("helpful", "unhelpful"):
        raise HTTPException(status_code=400, detail="Feedback must be 'helpful' or 'unhelpful'")

    result = await db.execute(
        select(Investigation).where(Investigation.exception_id == exception_id)
    )
    inv = result.scalar_one_or_none()
    if not inv:
        raise HTTPException(status_code=404, detail="Investigation not found for this exception")

    inv.user_feedback = feedback
    await db.flush()

    return {"status": "success", "feedback": feedback}


# ---------------------------------------------------------------------------
# Bulk Actions
# ---------------------------------------------------------------------------

@router.post("/bulk-action")
async def bulk_action(
    body: dict,
    db: AsyncSession = Depends(get_db),
):
    """
    Apply an action to multiple exceptions at once.

    Body: { "exception_ids": [1, 2, 3], "action": "approve"|"escalate"|"reject", "reason": "..." }
    """
    exception_ids = body.get("exception_ids", [])
    action = body.get("action", "")
    reason = body.get("reason", "Bulk action from dashboard")

    if action not in ("approve", "escalate", "reject"):
        raise HTTPException(status_code=400, detail=f"Invalid action: {action}")
    if not exception_ids:
        raise HTTPException(status_code=400, detail="No exception IDs provided")

    results = []
    for eid in exception_ids:
        result = await db.execute(
            select(Exception_).where(Exception_.id == eid)
        )
        exc = result.scalar_one_or_none()
        if not exc:
            results.append({"exception_id": eid, "status": "not_found"})
            continue

        old_status = exc.status

        if action == "approve":
            exc.status = "resolved"
            exc.resolved_at = datetime.utcnow()
            inv_result = await db.execute(
                select(Investigation).where(Investigation.exception_id == eid)
            )
            inv = inv_result.scalar_one_or_none()
            if inv:
                inv.resolution_type = "manual"
                inv.resolved_by = "human_reviewer"
        elif action == "reject":
            exc.status = "detected"
        elif action == "escalate":
            exc.status = "escalated"

        await log_audit(
            db, "exception", str(eid),
            action=f"bulk_{action}",
            actor="human",
            old_state={"status": old_status},
            new_state={"status": exc.status, "reason": reason},
        )
        results.append({"exception_id": eid, "new_status": exc.status})

    await db.flush()

    return {
        "action": action,
        "processed": len(results),
        "results": results,
    }


# ---------------------------------------------------------------------------
# Notes / Comments
# ---------------------------------------------------------------------------

@router.get("/{exception_id}/notes", response_model=list[ExceptionNoteOut])
async def list_notes(
    exception_id: int = Path(...),
    db: AsyncSession = Depends(get_db),
):
    """Get all notes/comments for an exception."""
    result = await db.execute(
        select(ExceptionNote)
        .where(ExceptionNote.exception_id == exception_id)
        .order_by(ExceptionNote.created_at)
    )
    return result.scalars().all()


@router.post("/{exception_id}/notes", response_model=ExceptionNoteOut, status_code=201)
async def add_note(
    exception_id: int = Path(...),
    body: ExceptionNoteCreate = ...,
    current_user: User = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """Add a note/comment to an exception."""
    # Verify exception exists
    result = await db.execute(
        select(Exception_).where(Exception_.id == exception_id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Exception not found")

    note = ExceptionNote(
        exception_id=exception_id,
        user_id=current_user.id if current_user else None,
        content=body.content,
    )
    db.add(note)
    await db.flush()

    actor = current_user.email if current_user else "anonymous"
    await log_audit(
        db, "exception", str(exception_id),
        action="note_added",
        actor=actor,
        new_state={"note_id": note.id, "content_preview": body.content[:100]},
    )

    return note
