"""
Export API — CSV export endpoints for transactions, exceptions, reconciliation results, and audit trail.
"""

import csv
import io
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from app.database import get_db
from app.models import (
    Transaction, Settlement, BankStatement,
    Exception_, ReconciliationResult, ReconciliationRun,
    AuditLog, User,
)
from app.services.auth import get_current_user
from app.services.rbac import require_permission

router = APIRouter()


def _csv_response(data: list[dict], filename: str) -> StreamingResponse:
    """Create a StreamingResponse with CSV data."""
    if not data:
        output = io.StringIO()
        output.write("No data found\n")
        output.seek(0)
    else:
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=data[0].keys())
        writer.writeheader()
        writer.writerows(data)
        output.seek(0)

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/transactions")
async def export_transactions(
    status: str | None = None,
    type: str | None = None,
    current_user: User = Depends(require_permission("export_data")),
    db: AsyncSession = Depends(get_db),
):
    """Export transactions as CSV."""
    query = select(Transaction).order_by(desc(Transaction.created_at)).limit(10000)
    if status:
        query = query.where(Transaction.status == status)
    if type:
        query = query.where(Transaction.type == type)
    if current_user.merchant_id:
        query = query.where(Transaction.merchant_id == current_user.merchant_id)

    result = await db.execute(query)
    txns = result.scalars().all()

    data = [
        {
            "id": t.id,
            "type": t.type,
            "order_id": t.order_id or "",
            "amount_paise": t.amount,
            "amount_rupees": f"{t.amount / 100:.2f}",
            "currency": t.currency,
            "status": t.status,
            "fee_paise": t.fee,
            "tax_paise": t.tax,
            "settlement_id": t.settlement_id or "",
            "method": t.method or "",
            "description": t.description or "",
            "captured_at": t.captured_at.isoformat() if t.captured_at else "",
            "created_at": t.created_at.isoformat() if t.created_at else "",
            "source": t.source,
        }
        for t in txns
    ]

    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    return _csv_response(data, f"fintrix_transactions_{ts}.csv")


@router.get("/exceptions")
async def export_exceptions(
    status: str | None = None,
    severity: str | None = None,
    current_user: User = Depends(require_permission("export_data")),
    db: AsyncSession = Depends(get_db),
):
    """Export exceptions as CSV."""
    query = select(Exception_).order_by(desc(Exception_.created_at)).limit(10000)
    if status:
        query = query.where(Exception_.status == status)
    if severity:
        query = query.where(Exception_.severity == severity)
    if current_user.merchant_id:
        query = query.where(Exception_.merchant_id == current_user.merchant_id)

    result = await db.execute(query)
    exceptions = result.scalars().all()

    data = [
        {
            "id": e.id,
            "run_id": e.run_id or "",
            "type": e.type,
            "severity": e.severity,
            "status": e.status,
            "amount_at_risk_paise": e.amount_at_risk,
            "amount_at_risk_rupees": f"{e.amount_at_risk / 100:.2f}",
            "created_at": e.created_at.isoformat() if e.created_at else "",
            "resolved_at": e.resolved_at.isoformat() if e.resolved_at else "",
        }
        for e in exceptions
    ]

    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    return _csv_response(data, f"fintrix_exceptions_{ts}.csv")


@router.get("/reconciliation/{run_id}")
async def export_reconciliation_run(
    run_id: int,
    current_user: User = Depends(require_permission("export_data")),
    db: AsyncSession = Depends(get_db),
):
    """Export a full reconciliation run report as CSV."""
    result = await db.execute(
        select(ReconciliationResult).where(ReconciliationResult.run_id == run_id)
    )
    results = result.scalars().all()

    data = [
        {
            "id": r.id,
            "run_id": r.run_id,
            "transaction_id": r.transaction_id or "",
            "settlement_id": r.settlement_id or "",
            "bank_stmt_id": r.bank_stmt_id or "",
            "match_type": r.match_type,
            "match_status": r.match_status,
            "match_score": f"{r.match_score:.4f}" if r.match_score else "",
            "expected_amount_paise": r.expected_amount or 0,
            "actual_amount_paise": r.actual_amount or 0,
            "difference_paise": r.difference,
            "difference_rupees": f"{r.difference / 100:.2f}",
        }
        for r in results
    ]

    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    return _csv_response(data, f"fintrix_reconciliation_run_{run_id}_{ts}.csv")


@router.get("/audit-trail")
async def export_audit_trail(
    entity_type: str | None = None,
    actor: str | None = None,
    limit: int = Query(default=5000, le=10000),
    current_user: User = Depends(require_permission("export_data")),
    db: AsyncSession = Depends(get_db),
):
    """Export audit trail as CSV."""
    query = select(AuditLog).order_by(desc(AuditLog.timestamp)).limit(limit)
    if entity_type:
        query = query.where(AuditLog.entity_type == entity_type)
    if actor:
        query = query.where(AuditLog.actor == actor)

    result = await db.execute(query)
    logs = result.scalars().all()

    data = [
        {
            "id": l.id,
            "timestamp": l.timestamp.isoformat() if l.timestamp else "",
            "entity_type": l.entity_type,
            "entity_id": l.entity_id,
            "action": l.action,
            "actor": l.actor,
        }
        for l in logs
    ]

    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    return _csv_response(data, f"fintrix_audit_trail_{ts}.csv")
