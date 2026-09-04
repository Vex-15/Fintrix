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
            func.sum(case((Exception_.status == "resolved", 1), else_=0)).label(
                "resolved"),
            func.sum(case((Exception_.status == "escalated", 1), else_=0)).label(
                "escalated"),
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
    investigation_hours_saved = (
        auto_resolved * MANUAL_INVESTIGATION_MINUTES_PER_EXCEPTION) / 60
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


# ---------------------------------------------------------------------------
# Forward Cash Forecaster
# ---------------------------------------------------------------------------

@router.get("/forecast")
async def get_cash_forecast(
    days: int = Query(default=14, ge=1, le=30),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Predict expected settlement inflows for the next 7–14 days.
    Uses historical settlement patterns, day-of-week seasonality,
    and pending captured-but-unsettled transactions.
    """
    from app.services.forecaster import forecast_inflows
    return await forecast_inflows(db, days_ahead=days)


# ---------------------------------------------------------------------------
# Tax-Line Matcher / GST Reconciliation
# ---------------------------------------------------------------------------

@router.get("/tax-reconciliation")
async def get_tax_reconciliation(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Compare expected vs recorded GST/fees per transaction.
    Generates a full tax reconciliation report with per-transaction
    and per-method breakdowns.
    """
    from app.services.tax_matcher import generate_tax_reconciliation
    return await generate_tax_reconciliation(db)


# ---------------------------------------------------------------------------
# Confidence Calibration Report
# ---------------------------------------------------------------------------

@router.get("/confidence-calibration")
async def get_confidence_calibration(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Show whether confidence predictions are well-calibrated.
    e.g., do 90% confidence predictions actually resolve correctly ~90% of the time?

    Returns calibration curve data and ECE (Expected Calibration Error).
    """
    # Fetch all investigations
    result = await db.execute(
        select(Investigation, Exception_)
        .join(Exception_, Investigation.exception_id == Exception_.id)
    )
    rows = result.all()

    if not rows:
        return {
            "calibration_curve": [],
            "ece": 0.0,
            "total_investigations": 0,
            "note": "No investigations found to calibrate.",
        }

    # Define calibration bands
    bands = [
        (0.0, 0.2), (0.2, 0.4), (0.4, 0.6),
        (0.6, 0.8), (0.8, 1.0),
    ]

    calibration_curve = []
    total_weighted_error = 0.0
    calibrated_count = 0

    for low, high in bands:
        band_items = [
            (inv, exc) for inv, exc in rows
            if low <= inv.confidence < high or (high == 1.0 and inv.confidence == 1.0 and low <= inv.confidence)
        ]

        if not band_items:
            calibration_curve.append({
                "confidence_range": f"{low:.1f}-{high:.1f}",
                "predicted_confidence": round((low + high) / 2, 2),
                "actual_accuracy": None,
                "count": 0,
            })
            continue

        # Determine "correct" outcomes:
        # - auto-resolved with no negative feedback = correct
        # - user_feedback == "helpful" = correct
        # - user_feedback == "unhelpful" = incorrect
        # - manually overridden (resolution_type == "manual") = incorrect
        correct = 0
        for inv, exc in band_items:
            if inv.user_feedback == "helpful":
                correct += 1
            elif inv.user_feedback == "unhelpful":
                pass  # incorrect
            elif inv.resolution_type == "auto" and exc.status == "resolved":
                correct += 1  # auto-resolved, no negative feedback
            elif inv.resolution_type == "manual":
                pass  # overridden — counts as incorrect
            else:
                # escalated — we don't know, treat as neutral (exclude)
                continue

            calibrated_count += 1

        count = len(band_items)
        avg_confidence = sum(inv.confidence for inv, _ in band_items) / count
        actual_accuracy = correct / count if count > 0 else 0

        calibration_curve.append({
            "confidence_range": f"{low:.1f}-{high:.1f}",
            "predicted_confidence": round(avg_confidence, 3),
            "actual_accuracy": round(actual_accuracy, 3),
            "count": count,
            "correct": correct,
        })

        # ECE contribution
        total_weighted_error += count * abs(avg_confidence - actual_accuracy)

    ece = round(total_weighted_error / max(calibrated_count, 1), 4)

    return {
        "calibration_curve": calibration_curve,
        "ece": ece,
        "ece_interpretation": (
            "excellent" if ece < 0.05
            else "good" if ece < 0.10
            else "fair" if ece < 0.20
            else "poor"
        ),
        "total_investigations": len(rows),
        "calibrated_investigations": calibrated_count,
    }


# ---------------------------------------------------------------------------
# Threshold Sensitivity View
# ---------------------------------------------------------------------------

@router.get("/threshold-sensitivity")
async def get_threshold_sensitivity(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Show the trade-off between auto-resolution rate and error rate
    at different confidence thresholds.

    Sweeps thresholds from 0.50 to 1.00 in 0.05 increments.
    """
    from app.config import settings

    # Fetch all investigations with exception data
    result = await db.execute(
        select(Investigation, Exception_)
        .join(Exception_, Investigation.exception_id == Exception_.id)
    )
    rows = result.all()

    if not rows:
        return {
            "sensitivity_curve": [],
            "current_threshold": settings.auto_resolve_confidence_threshold,
            "total_investigations": 0,
        }

    # Determine which investigations are "errors"
    # Error = user said "unhelpful" OR was manually overridden
    error_ids = set()
    for inv, exc in rows:
        if inv.user_feedback == "unhelpful":
            error_ids.add(inv.id)
        elif inv.resolution_type == "manual" and inv.recommended_action == "auto_resolve":
            error_ids.add(inv.id)

    sensitivity_curve = []
    total = len(rows)

    thresholds = [round(0.50 + i * 0.05, 2) for i in range(11)]  # 0.50 to 1.00

    for threshold in thresholds:
        # How many would be auto-resolved at this threshold?
        would_auto = [
            (inv, exc) for inv, exc in rows
            if inv.confidence >= threshold
            and inv.recommended_action == "auto_resolve"
            and exc.amount_at_risk <= settings.auto_resolve_max_amount_paise
        ]

        auto_count = len(would_auto)
        auto_rate = auto_count / total if total > 0 else 0

        # How many of those would be errors?
        errors_at_threshold = sum(
            1 for inv, _ in would_auto if inv.id in error_ids)
        error_rate = errors_at_threshold / \
            max(auto_count, 1) if auto_count > 0 else 0

        escalation_rate = 1.0 - auto_rate

        sensitivity_curve.append({
            "threshold": threshold,
            "auto_resolve_count": auto_count,
            "auto_resolve_rate": round(auto_rate, 4),
            "estimated_error_count": errors_at_threshold,
            "estimated_error_rate": round(error_rate, 4),
            "escalation_rate": round(escalation_rate, 4),
            "is_current": threshold == settings.auto_resolve_confidence_threshold,
        })

    return {
        "sensitivity_curve": sensitivity_curve,
        "current_threshold": settings.auto_resolve_confidence_threshold,
        "current_max_amount_paise": settings.auto_resolve_max_amount_paise,
        "total_investigations": total,
        "total_known_errors": len(error_ids),
    }


# ---------------------------------------------------------------------------
# Determinism Test (Runtime Endpoint)
# ---------------------------------------------------------------------------

@router.post("/determinism-test")
async def run_determinism_test(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Prove that identical input batches always produce identical reconciliation results.
    Creates temporary in-memory databases, loads synthetic data, runs reconciliation
    twice, and compares outputs.
    """
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession as AS
    from app.models import Base, Transaction as Txn, Settlement as Setl, BankStatement as BS
    from app.utils.synthetic_data import generate_dataset
    from app.services.reconciliation_engine import run_reconciliation as run_recon

    async def _run_once() -> dict:
        engine = create_async_engine(
            "sqlite+aiosqlite:///:memory:", echo=False)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        session_maker = async_sessionmaker(
            engine, class_=AS, expire_on_commit=False)
        async with session_maker() as session:
            data = generate_dataset()

            for s in data["settlements"]:
                session.add(Setl(**s))
            await session.flush()

            for t in data["transactions"]:
                session.add(Txn(**{**t, "source": "csv_batch"}))
            await session.flush()

            for b in data["bank_statements"]:
                session.add(BS(**b))
            await session.flush()
            await session.commit()

            run = await run_recon(session, trigger_type="determinism_test")
            await session.commit()

            exc_result = await session.execute(
                select(Exception_).where(Exception_.run_id == run.id)
            )
            exceptions = exc_result.scalars().all()
            exc_details = sorted(
                [{"type": e.type, "amount": e.amount_at_risk}
                    for e in exceptions],
                key=lambda x: (x["type"], x["amount"]),
            )

        await engine.dispose()

        return {
            "total_records": run.total_records,
            "matched": run.matched,
            "mismatched": run.mismatched,
            "unmatched": run.unmatched,
            "exceptions_count": run.exceptions_count,
            "exception_types": run.summary.get("exception_types", {}),
            "exception_details": exc_details,
        }

    run1 = await _run_once()
    run2 = await _run_once()

    diffs = []
    for key in ["total_records", "matched", "mismatched", "unmatched", "exceptions_count"]:
        if run1[key] != run2[key]:
            diffs.append({"field": key, "run1": run1[key], "run2": run2[key]})

    if run1["exception_types"] != run2["exception_types"]:
        diffs.append({"field": "exception_types",
                     "run1": run1["exception_types"], "run2": run2["exception_types"]})

    if run1["exception_details"] != run2["exception_details"]:
        diffs.append({"field": "exception_details",
                     "note": "Exception details differ"})

    return {
        "is_deterministic": len(diffs) == 0,
        "runs_compared": 2,
        "run_1": {k: v for k, v in run1.items() if k != "exception_details"},
        "run_2": {k: v for k, v in run2.items() if k != "exception_details"},
        "diffs": diffs,
    }
