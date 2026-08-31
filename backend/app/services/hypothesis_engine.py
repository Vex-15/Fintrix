"""
Hypothesis Engine — deterministic rule-based root-cause hypothesis generation.

Given an Exception_ and its gathered related data, generates 0–3 candidate
root-cause hypotheses using signature checks modeled on the MatchScore /
weighted-scoring pattern from advanced_matching.py.

Rules:
  1. timing_mismatch   – refund/adjustment created after settlement
  2. fee_change        – recorded fee diverges from plausible MDR rates
  3. missing_refund    – refund amount ≈ discrepancy, not linked
  4. duplicate_charge  – same (amount|method|order) within 30 min window
  5. partial_settlement – on_hold-like status, amount ≈ discrepancy
  6. manual_adjustment – adjustment-type txn, no settlement, amount ≈ discrepancy
  7. rounding          – discrepancy < 100 paise, high txn count

Returns the top-scoring hypothesis, or 'unknown' with confidence 0
if nothing fires.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

from app.config import settings


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class Hypothesis:
    """A single root-cause hypothesis with scored confidence."""
    category: str
    confidence: float          # 0.0 – 1.0
    root_cause: str            # Human-readable description
    evidence: list[str]        # Specific IDs / amounts cited
    recommended_action: str    # auto_resolve | escalate | needs_data
    details: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "category": self.category,
            "confidence": self.confidence,
            "root_cause": self.root_cause,
            "evidence": self.evidence,
            "recommended_action": self.recommended_action,
            "details": self.details,
        }


# ---------------------------------------------------------------------------
# Tolerance helpers (same bands as advanced_matching.py)
# ---------------------------------------------------------------------------

AMOUNT_EXACT_TOLERANCE = 0
AMOUNT_ROUNDING_TOLERANCE = 10      # ±10 paise
AMOUNT_MINOR_TOLERANCE = 100        # ±100 paise (₹1)
AMOUNT_FEE_TOLERANCE = 5000         # ±5000 paise (₹50)

# Plausible historical MDR rates to check against
PLAUSIBLE_MDR_RATES = [0.018, 0.020, 0.022]

# Expected rates (must match reconciliation_engine.py)
EXPECTED_MDR_RATE = 0.02
EXPECTED_GST_RATE = 0.18


def _amount_tolerance_score(difference: int | float) -> float:
    """Score how close a difference is to zero using tolerance bands."""
    diff = abs(difference)
    if diff <= AMOUNT_EXACT_TOLERANCE:
        return 1.0
    elif diff <= AMOUNT_ROUNDING_TOLERANCE:
        return 0.95
    elif diff <= AMOUNT_MINOR_TOLERANCE:
        return 0.85
    elif diff <= AMOUNT_FEE_TOLERANCE:
        # Linear decay from 0.7 to 0.5
        return max(0.5, 0.7 - (diff - AMOUNT_MINOR_TOLERANCE) / AMOUNT_FEE_TOLERANCE * 0.2)
    else:
        # Large difference — decay toward 0
        return max(0.0, 0.4 - diff / 1_000_000)


def _time_proximity_score(
    time_a: datetime | None,
    time_b: datetime | None,
    max_days: int = 7,
) -> float:
    """Score how close two timestamps are (1.0 = same day, decay over max_days)."""
    if not time_a or not time_b:
        return 0.0
    diff_seconds = abs((time_a - time_b).total_seconds())
    diff_days = diff_seconds / 86400
    if diff_days <= 0.5:
        return 1.0
    elif diff_days <= 1:
        return 0.9
    elif diff_days <= 2:
        return 0.7
    elif diff_days <= 3:
        return 0.5
    elif diff_days <= max_days:
        return max(0.1, 0.4 - (diff_days - 3) * 0.1)
    return 0.0


def _determine_action(
    confidence: float,
    amount_at_risk: int,
    category: str,
) -> str:
    """
    Determine recommended action using the EXISTING guardrail logic
    from config.py — do not change these thresholds.
    """
    if amount_at_risk >= settings.always_escalate_amount_paise:
        return "escalate"

    if (
        confidence >= settings.auto_resolve_confidence_threshold
        and amount_at_risk <= settings.auto_resolve_max_amount_paise
        and category in (
            "timing_mismatch", "fee_change", "rounding",
            "manual_adjustment", "duplicate_charge",
        )
    ):
        return "auto_resolve"

    return "escalate"


def _parse_dt(s: str | datetime | None) -> datetime | None:
    """Safely parse an ISO datetime string or return a datetime."""
    if s is None:
        return None
    if isinstance(s, datetime):
        return s
    try:
        return datetime.fromisoformat(str(s))
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Individual rule checks
# ---------------------------------------------------------------------------

def _check_timing_mismatch(
    exc_type: str,
    ctx: dict,
    related: dict,
    discrepancy: int,
) -> Hypothesis | None:
    """
    A refund/adjustment whose amount ≈ discrepancy and created_at falls
    between settlement creation and (if available) bank credit date.
    """
    settlement = related.get("settlement")
    if not settlement:
        return None

    setl_created = _parse_dt(settlement.get("created_at"))
    if not setl_created:
        return None

    # Bank entry date as upper bound (if available)
    bank = related.get("bank_statement")
    bank_date = _parse_dt(bank.get("entry_date")) if bank else None

    best_score = 0.0
    best_evidence = []
    best_txn_id = None

    for txn in related.get("transactions", []):
        txn_type = txn.get("type", "")
        if txn_type not in ("refund", "adjustment"):
            continue

        txn_amount = txn.get("amount", 0)
        txn_created = _parse_dt(txn.get("created_at"))
        if not txn_created:
            continue

        # Check if created after settlement
        if txn_created <= setl_created:
            continue

        # Amount tolerance
        amt_score = _amount_tolerance_score(abs(txn_amount - discrepancy))
        if amt_score < 0.3:
            continue

        # Time proximity
        time_score = _time_proximity_score(txn_created, setl_created)

        combined = 0.6 * amt_score + 0.4 * time_score

        if combined > best_score:
            best_score = combined
            best_txn_id = txn.get("id")
            best_evidence = [
                f"{txn_type.title()} {txn['id']} (amount={txn_amount} paise) "
                f"created at {txn_created.isoformat()} — "
                f"after settlement {settlement['id']} created at {setl_created.isoformat()}",
            ]

    if best_score < 0.4:
        return None

    confidence = min(0.95, max(0.5, best_score))
    return Hypothesis(
        category="timing_mismatch",
        confidence=round(confidence, 3),
        root_cause=f"Timing mismatch: {best_txn_id} was created after its settlement, "
                   f"causing a discrepancy of {discrepancy} paise.",
        evidence=best_evidence,
        recommended_action=_determine_action(confidence, discrepancy, "timing_mismatch"),
    )


def _check_fee_change(
    exc_type: str,
    ctx: dict,
    related: dict,
    discrepancy: int,
) -> Hypothesis | None:
    """
    Recorded fee vs expected fee at any plausible MDR rate diverges by
    an amount matching the discrepancy.
    """
    for txn in related.get("transactions", []):
        if txn.get("type") != "payment":
            continue

        recorded_fee = txn.get("fee", 0)
        txn_amount = txn.get("amount", 0)
        if txn_amount == 0:
            continue

        for rate in PLAUSIBLE_MDR_RATES:
            expected_fee = round(txn_amount * rate)
            fee_diff = abs(recorded_fee - expected_fee)

            # Check if the fee difference is close to the discrepancy
            # OR if the fee itself is simply wrong at this rate
            if fee_diff <= AMOUNT_MINOR_TOLERANCE:
                # Fee matches this rate — not a discrepancy
                continue

            # The actual MDR that produces the recorded fee
            actual_rate = recorded_fee / txn_amount if txn_amount else 0

            # Check if the fee divergence explains the discrepancy
            divergence_from_discrepancy = abs(fee_diff - discrepancy)
            amt_score = _amount_tolerance_score(divergence_from_discrepancy)

            if amt_score < 0.3:
                # Also check direct fee diff match
                direct_score = _amount_tolerance_score(abs(recorded_fee - round(txn_amount * EXPECTED_MDR_RATE)))
                if direct_score > 0.3 and exc_type == "fee_discrepancy":
                    # The recorded fee doesn't match expected — this IS the fee discrepancy
                    expected_at_2pct = round(txn_amount * EXPECTED_MDR_RATE)
                    confidence = min(0.95, max(0.6, 0.7 + (1.0 - abs(actual_rate - EXPECTED_MDR_RATE) / 0.01) * 0.2))
                    confidence = max(0.6, confidence)

                    return Hypothesis(
                        category="fee_change",
                        confidence=round(confidence, 3),
                        root_cause=f"Fee discrepancy on {txn['id']}: recorded fee {recorded_fee} paise "
                                   f"(effective rate {actual_rate:.3%}) vs expected {expected_at_2pct} paise "
                                   f"at standard {EXPECTED_MDR_RATE:.1%} MDR.",
                        evidence=[
                            f"Transaction {txn['id']}: amount={txn_amount}, recorded_fee={recorded_fee}, "
                            f"expected_fee_at_2%={expected_at_2pct}, difference={recorded_fee - expected_at_2pct}",
                            f"Effective MDR rate: {actual_rate:.4%} (expected: {EXPECTED_MDR_RATE:.1%})",
                        ],
                        recommended_action=_determine_action(confidence, discrepancy, "fee_change"),
                        details={"actual_rate": actual_rate, "expected_rate": EXPECTED_MDR_RATE},
                    )
                continue

            # Fee divergence at this rate explains the discrepancy
            confidence = min(0.95, max(0.6, 0.5 + amt_score * 0.4))

            return Hypothesis(
                category="fee_change",
                confidence=round(confidence, 3),
                root_cause=f"Fee change: recorded fee {recorded_fee} paise on {txn['id']} "
                           f"diverges from expected at {rate:.1%} MDR rate, "
                           f"explaining the {discrepancy} paise discrepancy.",
                evidence=[
                    f"Transaction {txn['id']}: amount={txn_amount}, recorded_fee={recorded_fee}, "
                    f"expected_fee_at_{rate:.1%}={expected_fee}, diff={fee_diff}",
                ],
                recommended_action=_determine_action(confidence, discrepancy, "fee_change"),
                details={"rate_checked": rate},
            )

    # Direct check for fee_discrepancy exception type
    if exc_type == "fee_discrepancy":
        recorded = ctx.get("recorded_fee")
        expected = ctx.get("expected_fee")
        txn_id = ctx.get("transaction_id", "unknown")
        if recorded is not None and expected is not None:
            fee_diff = abs(recorded - expected)
            txn_amount = ctx.get("amount", 0)
            actual_rate = recorded / txn_amount if txn_amount else 0

            confidence = min(0.95, max(0.7, 0.8 + _amount_tolerance_score(fee_diff - discrepancy) * 0.15))

            return Hypothesis(
                category="fee_change",
                confidence=round(confidence, 3),
                root_cause=f"Fee discrepancy on {txn_id}: recorded {recorded} vs expected {expected} paise "
                           f"(effective rate {actual_rate:.3%} vs {EXPECTED_MDR_RATE:.1%}).",
                evidence=[
                    f"Transaction {txn_id}: recorded_fee={recorded}, expected_fee={expected}, "
                    f"difference={recorded - expected} paise",
                    f"Exception context confirms fee mismatch amount_at_risk={discrepancy}",
                ],
                recommended_action=_determine_action(confidence, discrepancy, "fee_change"),
                details={"actual_rate": actual_rate},
            )

    return None


def _check_missing_refund(
    exc_type: str,
    ctx: dict,
    related: dict,
    discrepancy: int,
) -> Hypothesis | None:
    """A refund exists, amount ≈ discrepancy, not yet linked to the settlement."""
    settlement = related.get("settlement")
    setl_id = settlement.get("id") if settlement else ctx.get("settlement_id")

    for txn in related.get("transactions", []):
        if txn.get("type") != "refund":
            continue

        refund_amount = txn.get("amount", 0)
        amt_score = _amount_tolerance_score(abs(refund_amount - discrepancy))
        if amt_score < 0.4:
            continue

        # Check if refund is NOT linked to this settlement
        refund_setl = txn.get("settlement_id")
        if refund_setl and refund_setl == setl_id:
            continue  # Already linked — not a missing refund

        confidence = min(0.9, max(0.5, 0.5 + amt_score * 0.4))
        return Hypothesis(
            category="missing_refund",
            confidence=round(confidence, 3),
            root_cause=f"Unlinked refund {txn['id']} (amount={refund_amount} paise) "
                       f"approximately matches discrepancy of {discrepancy} paise.",
            evidence=[
                f"Refund {txn['id']}: amount={refund_amount}, settlement_id={refund_setl or 'None'}, "
                f"discrepancy={discrepancy}",
            ],
            recommended_action=_determine_action(confidence, discrepancy, "missing_refund"),
        )

    return None


def _check_duplicate_charge(
    exc_type: str,
    ctx: dict,
    related: dict,
    discrepancy: int,
) -> Hypothesis | None:
    """
    Reuse the existing duplicate-detection signature from reconciliation_engine.py
    Step 4: same (amount, method, order_id) within 30 min window.
    """
    # If the exception itself is about duplicates, use the context directly
    if exc_type == "duplicate_suspected":
        original_id = ctx.get("original_id", "unknown")
        duplicate_id = ctx.get("duplicate_id", "unknown")
        amount = ctx.get("amount", 0)
        time_diff = ctx.get("time_diff_seconds", 0)

        # Higher confidence for closer timestamps
        time_factor = max(0.0, 1.0 - abs(time_diff) / 1800)
        confidence = min(0.95, max(0.7, 0.7 + time_factor * 0.25))

        return Hypothesis(
            category="duplicate_charge",
            confidence=round(confidence, 3),
            root_cause=f"Suspected duplicate charge: {duplicate_id} duplicates {original_id} "
                       f"(same amount {amount} paise, {abs(time_diff):.0f}s apart).",
            evidence=[
                f"Original: {original_id}, Duplicate: {duplicate_id}",
                f"Amount: {amount} paise, Method: {ctx.get('method', 'N/A')}, "
                f"Order: {ctx.get('order_id', 'N/A')}",
                f"Time difference: {abs(time_diff):.0f} seconds (threshold: 1800s)",
            ],
            recommended_action=_determine_action(confidence, amount, "duplicate_charge"),
        )

    # Check related transactions for duplicate signatures
    payments = [t for t in related.get("transactions", []) if t.get("type") == "payment"]
    if len(payments) < 2:
        return None

    for i, t1 in enumerate(payments):
        for t2 in payments[i + 1:]:
            key1 = f"{t1.get('amount')}|{t1.get('method')}|{t1.get('order_id')}"
            key2 = f"{t2.get('amount')}|{t2.get('method')}|{t2.get('order_id')}"
            if key1 != key2:
                continue

            dt1 = _parse_dt(t1.get("created_at"))
            dt2 = _parse_dt(t2.get("created_at"))
            if dt1 and dt2:
                time_diff = abs((dt1 - dt2).total_seconds())
                if time_diff <= 1800:
                    time_factor = max(0.0, 1.0 - time_diff / 1800)
                    confidence = min(0.95, max(0.7, 0.7 + time_factor * 0.25))
                    return Hypothesis(
                        category="duplicate_charge",
                        confidence=round(confidence, 3),
                        root_cause=f"Duplicate charge detected: {t1['id']} and {t2['id']} "
                                   f"share the same signature and are {time_diff:.0f}s apart.",
                        evidence=[
                            f"Transaction {t1['id']} and {t2['id']}: same amount/method/order",
                            f"Time difference: {time_diff:.0f}s",
                        ],
                        recommended_action=_determine_action(
                            confidence, t1.get("amount", 0), "duplicate_charge"
                        ),
                    )

    return None


def _check_partial_settlement(
    exc_type: str,
    ctx: dict,
    related: dict,
    discrepancy: int,
) -> Hypothesis | None:
    """
    A transaction with on_hold-like status exists whose amount ≈ discrepancy.
    Transaction.status is a string field — check for 'on_hold', 'authorized', 'created'
    (i.e. non-terminal states that could indicate a held payment).
    """
    hold_statuses = {"on_hold", "authorized", "created", "pending"}

    for txn in related.get("transactions", []):
        status = (txn.get("status") or "").lower()
        if status not in hold_statuses:
            continue

        txn_amount = txn.get("amount", 0)
        amt_score = _amount_tolerance_score(abs(txn_amount - discrepancy))
        if amt_score < 0.3:
            continue

        confidence = min(0.85, max(0.5, 0.5 + amt_score * 0.35))
        return Hypothesis(
            category="partial_settlement",
            confidence=round(confidence, 3),
            root_cause=f"Partial settlement: {txn['id']} has status '{status}' "
                       f"with amount {txn_amount} paise ≈ discrepancy {discrepancy} paise.",
            evidence=[
                f"Transaction {txn['id']}: status={status}, amount={txn_amount}, "
                f"discrepancy={discrepancy}",
            ],
            recommended_action=_determine_action(confidence, discrepancy, "partial_settlement"),
        )

    return None


def _check_manual_adjustment(
    exc_type: str,
    ctx: dict,
    related: dict,
    discrepancy: int,
) -> Hypothesis | None:
    """An adjustment-type transaction with no settlement link, amount ≈ discrepancy."""
    # Direct match for unexpected_adjustment exception type
    if exc_type == "unexpected_adjustment":
        txn_id = ctx.get("transaction_id", "unknown")
        amount = ctx.get("amount", 0)
        amt_score = _amount_tolerance_score(abs(amount - discrepancy))
        confidence = min(0.9, max(0.6, 0.6 + amt_score * 0.3))

        return Hypothesis(
            category="manual_adjustment",
            confidence=round(confidence, 3),
            root_cause=f"Unexpected manual adjustment {txn_id}: amount {amount} paise "
                       f"with no linked settlement or order.",
            evidence=[
                f"Adjustment {txn_id}: amount={amount} paise, "
                f"description='{ctx.get('description', 'N/A')}', "
                f"settlement_id=None",
            ],
            recommended_action=_determine_action(confidence, discrepancy, "manual_adjustment"),
        )

    # Check related transactions
    for txn in related.get("transactions", []):
        if txn.get("type") != "adjustment":
            continue
        if txn.get("settlement_id"):
            continue  # Has a settlement link — not unexplained

        txn_amount = txn.get("amount", 0)
        amt_score = _amount_tolerance_score(abs(txn_amount - discrepancy))
        if amt_score < 0.3:
            continue

        confidence = min(0.9, max(0.6, 0.6 + amt_score * 0.3))
        return Hypothesis(
            category="manual_adjustment",
            confidence=round(confidence, 3),
            root_cause=f"Unlinked adjustment {txn['id']} (amount={txn_amount} paise) "
                       f"may explain discrepancy of {discrepancy} paise.",
            evidence=[
                f"Adjustment {txn['id']}: amount={txn_amount}, settlement_id=None",
            ],
            recommended_action=_determine_action(confidence, discrepancy, "manual_adjustment"),
        )

    return None


def _check_rounding(
    exc_type: str,
    ctx: dict,
    related: dict,
    discrepancy: int,
) -> Hypothesis | None:
    """Discrepancy < 100 paise (₹1) and count of settlement transactions is high."""
    if discrepancy >= 100:
        return None

    # Count transactions in the settlement
    txn_count = len(related.get("transactions", []))
    if txn_count < 2:
        # Also check from context
        payment_ids = ctx.get("payment_ids", [])
        if len(payment_ids) < 2:
            return None
        txn_count = len(payment_ids)

    # Higher confidence for smaller discrepancies and more transactions
    size_factor = max(0.0, 1.0 - discrepancy / 100)
    count_factor = min(1.0, txn_count / 5)
    confidence = min(0.95, max(0.85, 0.85 + size_factor * 0.05 + count_factor * 0.05))

    return Hypothesis(
        category="rounding",
        confidence=round(confidence, 3),
        root_cause=f"Rounding difference of {discrepancy} paise across {txn_count} transactions — "
                   f"likely sub-paise rounding during fee/tax calculation.",
        evidence=[
            f"Discrepancy: {discrepancy} paise (< ₹1 threshold)",
            f"Transaction count: {txn_count} (multiple transactions increase rounding risk)",
            f"Settlement: {ctx.get('settlement_id', 'N/A')}",
        ],
        recommended_action=_determine_action(confidence, discrepancy, "rounding"),
    )


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

# Mapping from exception types to relevant rule checks (ordered by priority)
_EXCEPTION_RULE_MAP: dict[str, list] = {
    "timing_mismatch": [_check_timing_mismatch, _check_missing_refund],
    "fee_discrepancy": [_check_fee_change],
    "amount_mismatch": [
        _check_rounding, _check_timing_mismatch, _check_fee_change,
        _check_missing_refund, _check_manual_adjustment,
    ],
    "duplicate_suspected": [_check_duplicate_charge],
    "missing_settlement": [_check_partial_settlement],
    "missing_bank_entry": [],  # No rule can diagnose this from available data
    "unexpected_adjustment": [_check_manual_adjustment],
    "rounding_difference": [_check_rounding],
}

# All rules in priority order for fallback
_ALL_RULES = [
    _check_rounding,
    _check_duplicate_charge,
    _check_fee_change,
    _check_timing_mismatch,
    _check_missing_refund,
    _check_partial_settlement,
    _check_manual_adjustment,
]


def generate_hypotheses(
    exception_type: str,
    exception_context: dict,
    related_data: dict,
    amount_at_risk: int,
) -> list[Hypothesis]:
    """
    Generate 0–3 candidate root-cause hypotheses for an exception.

    Args:
        exception_type: The detected exception type (e.g. 'fee_discrepancy').
        exception_context: The exception's context dict.
        related_data: Gathered related data (transactions, settlement, bank_statement).
        amount_at_risk: The discrepancy amount in paise.

    Returns:
        List of Hypothesis objects, sorted by confidence descending.
        If nothing fires, returns a single 'unknown' hypothesis with confidence 0.
    """
    discrepancy = abs(amount_at_risk)
    ctx = exception_context or {}
    hypotheses: list[Hypothesis] = []

    # First, try rules specifically relevant to this exception type
    targeted_rules = _EXCEPTION_RULE_MAP.get(exception_type, [])
    for rule_fn in targeted_rules:
        try:
            h = rule_fn(exception_type, ctx, related_data, discrepancy)
            if h and h.confidence > 0:
                hypotheses.append(h)
        except Exception:
            continue  # Individual rule failure must not crash the engine

    # If no targeted rule fired, try all rules
    if not hypotheses:
        for rule_fn in _ALL_RULES:
            if rule_fn in targeted_rules:
                continue  # Already tried
            try:
                h = rule_fn(exception_type, ctx, related_data, discrepancy)
                if h and h.confidence > 0:
                    hypotheses.append(h)
            except Exception:
                continue

    # Sort by confidence descending, take top 3
    hypotheses.sort(key=lambda h: h.confidence, reverse=True)
    hypotheses = hypotheses[:3]

    # If nothing fired, return unknown
    if not hypotheses:
        hypotheses.append(Hypothesis(
            category="unknown",
            confidence=0.0,
            root_cause=f"No deterministic rule matched for {exception_type} "
                       f"exception (discrepancy: {discrepancy} paise). "
                       f"Requires manual investigation.",
            evidence=[
                f"Exception type: {exception_type}",
                f"Amount at risk: {discrepancy} paise",
                f"Related transactions: {len(related_data.get('transactions', []))}",
            ],
            recommended_action="escalate",
        ))

    return hypotheses
