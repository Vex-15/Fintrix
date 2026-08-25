"""
Audit trail utility — append-only logging for every state change.
"""

from sqlalchemy.ext.asyncio import AsyncSession
from app.models import AuditLog


async def log_audit(
    db: AsyncSession,
    entity_type: str,
    entity_id: str,
    action: str,
    actor: str = "system",
    old_state: dict | None = None,
    new_state: dict | None = None,
    metadata: dict | None = None,
):
    """Write an immutable audit log entry. Never raises — logs errors silently."""
    try:
        entry = AuditLog(
            entity_type=entity_type,
            entity_id=str(entity_id),
            action=action,
            actor=actor,
            old_state=old_state,
            new_state=new_state,
            metadata_=metadata or {},
        )
        db.add(entry)
        await db.flush()
    except Exception:
        # Audit logging must never crash the main flow
        pass
