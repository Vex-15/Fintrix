"""
Scheduler service — APScheduler integration for automated reconciliation runs and Razorpay data sync.
"""

import asyncio
from datetime import datetime, timezone
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.config import settings
from app.database import async_session

# Global scheduler instance
scheduler: Optional[AsyncIOScheduler] = None


async def _run_scheduled_reconciliation():
    """Execute a scheduled reconciliation run."""
    from app.services.reconciliation_engine import run_reconciliation
    from app.services.ai_investigator import investigate_all_exceptions
    from app.utils.audit import log_audit

    async with async_session() as db:
        try:
            run = await run_reconciliation(db, trigger_type="scheduled")
            await investigate_all_exceptions(db, run.id)
            await db.commit()

            await log_audit(
                db, "scheduler", "reconciliation",
                action="scheduled_run_completed",
                actor="system",
                new_state={
                    "run_id": run.id,
                    "matched": run.matched,
                    "exceptions": run.exceptions_count,
                },
            )
            await db.commit()
            print(f"[SCHEDULER] Reconciliation run #{run.id} completed: {run.matched} matched, {run.exceptions_count} exceptions")
        except Exception as e:
            await db.rollback()
            print(f"[SCHEDULER] Reconciliation failed: {e}")


async def _run_razorpay_sync():
    """Execute a scheduled Razorpay data sync."""
    from app.services.razorpay import sync_payments, sync_settlements

    async with async_session() as db:
        try:
            payments_result = await sync_payments(db)
            settlements_result = await sync_settlements(db)
            await db.commit()

            p_synced = payments_result.get("synced", 0)
            s_synced = settlements_result.get("synced", 0)

            if p_synced > 0 or s_synced > 0:
                print(f"[SCHEDULER] Razorpay sync: {p_synced} payments, {s_synced} settlements")
        except Exception as e:
            await db.rollback()
            print(f"[SCHEDULER] Razorpay sync failed: {e}")


def init_scheduler():
    """Initialize and start the APScheduler with configured jobs."""
    global scheduler

    if scheduler is not None:
        return scheduler

    scheduler = AsyncIOScheduler()

    # Reconciliation job (default: every 6 hours)
    try:
        cron_parts = settings.scheduler_reconciliation_cron.split()
        if len(cron_parts) == 5:
            scheduler.add_job(
                _run_scheduled_reconciliation,
                CronTrigger(
                    minute=cron_parts[0],
                    hour=cron_parts[1],
                    day=cron_parts[2],
                    month=cron_parts[3],
                    day_of_week=cron_parts[4],
                ),
                id="reconciliation_cron",
                name="Scheduled Reconciliation",
                replace_existing=True,
            )
            print(f"[SCHEDULER] Reconciliation cron: {settings.scheduler_reconciliation_cron}")
    except Exception as e:
        print(f"[SCHEDULER] Failed to setup reconciliation cron: {e}")

    # Razorpay sync job (default: every 15 minutes)
    if settings.razorpay_key_id:
        scheduler.add_job(
            _run_razorpay_sync,
            IntervalTrigger(minutes=settings.scheduler_razorpay_sync_minutes),
            id="razorpay_sync",
            name="Razorpay Data Sync",
            replace_existing=True,
        )
        print(f"[SCHEDULER] Razorpay sync: every {settings.scheduler_razorpay_sync_minutes} minutes")

    scheduler.start()
    print("[SCHEDULER] Started")

    return scheduler


def stop_scheduler():
    """Gracefully shut down the scheduler."""
    global scheduler
    if scheduler:
        scheduler.shutdown(wait=False)
        scheduler = None
        print("[SCHEDULER] Stopped")


def get_scheduler_status() -> dict:
    """Get current scheduler status and job information."""
    if not scheduler:
        return {"status": "stopped", "jobs": []}

    jobs = []
    for job in scheduler.get_jobs():
        next_run = job.next_run_time
        jobs.append({
            "id": job.id,
            "name": job.name,
            "next_run": next_run.isoformat() if next_run else None,
            "trigger": str(job.trigger),
        })

    return {
        "status": "running" if scheduler.running else "paused",
        "jobs": jobs,
    }
