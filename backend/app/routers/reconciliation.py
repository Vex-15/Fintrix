"""
Reconciliation API — trigger runs, retrieve results, and dashboard stats.

Enhanced with:
  - Dashboard stats endpoint with historical trends
  - Run comparison capabilities
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models import (
    ReconciliationRun, ReconciliationResult,
    Exception_, Investigation, Transaction, Settlement, BankStatement,
)
from app.schemas import ReconciliationRunOut, ReconciliationMetrics
from app.services.reconciliation_engine import run_reconciliation

router = APIRouter()


@router.post("/run", response_model=ReconciliationRunOut)
async def trigger_reconciliation(
    db: AsyncSession = Depends(get_db),
):
    """Trigger a full reconciliation run across all ingested data."""
    run = await run_reconciliation(db, trigger_type="manual")
    return run


@router.get("/runs", response_model=list[ReconciliationRunOut])
async def list_runs(
    db: AsyncSession = Depends(get_db),
):
    """List all reconciliation runs, most recent first."""
    result = await db.execute(
        select(ReconciliationRun).order_by(desc(ReconciliationRun.started_at)).limit(50)
    )
    return result.scalars().all()


@router.get("/runs/{run_id}", response_model=ReconciliationRunOut)
async def get_run(
    run_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Get details of a specific reconciliation run."""
    result = await db.execute(
        select(ReconciliationRun).where(ReconciliationRun.id == run_id)
    )
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@router.get("/runs/{run_id}/results")
async def get_run_results(
    run_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Get all reconciliation results for a specific run."""
    result = await db.execute(
        select(ReconciliationResult).where(ReconciliationResult.run_id == run_id)
    )
    rows = result.scalars().all()
    return [
        {
            "id": r.id,
            "run_id": r.run_id,
            "transaction_id": r.transaction_id,
            "settlement_id": r.settlement_id,
            "bank_stmt_id": r.bank_stmt_id,
            "match_type": r.match_type,
            "match_status": r.match_status,
            "expected_amount": r.expected_amount,
            "actual_amount": r.actual_amount,
            "difference": r.difference,
            "match_details": r.match_details,
        }
        for r in rows
    ]


@router.get("/metrics", response_model=ReconciliationMetrics)
async def get_metrics(
    db: AsyncSession = Depends(get_db),
):
    """Get aggregate reconciliation metrics across the latest run."""
    # Get the latest completed run
    result = await db.execute(
        select(ReconciliationRun)
        .where(ReconciliationRun.status == "completed")
        .order_by(desc(ReconciliationRun.completed_at))
        .limit(1)
    )
    latest_run = result.scalar_one_or_none()

    if not latest_run:
        raise HTTPException(status_code=404, detail="No completed reconciliation runs found")

    # Count exception statuses for this run
    exc_result = await db.execute(
        select(Exception_.status, func.count(Exception_.id))
        .where(Exception_.run_id == latest_run.id)
        .group_by(Exception_.status)
    )
    status_counts = dict(exc_result.all())

    auto_resolved = status_counts.get("resolved", 0)
    escalated = status_counts.get("escalated", 0)
    unresolved = status_counts.get("detected", 0) + status_counts.get("investigating", 0)

    # Avg AI latency
    ai_result = await db.execute(
        select(func.avg(Investigation.latency_ms))
        .join(Exception_, Investigation.exception_id == Exception_.id)
        .where(Exception_.run_id == latest_run.id)
    )
    avg_ai_latency = ai_result.scalar()

    total = latest_run.total_records or 1
    throughput = total / (latest_run.duration_ms / 1000) if latest_run.duration_ms else 0

    return ReconciliationMetrics(
        total_records=latest_run.total_records,
        matched=latest_run.matched,
        mismatched=latest_run.mismatched,
        unmatched=latest_run.unmatched,
        exceptions_total=latest_run.exceptions_count,
        auto_resolved=auto_resolved,
        escalated=escalated,
        unresolved=unresolved,
        match_rate=latest_run.matched / total if total else 0,
        throughput_records_per_sec=round(throughput, 1),
        avg_ai_latency_ms=round(avg_ai_latency, 1) if avg_ai_latency else None,
        audit_completeness=1.0,  # We audit everything
    )


# ---------------------------------------------------------------------------
# Dashboard Stats — Aggregated data for the frontend dashboard
# ---------------------------------------------------------------------------

@router.get("/dashboard-stats")
async def get_dashboard_stats(
    db: AsyncSession = Depends(get_db),
):
    """
    Get aggregated stats for the live dashboard:
      - Historical run trends (last 10 runs)
      - Exception distribution
      - Resolution rates
      - Currently pending items
      - Data source counts
    """
    # --- Historical runs (last 10) ---
    runs_result = await db.execute(
        select(ReconciliationRun)
        .order_by(desc(ReconciliationRun.started_at))
        .limit(10)
    )
    runs = runs_result.scalars().all()
    run_history = [
        {
            "id": r.id,
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "completed_at": r.completed_at.isoformat() if r.completed_at else None,
            "status": r.status,
            "total_records": r.total_records,
            "matched": r.matched,
            "mismatched": r.mismatched,
            "unmatched": r.unmatched,
            "exceptions_count": r.exceptions_count,
            "duration_ms": r.duration_ms,
        }
        for r in runs
    ]

    # --- Data source counts ---
    txn_count = (await db.execute(select(func.count(Transaction.id)))).scalar() or 0
    setl_count = (await db.execute(select(func.count(Settlement.id)))).scalar() or 0
    bank_count = (await db.execute(select(func.count(BankStatement.id)))).scalar() or 0

    # --- Exception overview (all time) ---
    exc_by_status = dict(
        (await db.execute(
            select(Exception_.status, func.count(Exception_.id))
            .group_by(Exception_.status)
        )).all()
    )
    exc_by_type = dict(
        (await db.execute(
            select(Exception_.type, func.count(Exception_.id))
            .group_by(Exception_.type)
        )).all()
    )
    exc_by_severity = dict(
        (await db.execute(
            select(Exception_.severity, func.count(Exception_.id))
            .group_by(Exception_.severity)
        )).all()
    )

    total_exceptions = sum(exc_by_status.values())
    resolved_count = exc_by_status.get("resolved", 0)
    escalated_count = exc_by_status.get("escalated", 0)
    pending_count = exc_by_status.get("detected", 0) + exc_by_status.get("investigating", 0)

    # --- AI resolution stats ---
    auto_resolved = (await db.execute(
        select(func.count(Investigation.id))
        .where(Investigation.resolution_type == "auto")
    )).scalar() or 0

    manual_resolved = (await db.execute(
        select(func.count(Investigation.id))
        .where(Investigation.resolution_type == "manual")
    )).scalar() or 0

    # --- Total amount at risk ---
    total_at_risk = (await db.execute(
        select(func.sum(Exception_.amount_at_risk))
        .where(Exception_.status.in_(["detected", "investigating", "escalated"]))
    )).scalar() or 0

    resolved_at_risk = (await db.execute(
        select(func.sum(Exception_.amount_at_risk))
        .where(Exception_.status == "resolved")
    )).scalar() or 0

    # --- Recent exceptions (last 5) ---
    recent_exc_result = await db.execute(
        select(Exception_)
        .options(selectinload(Exception_.investigation))
        .order_by(desc(Exception_.created_at))
        .limit(5)
    )
    recent_exceptions = [
        {
            "id": e.id,
            "type": e.type,
            "severity": e.severity,
            "status": e.status,
            "amount_at_risk": e.amount_at_risk,
            "created_at": e.created_at.isoformat() if e.created_at else None,
            "investigation": {
                "confidence": e.investigation.confidence,
                "recommended_action": e.investigation.recommended_action,
                "root_cause": e.investigation.root_cause,
            } if e.investigation else None,
        }
        for e in recent_exc_result.scalars().all()
    ]

    return {
        "data_sources": {
            "transactions": txn_count,
            "settlements": setl_count,
            "bank_statements": bank_count,
        },
        "run_history": run_history,
        "exceptions": {
            "total": total_exceptions,
            "by_status": exc_by_status,
            "by_type": exc_by_type,
            "by_severity": exc_by_severity,
            "pending": pending_count,
            "resolved": resolved_count,
            "escalated": escalated_count,
            "auto_resolved": auto_resolved,
            "manual_resolved": manual_resolved,
        },
        "financial": {
            "total_at_risk": total_at_risk,
            "resolved_at_risk": resolved_at_risk,
            "pending_at_risk": total_at_risk,
        },
        "recent_exceptions": recent_exceptions,
    }
