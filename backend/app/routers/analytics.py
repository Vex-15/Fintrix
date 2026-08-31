"""
Analytics API — trend data, SLA tracking, and ROI calculations.
"""

from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc, case

from app.database import get_db
from app.models import (
    ReconciliationRun, Exception_, Investigation,
    Transaction, User,
)
from app.services.auth import get_current_user

router = APIRouter()


@router.get("/trends")
async def get_trends(
    days: int = Query(default=30, le=90),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Historical accuracy, exception volume, and resolution trends.
    Returns daily aggregates for the last N days.
    """
    cutoff = datetime.utcnow() - timedelta(days=days)

    # Get all completed runs in the period
    runs_result = await db.execute(
        select(ReconciliationRun)
        .where(
            ReconciliationRun.status == "completed",
            ReconciliationRun.completed_at >= cutoff,
        )
        .order_by(ReconciliationRun.completed_at)
    )
    runs = runs_result.scalars().all()

    # Run-level trend data
    run_trends = []
    for run in runs:
        total = run.total_records or 1
        accuracy = run.matched / total if total else 0
        run_trends.append({
            "date": run.completed_at.strftime("%Y-%m-%d") if run.completed_at else None,
            "run_id": run.id,
            "total_records": run.total_records,
            "matched": run.matched,
            "exceptions": run.exceptions_count,
            "accuracy": round(accuracy, 4),
            "duration_ms": run.duration_ms,
        })

    # Exception trend (by day)
    exc_result = await db.execute(
        select(
            func.date(Exception_.created_at).label("day"),
            func.count(Exception_.id).label("total"),
            func.sum(case((Exception_.status == "resolved", 1), else_=0)).label("resolved"),
            func.sum(case((Exception_.status == "escalated", 1), else_=0)).label("escalated"),
            func.sum(Exception_.amount_at_risk).label("total_risk"),
        )
        .where(Exception_.created_at >= cutoff)
        .group_by(func.date(Exception_.created_at))
        .order_by(func.date(Exception_.created_at))
    )
    exception_trends = [
        {
            "date": str(row.day),
            "total": row.total,
            "resolved": int(row.resolved or 0),
            "escalated": int(row.escalated or 0),
            "total_risk_paise": int(row.total_risk or 0),
        }
        for row in exc_result.all()
    ]

    # Calculate ageing metrics for unresolved exceptions
    now = datetime.utcnow()
    ageing = {"0_to_3_days": 0, "4_to_7_days": 0, "8_plus_days": 0}
    
    unresolved = await db.execute(
        select(Exception_.created_at)
        .where(Exception_.status != "resolved")
    )
    for (created_at,) in unresolved.all():
        if not created_at:
            continue
        age_days = (now - created_at).days
        if age_days <= 3:
            ageing["0_to_3_days"] += 1
        elif age_days <= 7:
            ageing["4_to_7_days"] += 1
        else:
            ageing["8_plus_days"] += 1

    return {
        "period_days": days,
        "run_trends": run_trends,
        "exception_trends": exception_trends,
        "summary": {
            "total_runs": len(runs),
            "avg_accuracy": round(sum(r["accuracy"] for r in run_trends) / max(len(run_trends), 1), 4),
            "total_exceptions": sum(r["total"] for r in exception_trends),
            "total_resolved": sum(r["resolved"] for r in exception_trends),
            "total_funds_at_risk_paise": sum(r["total_risk_paise"] for r in exception_trends),
        },
        "ageing_metrics": ageing,
    }


@router.get("/sla")
async def get_sla_metrics(
    days: int = Query(default=30, le=90),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    SLA tracking: time-to-detect, time-to-investigate, time-to-resolve metrics.
    Returns P50, P95, P99 percentiles.
    """
    cutoff = datetime.utcnow() - timedelta(days=days)

    # Get resolved exceptions with investigation data
    inv_result = await db.execute(
        select(Investigation, Exception_)
        .join(Exception_, Investigation.exception_id == Exception_.id)
        .where(Exception_.created_at >= cutoff)
    )
    rows = inv_result.all()

    investigation_latencies = []
    resolution_times = []

    for inv, exc in rows:
        # AI investigation latency (ms)
        if inv.latency_ms:
            investigation_latencies.append(inv.latency_ms)

        # Time to resolve (seconds from detection to resolution)
        if exc.resolved_at and exc.created_at:
            resolve_time = (exc.resolved_at - exc.created_at).total_seconds()
            resolution_times.append(resolve_time)

    def percentiles(data: list[float]) -> dict:
        if not data:
            return {"p50": None, "p95": None, "p99": None, "avg": None, "count": 0}
        data.sort()
        n = len(data)
        return {
            "p50": round(data[n // 2], 1),
            "p95": round(data[int(n * 0.95)], 1) if n > 1 else round(data[0], 1),
            "p99": round(data[int(n * 0.99)], 1) if n > 1 else round(data[0], 1),
            "avg": round(sum(data) / n, 1),
            "count": n,
        }

    # Reconciliation throughput
    run_result = await db.execute(
        select(ReconciliationRun)
        .where(ReconciliationRun.status == "completed", ReconciliationRun.completed_at >= cutoff)
    )
    runs = run_result.scalars().all()
    run_durations = [r.duration_ms for r in runs if r.duration_ms]

    return {
        "period_days": days,
        "investigation_latency_ms": percentiles(investigation_latencies),
        "time_to_resolve_seconds": percentiles(resolution_times),
        "reconciliation_duration_ms": percentiles(run_durations),
        "throughput": {
            "total_runs": len(runs),
            "total_records_processed": sum(r.total_records for r in runs),
            "avg_records_per_run": round(sum(r.total_records for r in runs) / max(len(runs), 1), 1),
        },
    }


@router.get("/roi")
async def get_roi_metrics(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    ROI calculator: manual hours saved, cost savings estimate.
    
    Assumptions:
    - Manual reconciliation: ~2 minutes per transaction
    - Manual investigation: ~15 minutes per exception
    - Average accountant cost: ₹500/hour
    """
    MANUAL_RECON_MINUTES_PER_TXN = 2
    MANUAL_INVESTIGATION_MINUTES_PER_EXCEPTION = 15
    COST_PER_HOUR = 500  # ₹500/hour

    # Total records processed
    total_records = (await db.execute(
        select(func.sum(ReconciliationRun.total_records))
        .where(ReconciliationRun.status == "completed")
    )).scalar() or 0

    # Total exceptions auto-resolved
    auto_resolved = (await db.execute(
        select(func.count(Investigation.id))
        .where(Investigation.resolution_type == "auto")
    )).scalar() or 0

    # Total exceptions overall
    total_exceptions = (await db.execute(
        select(func.count(Exception_.id))
    )).scalar() or 0

    # Amount saved (auto-resolved exceptions)
    amount_saved = (await db.execute(
        select(func.sum(Exception_.amount_at_risk))
        .where(Exception_.status == "resolved")
    )).scalar() or 0

    # Calculate time savings
    recon_hours_saved = (total_records * MANUAL_RECON_MINUTES_PER_TXN) / 60
    investigation_hours_saved = (auto_resolved * MANUAL_INVESTIGATION_MINUTES_PER_EXCEPTION) / 60
    total_hours_saved = recon_hours_saved + investigation_hours_saved
    cost_saved = total_hours_saved * COST_PER_HOUR

    # Average AI processing time vs manual
    avg_ai_latency = (await db.execute(
        select(func.avg(Investigation.latency_ms))
    )).scalar() or 0

    # Auto-resolve rate
    auto_resolve_rate = (auto_resolved / max(total_exceptions, 1)) * 100

    return {
        "total_records_processed": total_records,
        "total_exceptions": total_exceptions,
        "auto_resolved": auto_resolved,
        "auto_resolve_rate": round(auto_resolve_rate, 1),
        "time_savings": {
            "reconciliation_hours": round(recon_hours_saved, 1),
            "investigation_hours": round(investigation_hours_saved, 1),
            "total_hours_saved": round(total_hours_saved, 1),
        },
        "cost_savings": {
            "hourly_rate": COST_PER_HOUR,
            "total_saved_rupees": round(cost_saved, 2),
        },
        "accuracy": {
            "avg_ai_latency_ms": round(avg_ai_latency, 1) if avg_ai_latency else None,
            "manual_time_per_exception_min": MANUAL_INVESTIGATION_MINUTES_PER_EXCEPTION,
            "speedup_factor": round((MANUAL_INVESTIGATION_MINUTES_PER_EXCEPTION * 60 * 1000) / max(avg_ai_latency, 1), 1) if avg_ai_latency else None,
        },
        "amount_at_risk_resolved_paise": amount_saved,
        "amount_at_risk_resolved_rupees": round(amount_saved / 100, 2),
    }
