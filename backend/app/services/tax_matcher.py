"""
Tax-Line Matcher — Compare expected vs recorded GST/fees.

For every captured payment transaction:
  - Calculate expected_fee = amount × MDR_RATE
  - Calculate expected_tax = expected_fee × GST_RATE
  - Compare against recorded fee and tax
  - Classify discrepancy: exact_match | rounding_diff | rate_change | unexplained

Generates a structured tax reconciliation report.
"""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.config import settings
from app.models import Transaction


# Tolerance thresholds (paise)
ROUNDING_TOLERANCE = 10    # ±10 paise (₹0.10)
MINOR_TOLERANCE = 100      # ±₹1


async def generate_tax_reconciliation(
    db: AsyncSession,
    merchant_id: str | None = None,
) -> dict:
    """
    Generate a full GST/fee tax reconciliation report.

    Returns:
        {
            "summary": { ... },
            "discrepancies": [ ... ],
            "totals": { ... },
            "method_breakdown": { ... },
        }
    """
    # Fetch all captured payment transactions
    query = select(Transaction).where(
        Transaction.type == "payment",
        Transaction.status == "captured",
    )
    if merchant_id:
        query = query.where(Transaction.merchant_id == merchant_id)

    result = await db.execute(query)
    transactions = result.scalars().all()

    # Accumulators
    total_expected_fee = 0
    total_recorded_fee = 0
    total_expected_tax = 0
    total_recorded_tax = 0
    total_gross_amount = 0

    exact_matches = 0
    rounding_diffs = 0
    rate_changes = 0
    unexplained = 0

    discrepancies = []
    method_stats: dict[str, dict] = {}

    for txn in transactions:
        amount = txn.amount
        recorded_fee = txn.fee
        recorded_tax = txn.tax
        method = txn.method or "unknown"

        # Expected at standard MDR rate
        expected_fee = round(amount * settings.expected_mdr_rate)
        expected_tax = round(expected_fee * settings.expected_gst_rate)

        fee_diff = recorded_fee - expected_fee
        tax_diff = recorded_tax - expected_tax
        abs_fee_diff = abs(fee_diff)
        abs_tax_diff = abs(tax_diff)

        # Accumulate totals
        total_gross_amount += amount
        total_expected_fee += expected_fee
        total_recorded_fee += recorded_fee
        total_expected_tax += expected_tax
        total_recorded_tax += recorded_tax

        # Classify
        if abs_fee_diff == 0 and abs_tax_diff == 0:
            category = "exact_match"
            exact_matches += 1
        elif abs_fee_diff <= ROUNDING_TOLERANCE and abs_tax_diff <= ROUNDING_TOLERANCE:
            category = "rounding_diff"
            rounding_diffs += 1
        else:
            # Check if it matches an alternative MDR rate
            effective_rate = recorded_fee / amount if amount > 0 else 0
            matched_alt_rate = False
            for alt_rate in settings.plausible_mdr_rates:
                alt_fee = round(amount * alt_rate)
                if abs(recorded_fee - alt_fee) <= ROUNDING_TOLERANCE:
                    category = "rate_change"
                    rate_changes += 1
                    matched_alt_rate = True
                    break

            if not matched_alt_rate:
                category = "unexplained"
                unexplained += 1

        # Per-method stats
        if method not in method_stats:
            method_stats[method] = {
                "count": 0,
                "total_amount": 0,
                "expected_fee": 0,
                "recorded_fee": 0,
                "fee_diff": 0,
                "expected_tax": 0,
                "recorded_tax": 0,
                "tax_diff": 0,
            }
        ms = method_stats[method]
        ms["count"] += 1
        ms["total_amount"] += amount
        ms["expected_fee"] += expected_fee
        ms["recorded_fee"] += recorded_fee
        ms["fee_diff"] += fee_diff
        ms["expected_tax"] += expected_tax
        ms["recorded_tax"] += recorded_tax
        ms["tax_diff"] += tax_diff

        # Only include non-exact matches in discrepancies list
        if category != "exact_match":
            effective_rate = recorded_fee / amount if amount > 0 else 0
            discrepancies.append({
                "transaction_id": txn.id,
                "amount_paise": amount,
                "amount_rupees": round(amount / 100, 2),
                "method": method,
                "recorded_fee": recorded_fee,
                "expected_fee": expected_fee,
                "fee_difference": fee_diff,
                "recorded_tax": recorded_tax,
                "expected_tax": expected_tax,
                "tax_difference": tax_diff,
                "effective_mdr_rate": round(effective_rate, 5),
                "expected_mdr_rate": settings.expected_mdr_rate,
                "category": category,
                "settlement_id": txn.settlement_id,
            })

    total_count = len(transactions)

    # Compute per-method rupee values
    method_breakdown = {}
    for method, ms in method_stats.items():
        method_breakdown[method] = {
            "transaction_count": ms["count"],
            "total_amount_rupees": round(ms["total_amount"] / 100, 2),
            "expected_fee_rupees": round(ms["expected_fee"] / 100, 2),
            "recorded_fee_rupees": round(ms["recorded_fee"] / 100, 2),
            "fee_difference_rupees": round(ms["fee_diff"] / 100, 2),
            "expected_gst_rupees": round(ms["expected_tax"] / 100, 2),
            "recorded_gst_rupees": round(ms["recorded_tax"] / 100, 2),
            "gst_difference_rupees": round(ms["tax_diff"] / 100, 2),
        }

    return {
        "summary": {
            "total_transactions": total_count,
            "exact_matches": exact_matches,
            "rounding_differences": rounding_diffs,
            "rate_changes": rate_changes,
            "unexplained_discrepancies": unexplained,
            "match_rate": round(exact_matches / max(total_count, 1), 4),
            "discrepancy_rate": round(
                (rounding_diffs + rate_changes + unexplained) / max(total_count, 1),
                4,
            ),
            "expected_mdr_rate": settings.expected_mdr_rate,
            "expected_gst_rate": settings.expected_gst_rate,
        },
        "totals": {
            "gross_transaction_amount_paise": total_gross_amount,
            "gross_transaction_amount_rupees": round(total_gross_amount / 100, 2),
            "expected_total_fee_paise": total_expected_fee,
            "expected_total_fee_rupees": round(total_expected_fee / 100, 2),
            "recorded_total_fee_paise": total_recorded_fee,
            "recorded_total_fee_rupees": round(total_recorded_fee / 100, 2),
            "fee_difference_paise": total_recorded_fee - total_expected_fee,
            "fee_difference_rupees": round((total_recorded_fee - total_expected_fee) / 100, 2),
            "expected_total_gst_paise": total_expected_tax,
            "expected_total_gst_rupees": round(total_expected_tax / 100, 2),
            "recorded_total_gst_paise": total_recorded_tax,
            "recorded_total_gst_rupees": round(total_recorded_tax / 100, 2),
            "gst_difference_paise": total_recorded_tax - total_expected_tax,
            "gst_difference_rupees": round((total_recorded_tax - total_expected_tax) / 100, 2),
        },
        "discrepancies": discrepancies,
        "method_breakdown": method_breakdown,
    }
