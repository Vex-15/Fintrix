"""
Deterministic Reconciliation Engine.

Implements the 6-step reconciliation pipeline:
  Step 1: Settlement unpacking (aggregate match)
  Step 2: Bank statement matching (UTR join + Ensemble scoring)
  Step 3: Orphan detection (missing settlement / bank entry)
  Step 4: Duplicate detection
  Step 5: Fee/tax validation
  Step 6: Timing analysis

Enhanced with:
  - 5-strategy ensemble matching in Step 2
  - Match score tracking
  - Fuzzy matching fallback for unmatched settlements
"""

import time
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, text

from app.models import (
    Transaction, Settlement, BankStatement,
    ReconciliationRun, ReconciliationResult, Exception_,
)
from app.utils.audit import log_audit
from app.config import settings
from app.services.advanced_matching import (
    match_settlement_to_bank, find_best_matches,
    AUTO_MATCH_THRESHOLD, SUGGEST_MATCH_THRESHOLD,
)

# Fee validation constants
FEE_TOLERANCE_PAISE = 100  # Allow ±₹1 tolerance for rounding


async def compute_priority(db: AsyncSession, amount_at_risk: int, exc_type: str, merchant_id: str | None = None) -> tuple[str, str]:
    """
    Deterministic severity based on amount, with priority rationale based on DB history.
    Returns (severity, rationale).
    """
    if amount_at_risk < 10000:
        severity = "low"
    elif amount_at_risk < 1000000:
        severity = "medium"
    elif amount_at_risk < 10000000:
        severity = "high"
    else:
        severity = "critical"

    query = select(func.count(Exception_.id)).where(Exception_.type == exc_type, Exception_.status == "detected")
    if merchant_id:
        query = query.where(Exception_.merchant_id == merchant_id)
        
    recent_count = (await db.execute(query)).scalar() or 0
    
    rationale = f"Base severity '{severity}' due to amount at risk (₹{amount_at_risk/100:,.2f}). "
    if recent_count > 5:
        rationale += f"Elevated priority: {recent_count} recent unresolved exceptions of type '{exc_type}' detected."
        if severity == "low": severity = "medium"
        elif severity == "medium": severity = "high"
    else:
        rationale += "No significant recurring pattern detected."
        
    return severity, rationale


