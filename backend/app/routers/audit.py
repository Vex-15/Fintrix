"""
Audit API — query the immutable audit trail.

Enhanced with:
  - Entity-specific timeline endpoint
  - Before/after diff support
  - Actor-filtered queries
"""

from fastapi import APIRouter, Depends, Query, Path
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, asc

from app.database import get_db
from app.models import AuditLog
from app.schemas import AuditLogOut

router = APIRouter()


@router.get("/", response_model=list[AuditLogOut])
async def list_audit_logs(
    entity_type: str | None = None,
    entity_id: str | None = None,
    action: str | None = None,
    actor: str | None = None,
    limit: int = Query(default=100, le=500),
    db: AsyncSession = Depends(get_db),
):
    """Query audit trail with optional filters. Returns most recent first."""
    query = select(AuditLog).order_by(desc(AuditLog.timestamp)).limit(limit)

    if entity_type:
        query = query.where(AuditLog.entity_type == entity_type)
    if entity_id:
        query = query.where(AuditLog.entity_id == entity_id)
    if action:
        query = query.where(AuditLog.action == action)
    if actor:
        query = query.where(AuditLog.actor == actor)

    result = await db.execute(query)
    return result.scalars().all()


@router.get("/timeline/{entity_type}/{entity_id}")
async def get_entity_timeline(
    entity_type: str = Path(...),
    entity_id: str = Path(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Get the full chronological history of a specific entity.
    Returns all audit log entries ordered by time, with before/after diffs.
    """
    result = await db.execute(
        select(AuditLog)
        .where(
            AuditLog.entity_type == entity_type,
            AuditLog.entity_id == entity_id,
        )
        .order_by(asc(AuditLog.timestamp))
    )
    logs = result.scalars().all()

    timeline = []
    for log in logs:
        entry = {
            "id": log.id,
            "timestamp": log.timestamp.isoformat() if log.timestamp else None,
            "action": log.action,
            "actor": log.actor,
            "old_state": log.old_state,
            "new_state": log.new_state,
            "metadata": log.metadata_,
            "diff": None,
        }

        # Compute diff between old and new state
        if log.old_state and log.new_state:
            diff = {}
            all_keys = set(list(log.old_state.keys()) + list(log.new_state.keys()))
            for key in all_keys:
                old_val = log.old_state.get(key)
                new_val = log.new_state.get(key)
                if old_val != new_val:
                    diff[key] = {"before": old_val, "after": new_val}
            entry["diff"] = diff if diff else None

        timeline.append(entry)

    return {
        "entity_type": entity_type,
        "entity_id": entity_id,
        "total_entries": len(timeline),
        "timeline": timeline,
    }


@router.get("/stats")
async def audit_stats(
    db: AsyncSession = Depends(get_db),
):
    """Get audit trail statistics — counts by actor, action, and entity type."""
    from sqlalchemy import func

    by_actor = dict(
        (await db.execute(
            select(AuditLog.actor, func.count(AuditLog.id))
            .group_by(AuditLog.actor)
        )).all()
    )
    by_action = dict(
        (await db.execute(
            select(AuditLog.action, func.count(AuditLog.id))
            .group_by(AuditLog.action)
        )).all()
    )
    by_entity = dict(
        (await db.execute(
            select(AuditLog.entity_type, func.count(AuditLog.id))
            .group_by(AuditLog.entity_type)
        )).all()
    )

    total = sum(by_actor.values())

    return {
        "total": total,
        "by_actor": by_actor,
        "by_action": by_action,
        "by_entity_type": by_entity,
    }