async def run_reconciliation(db: AsyncSession, trigger_type: str = "manual", merchant_id: str | None = None) -> ReconciliationRun:
    """
    Execute a full reconciliation run.

    Returns a ReconciliationRun with populated metrics.
    """
    start_time = time.time()

    # Create the run record
    run = ReconciliationRun(
        trigger_type=trigger_type,
        status="running",
        merchant_id=merchant_id,
    )
    db.add(run)
    await db.flush()

    await log_audit(db, "reconciliation_run", str(run.id), "started", "system",
                    new_state={"trigger_type": trigger_type})

    # Load all data (scoped by merchant if provided)
    txn_query = select(Transaction)
    setl_query = select(Settlement)
    bank_query = select(BankStatement)

    if merchant_id:
        txn_query = txn_query.where(Transaction.merchant_id == merchant_id)
        setl_query = setl_query.where(Settlement.merchant_id == merchant_id)
        bank_query = bank_query.where(BankStatement.merchant_id == merchant_id)

    txns = (await db.execute(txn_query)).scalars().all()
    settlements = (await db.execute(setl_query)).scalars().all()
    bank_stmts = (await db.execute(bank_query)).scalars().all()

    # Index for fast lookups
    txns_by_id = {t.id: t for t in txns}
    setl_by_id = {s.id: s for s in settlements}
    bank_by_ref = {b.reference: b for b in bank_stmts if b.reference}

    # Group transactions by settlement
    txns_by_settlement: dict[str, list[Transaction]] = {}
    for txn in txns:
        if txn.settlement_id:
            txns_by_settlement.setdefault(txn.settlement_id, []).append(txn)

    # Track which entities have been matched
    matched_txn_ids: set[str] = set()
    matched_setl_ids: set[str] = set()
    matched_bank_ids: set[int] = set()
    exceptions_created: list[Exception_] = []
    results_created: list[ReconciliationResult] = []

    # -----------------------------------------------------------------------
    # STEP 1: Settlement Unpacking (Aggregate Match)
    # For each settlement, verify that sum of its transactions reconciles.
    # -----------------------------------------------------------------------
    for setl in settlements:
        # Find all transactions assigned to this settlement
        setl_txns = [t for t in txns if t.settlement_id == setl.id]
        payments = [t for t in setl_txns if t.type == "payment"]
        refunds = [t for t in setl_txns if t.type == "refund"]

        if not payments:
            continue

        # Calculate expected settlement amount
        total_gross = sum(t.amount for t in payments)
        total_fees = sum(t.fee for t in payments)
        total_tax = sum(t.tax for t in payments)
        total_refunds = sum(t.amount for t in refunds)
        expected_net = total_gross - total_fees - total_tax - total_refunds

        difference = abs(setl.amount - expected_net)

        if difference == 0:
            # Perfect aggregate match
            match_status = "matched"
            match_type = "aggregate"
            for t in setl_txns:
                matched_txn_ids.add(t.id)
            matched_setl_ids.add(setl.id)
        else:
            # Amount mismatch
            match_status = "mismatched"
            match_type = "aggregate"

            sev, rat = await compute_priority(db, difference, "amount_mismatch", merchant_id)
            exc = Exception_(
                run_id=run.id,
                type="amount_mismatch",
                severity=sev,

                status="detected",
                amount_at_risk=difference,
                merchant_id=merchant_id,
                context={
                    "settlement_id": setl.id,
                    "expected_net": expected_net,
                    "actual_net": setl.amount,
                    "difference": setl.amount - expected_net,
                    "total_gross": total_gross,
                    "total_fees": total_fees,
                    "total_tax": total_tax,
                    "total_refunds": total_refunds,
                    "payment_ids": [t.id for t in payments],
                    "refund_ids": [t.id for t in refunds],
                    "priority_rationale": rat,
                },
            )
            db.add(exc)
            exceptions_created.append(exc)
            await log_audit(db, "exception", str(setl.id), "detected", "system",
                            new_state={"type": "amount_mismatch", "difference": difference})

        # Record the aggregate result
        result = ReconciliationResult(
            run_id=run.id,
            settlement_id=setl.id,
            match_type=match_type,
            match_status=match_status,
            expected_amount=expected_net,
            actual_amount=setl.amount,
            difference=setl.amount - expected_net,
            match_details={
                "step": "settlement_unpacking",
                "payments": len(payments),
                "refunds": len(refunds),
            },
        )
        db.add(result)
        results_created.append(result)

    # -----------------------------------------------------------------------
    # STEP 2: Ensemble Matching (Bank Statements)
    # -----------------------------------------------------------------------
    unmatched_settlements = settlements
    unmatched_bank_stmts = [b for b in bank_stmts if b.id not in matched_bank_ids]

    # Run ensemble matching
    ensemble_results = find_best_matches(
        settlements, unmatched_bank_stmts, txns_by_settlement
    )

    for match in ensemble_results:
        setl = setl_by_id.get(match.settlement_id)
        if not setl:
            continue

        bank_entry = None
        for b in bank_stmts:
            if b.id == match.bank_stmt_id:
                bank_entry = b
                break

        if not bank_entry:
            continue

        matched_bank_ids.add(bank_entry.id)
        difference = abs(bank_entry.credit - setl.amount)

        if match.match_type == "auto_match":
            # High confidence auto-match
            matched_setl_ids.add(setl.id)
            match_status = "matched"
        elif match.match_type == "suggested":
            # Moderate confidence — match but flag
            matched_setl_ids.add(setl.id)
            match_status = "matched" if difference == 0 else "mismatched"
        else:
            # Low confidence — flag for review
            match_status = "mismatched"

        if difference > 0 and match.final_score < AUTO_MATCH_THRESHOLD:
            exc_t = "amount_mismatch" if difference > 10 else "rounding_difference"
            sev, rat = await compute_priority(db, difference, exc_t, merchant_id) if difference > 10 else ("low", "Rounding difference.")
            exc = Exception_(
                run_id=run.id,
                type=exc_t,
                severity=sev,
                status="detected",
                amount_at_risk=difference,
                merchant_id=merchant_id,
                context={
                    "settlement_id": setl.id,
                    "settlement_amount": setl.amount,
                    "bank_credit": bank_entry.credit,
                    "difference": bank_entry.credit - setl.amount,
                    "utr": setl.utr,
                    "source": "ensemble_matching",
                    "ensemble_score": match.final_score,
                    "strategy_scores": match.details.get("strategy_scores", {}),
                    "priority_rationale": rat,
                },
            )
            db.add(exc)
            exceptions_created.append(exc)
            
            # Remove transactions from matched_txn_ids since settlement is mismatched
            for t in setl_txns:
                if t.id in matched_txn_ids:
                    matched_txn_ids.remove(t.id)

        result = ReconciliationResult(
            run_id=run.id,
            settlement_id=setl.id,
            bank_stmt_id=bank_entry.id,
            match_type="ensemble",
            match_status=match_status,
            match_score=match.final_score,
            expected_amount=setl.amount,
            actual_amount=bank_entry.credit,
            difference=bank_entry.credit - setl.amount,
            match_details={
                "step": "ensemble_matching",
                "ensemble_type": match.match_type,
                "strategy_scores": match.details.get("strategy_scores", {}),
                "weighted_scores": match.details.get("weighted_scores", {}),
                "explanation": match.explanation,
                "utr": setl.utr,
            },
        )
        db.add(result)
        results_created.append(result)

    # Flag settlements with no bank entry match at all
    matched_setl_in_bank = {m.settlement_id for m in ensemble_results}
    for setl in settlements:
        if setl.utr and setl.id not in matched_setl_in_bank:
            sev, rat = await compute_priority(db, setl.amount, "missing_bank_entry", merchant_id)
            exc = Exception_(
                run_id=run.id,
                type="missing_bank_entry",
                severity=sev,
                status="detected",
                amount_at_risk=setl.amount,
                merchant_id=merchant_id,
                context={
                    "settlement_id": setl.id,
                    "settlement_amount": setl.amount,
                    "utr": setl.utr,
                    "settlement_status": setl.status,
                    "priority_rationale": rat,
                },
            )
            db.add(exc)
            exceptions_created.append(exc)
            await log_audit(db, "exception", setl.id, "detected", "system",
                            new_state={"type": "missing_bank_entry", "utr": setl.utr})
                            
            # Remove transactions from matched_txn_ids since settlement has no bank entry
            for t in txns:
                if t.settlement_id == setl.id and t.id in matched_txn_ids:
                    matched_txn_ids.remove(t.id)

    # -----------------------------------------------------------------------
    # STEP 3: Orphan Detection
    # Find captured payments with no settlement, and unmatched bank entries.
    # -----------------------------------------------------------------------
    for txn in txns:
        if txn.id in matched_txn_ids:
            continue
        if txn.type == "payment" and txn.status == "captured" and not txn.settlement_id:
            sev, rat = await compute_priority(db, txn.amount, "missing_settlement", merchant_id)
            exc = Exception_(
                run_id=run.id,
                type="missing_settlement",
                severity=sev,
                status="detected",
                amount_at_risk=txn.amount,
                merchant_id=merchant_id,
                context={
                    "transaction_id": txn.id,
                    "amount": txn.amount,
                    "status": txn.status,
                    "order_id": txn.order_id,
                    "method": txn.method,
                    "captured_at": txn.captured_at.isoformat() if txn.captured_at else None,
                    "priority_rationale": rat,
                },
            )
            db.add(exc)
            exceptions_created.append(exc)
            await log_audit(db, "exception", txn.id, "detected", "system",
                            new_state={"type": "missing_settlement"})

        elif txn.type == "adjustment" and not txn.settlement_id:
            sev, rat = await compute_priority(db, txn.amount, "unexpected_adjustment", merchant_id)
            exc = Exception_(
                run_id=run.id,
                type="unexpected_adjustment",
                severity=sev,
                status="detected",
                amount_at_risk=txn.amount,
                merchant_id=merchant_id,
                context={
                    "transaction_id": txn.id,
                    "amount": txn.amount,
                    "description": txn.description,
                    "created_at": txn.created_at.isoformat() if txn.created_at else None,
                    "priority_rationale": rat,
                },
            )
            db.add(exc)
            exceptions_created.append(exc)
            await log_audit(db, "exception", txn.id, "detected", "system",
                            new_state={"type": "unexpected_adjustment"})

    # -----------------------------------------------------------------------
    # STEP 4: Duplicate Detection
    # Find payments with same (amount, method, order_id) within 30 min window.
    # -----------------------------------------------------------------------
    payments_only = [t for t in txns if t.type == "payment" and t.status == "captured"]
    seen_groups: dict[str, list[Transaction]] = {}

    for txn in payments_only:
        key = f"{txn.amount}|{txn.method}|{txn.order_id}"
        if key not in seen_groups:
            seen_groups[key] = []
        seen_groups[key].append(txn)

    for key, group in seen_groups.items():
        if len(group) < 2:
            continue

        # Sort by created_at
        group.sort(key=lambda t: t.created_at or datetime.min)

        for i in range(1, len(group)):
            time_diff = (group[i].created_at - group[i - 1].created_at).total_seconds()
            if abs(time_diff) <= 1800:  # within 30 minutes
                sev, rat = await compute_priority(db, group[i].amount, "duplicate_suspected", merchant_id)
                exc = Exception_(
                    run_id=run.id,
                    type="duplicate_suspected",
                    severity=sev,
                    status="detected",
                    amount_at_risk=group[i].amount,
                    merchant_id=merchant_id,
                    context={
                        "original_id": group[i - 1].id,
                        "duplicate_id": group[i].id,
                        "amount": group[i].amount,
                        "method": group[i].method,
                        "order_id": group[i].order_id,
                        "time_diff_seconds": time_diff,
                        "priority_rationale": rat,
                    },
                )
                db.add(exc)
                exceptions_created.append(exc)
                await log_audit(db, "exception", group[i].id, "detected", "system",
                                new_state={"type": "duplicate_suspected",
                                           "original": group[i - 1].id})

    # -----------------------------------------------------------------------
    # STEP 5: Fee/Tax Validation
    # Verify that recorded fees match expected MDR calculation.
    # -----------------------------------------------------------------------
    for txn in txns:
        if txn.type != "payment" or txn.status != "captured":
            continue

        expected_fee = round(txn.amount * settings.expected_mdr_rate)
        expected_tax = round(expected_fee * settings.expected_gst_rate)
        fee_diff = abs(txn.fee - expected_fee)

        if fee_diff > FEE_TOLERANCE_PAISE:
            sev, rat = await compute_priority(db, fee_diff, "fee_discrepancy", merchant_id)
            exc = Exception_(
                run_id=run.id,
                type="fee_discrepancy",
                severity=sev,
                status="detected",
                amount_at_risk=fee_diff,
                merchant_id=merchant_id,
                context={
                    "transaction_id": txn.id,
                    "amount": txn.amount,
                    "recorded_fee": txn.fee,
                    "expected_fee": expected_fee,
                    "fee_difference": txn.fee - expected_fee,
                    "recorded_tax": txn.tax,
                    "expected_tax": expected_tax,
                    "method": txn.method,
                    "priority_rationale": rat,
                },
            )
            db.add(exc)
            exceptions_created.append(exc)
            await log_audit(db, "exception", txn.id, "detected", "system",
                            new_state={"type": "fee_discrepancy",
                                       "recorded": txn.fee, "expected": expected_fee})

    # -----------------------------------------------------------------------
    # STEP 6: Timing Analysis
    # Flag refunds created after their settlement was created.
    # -----------------------------------------------------------------------
    for txn in txns:
        if txn.type != "refund" or not txn.settlement_id:
            continue

        setl = setl_by_id.get(txn.settlement_id)
        if not setl or not setl.created_at or not txn.created_at:
            continue

        if txn.created_at > setl.created_at:
            time_diff = (txn.created_at - setl.created_at).total_seconds()
            sev, rat = await compute_priority(db, txn.amount, "timing_mismatch", merchant_id)
            exc = Exception_(
                run_id=run.id,
                type="timing_mismatch",
                severity=sev,
                status="detected",
                amount_at_risk=txn.amount,
                merchant_id=merchant_id,
                context={
                    "transaction_id": txn.id,
                    "refund_amount": txn.amount,
                    "settlement_id": setl.id,
                    "refund_created": txn.created_at.isoformat(),
                    "settlement_created": setl.created_at.isoformat(),
                    "delay_seconds": time_diff,
                    "order_id": txn.order_id,
                    "description": txn.description,
                    "priority_rationale": rat,
                },
            )
            db.add(exc)
            exceptions_created.append(exc)
            await log_audit(db, "exception", txn.id, "detected", "system",
                            new_state={"type": "timing_mismatch",
                                       "delay_seconds": time_diff})

    # -----------------------------------------------------------------------
    # Finalize the run
    # -----------------------------------------------------------------------
    elapsed_ms = int((time.time() - start_time) * 1000)

    # Count results
    total_txns = len(txns)
    n_matched = len(matched_txn_ids)
    n_exceptions = len(exceptions_created)
    n_unmatched = total_txns - n_matched - n_exceptions

    run.status = "completed"
    run.completed_at = datetime.utcnow()
    run.total_records = total_txns
    run.matched = n_matched
    run.mismatched = sum(1 for e in exceptions_created if e.type == "amount_mismatch")
    run.unmatched = max(0, n_unmatched)
    run.exceptions_count = n_exceptions
    run.duration_ms = elapsed_ms
    run.summary = {
        "settlements_checked": len(settlements),
        "bank_statements_checked": len(bank_stmts),
        "ensemble_matches": len(ensemble_results),
        "exception_types": {},
    }

    # Count exception types
    for exc in exceptions_created:
        t = exc.type
        run.summary["exception_types"][t] = run.summary["exception_types"].get(t, 0) + 1

    await db.flush()

    await log_audit(db, "reconciliation_run", str(run.id), "completed", "system",
                    new_state={
                        "total_records": run.total_records,
                        "matched": run.matched,
                        "exceptions": run.exceptions_count,
                        "duration_ms": elapsed_ms,
                        "ensemble_matches": len(ensemble_results),
                    })

    return run
