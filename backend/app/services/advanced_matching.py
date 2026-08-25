"""
Advanced Matching Engine — Ensemble scoring with 5 strategies.

Each strategy produces a score between 0.0 and 1.0.
A weighted combination yields the final confidence score.

Strategies:
  1. UTR Match (weight 0.35) — Exact or fuzzy UTR matching
  2. Amount Match (weight 0.25) — Amount comparison with tolerance bands
  3. Date Match (weight 0.15) — Date proximity scoring
  4. Merchant Category Match (weight 0.15) — Payment method and category correlation
  5. Description Pattern Match (weight 0.10) — Text pattern matching on bank descriptions

Thresholds:
  - Auto-match: ≥ 0.95
  - Suggest match: ≥ 0.75
  - Manual review: < 0.75
"""

import re
from datetime import date, timedelta
from dataclasses import dataclass, field
from typing import Optional

from app.models import Settlement, BankStatement, Transaction


# ---------------------------------------------------------------------------
# Strategy Results
# ---------------------------------------------------------------------------

@dataclass
class MatchScore:
    """Result from a single matching strategy."""
    strategy: str
    score: float  # 0.0 to 1.0
    weight: float
    explanation: str = ""
    details: dict = field(default_factory=dict)

    @property
    def weighted_score(self) -> float:
        return self.score * self.weight


@dataclass
class EnsembleResult:
    """Combined result from all strategies."""
    settlement_id: str
    bank_stmt_id: int
    scores: list[MatchScore]
    final_score: float
    match_type: str  # auto_match | suggested | manual_review
    explanation: str = ""
    details: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Strategy Weights
# ---------------------------------------------------------------------------

WEIGHTS = {
    "utr": 0.35,
    "amount": 0.25,
    "date": 0.15,
    "category": 0.15,
    "description": 0.10,
}

# Thresholds
AUTO_MATCH_THRESHOLD = 0.95
SUGGEST_MATCH_THRESHOLD = 0.75

# Amount tolerance bands
AMOUNT_EXACT_TOLERANCE = 0       # Exact match
AMOUNT_ROUNDING_TOLERANCE = 10   # ±10 paise (₹0.10)
AMOUNT_MINOR_TOLERANCE = 100     # ±100 paise (₹1.00)
AMOUNT_FEE_TOLERANCE = 5000      # ±5000 paise (₹50.00) — may include fee differences

# Date proximity max days
DATE_MAX_DAYS = 7


# ---------------------------------------------------------------------------
# Strategy 1: UTR Match
# ---------------------------------------------------------------------------

def score_utr(settlement: Settlement, bank_stmt: BankStatement) -> MatchScore:
    """
    Match settlement UTR against bank statement reference.
    Exact match: 1.0, partial/fuzzy: 0.3-0.8, no match: 0.0
    """
    utr = (settlement.utr or "").strip().upper()
    ref = (bank_stmt.reference or "").strip().upper()

    if not utr or not ref:
        return MatchScore("utr", 0.0, WEIGHTS["utr"], "Missing UTR or reference.", {"reason": "missing UTR or reference"})

    # Exact match
    if utr == ref:
        return MatchScore("utr", 1.0, WEIGHTS["utr"], "Exact UTR match.", {"match": "exact"})

    # One contains the other (partial UTR in longer reference)
    if utr in ref or ref in utr:
        overlap = min(len(utr), len(ref)) / max(len(utr), len(ref))
        return MatchScore("utr", 0.5 + overlap * 0.3, WEIGHTS["utr"], "Partial UTR match.", {"match": "partial", "overlap": overlap})

    # Numeric similarity (strip non-digits and compare)
    utr_digits = re.sub(r'\D', '', utr)
    ref_digits = re.sub(r'\D', '', ref)
    if utr_digits and ref_digits and utr_digits == ref_digits:
        return MatchScore("utr", 0.85, WEIGHTS["utr"], "Numeric UTR match.", {"match": "numeric_match"})

    # Levenshtein-like similarity for short UTRs
    if len(utr) > 4 and len(ref) > 4:
        common = sum(1 for a, b in zip(utr, ref) if a == b)
        max_len = max(len(utr), len(ref))
        similarity = common / max_len
        if similarity > 0.7:
            return MatchScore("utr", similarity * 0.6, WEIGHTS["utr"], "Fuzzy UTR match.", {"match": "fuzzy", "similarity": similarity})

    return MatchScore("utr", 0.0, WEIGHTS["utr"], "No UTR match.", {"match": "none"})


# ---------------------------------------------------------------------------
# Strategy 2: Amount Match
# ---------------------------------------------------------------------------

def score_amount(settlement: Settlement, bank_stmt: BankStatement) -> MatchScore:
    """
    Compare settlement amount with bank credit amount.
    Uses tolerance bands for different score levels.
    """
    setl_amount = settlement.amount
    bank_amount = bank_stmt.credit

    if setl_amount == 0 or bank_amount == 0:
        return MatchScore("amount", 0.0, WEIGHTS["amount"], "Zero amount.", {"reason": "zero amount"})

    difference = abs(setl_amount - bank_amount)

    if difference <= AMOUNT_EXACT_TOLERANCE:
        score = 1.0
        band = "exact"
        explanation = "Exact amount match."
    elif difference <= AMOUNT_ROUNDING_TOLERANCE:
        score = 0.95
        band = "rounding"
        explanation = f"Amount matches within rounding tolerance ({difference} paise difference)."
    elif difference <= AMOUNT_MINOR_TOLERANCE:
        score = 0.85
        band = "minor"
        explanation = f"Amount matches within minor tolerance ({difference} paise difference)."
    elif difference <= AMOUNT_FEE_TOLERANCE:
        # Could be fee difference; score based on relative diff
        relative_diff = difference / max(setl_amount, bank_amount)
        score = max(0.3, 0.7 - relative_diff * 5)
        band = "fee_range"
        explanation = f"Amount difference ({difference} paise) is within typical fee variation."
    else:
        # Large difference — score inversely proportional
        relative_diff = difference / max(setl_amount, bank_amount)
        score = max(0.0, 0.3 - relative_diff)
        band = "large_diff"
        explanation = f"Large amount discrepancy of {difference} paise."

    return MatchScore("amount", score, WEIGHTS["amount"], explanation, {
        "settlement_amount": setl_amount,
        "bank_amount": bank_amount,
        "difference": difference,
        "band": band,
    })


# ---------------------------------------------------------------------------
# Strategy 3: Date Match
# ---------------------------------------------------------------------------

def score_date(settlement: Settlement, bank_stmt: BankStatement) -> MatchScore:
    """
    Score based on proximity between settlement creation date and bank entry date.
    Same day: 1.0, T+1: 0.9, T+2: 0.7, T+3: 0.5, beyond: decay
    """
    setl_date = settlement.created_at.date() if settlement.created_at else None
    bank_date = bank_stmt.entry_date

    if not setl_date or not bank_date:
        return MatchScore("date", 0.0, WEIGHTS["date"], "Missing date.", {"reason": "missing date"})

    day_diff = abs((bank_date - setl_date).days)

    if day_diff == 0:
        score = 1.0
        explanation = "Same day match."
    elif day_diff == 1:
        score = 0.9  # T+1 is very common for settlements
        explanation = "T+1 day match."
    elif day_diff == 2:
        score = 0.7
        explanation = "T+2 days match."
    elif day_diff == 3:
        score = 0.5
        explanation = "T+3 days match."
    elif day_diff <= DATE_MAX_DAYS:
        score = max(0.1, 0.4 - (day_diff - 3) * 0.1)
        explanation = f"Matched within {day_diff} days."
    else:
        score = 0.0
        explanation = f"Date difference of {day_diff} days exceeds threshold."

    return MatchScore("date", score, WEIGHTS["date"], explanation, {
        "settlement_date": str(setl_date),
        "bank_date": str(bank_date),
        "day_diff": day_diff,
    })


# ---------------------------------------------------------------------------
# Strategy 4: Merchant Category Match
# ---------------------------------------------------------------------------

def score_category(
    settlement: Settlement,
    bank_stmt: BankStatement,
    settlement_transactions: list[Transaction],
) -> MatchScore:
    """
    Match based on payment method and merchant category patterns.
    If the settlement's transactions use methods that correlate with the
    bank description patterns, boost the score.
    """
    if not settlement_transactions:
        return MatchScore("category", 0.0, WEIGHTS["category"], "No transactions to determine category.", {"reason": "no transactions"})

    # Collect methods used in this settlement
    methods = set()
    for txn in settlement_transactions:
        if txn.method:
            methods.add(txn.method.lower())

    bank_desc = (bank_stmt.description or "").lower()

    score = 0.0
    matches = []

    # Method-based patterns in bank descriptions
    method_patterns = {
        "upi": ["upi", "neft", "imps", "rtgs"],
        "card": ["card", "visa", "mastercard", "rupay", "credit", "debit"],
        "netbanking": ["netbanking", "net banking", "neft", "internet banking"],
        "wallet": ["wallet", "paytm", "phonepe", "mobikwik"],
    }

    for method in methods:
        patterns = method_patterns.get(method, [method])
        for pattern in patterns:
            if pattern in bank_desc:
                score = max(score, 0.8)
                matches.append(f"{method}→{pattern}")
                break

    # Check for settlement/payment gateway keywords in bank desc
    gateway_keywords = ["razorpay", "rzp", "payment", "settlement", "setl", "merchant"]
    for kw in gateway_keywords:
        if kw in bank_desc:
            score = max(score, 0.5)
            matches.append(f"gateway_keyword:{kw}")

    # If multiple methods match, boost score
    if len(matches) >= 2:
        score = min(1.0, score + 0.1)
        
    explanation = "Category match found based on keywords." if score > 0 else "No category match found."

    return MatchScore("category", score, WEIGHTS["category"], explanation, {
        "methods": list(methods),
        "matches": matches,
    })


# ---------------------------------------------------------------------------
# Strategy 5: Description Pattern Match
# ---------------------------------------------------------------------------

def score_description(settlement: Settlement, bank_stmt: BankStatement) -> MatchScore:
    """
    NLP-lite pattern matching on bank statement descriptions.
    Look for settlement IDs, transaction IDs, amounts, or merchant identifiers.
    """
    desc = (bank_stmt.description or "").lower()

    if not desc:
        return MatchScore("description", 0.0, WEIGHTS["description"], "No description.", {"reason": "no description"})

    score = 0.0
    matches = []

    # Check if settlement ID appears in description
    if settlement.id and settlement.id.lower() in desc:
        score = max(score, 1.0)
        matches.append("settlement_id_in_desc")

    # Check if UTR appears in description
    if settlement.utr and settlement.utr.lower() in desc:
        score = max(score, 0.9)
        matches.append("utr_in_desc")

    # Check for amount patterns (convert paise to rupees for matching)
    amount_rupees = settlement.amount / 100
    amount_str = f"{amount_rupees:.2f}"
    amount_int_str = str(int(amount_rupees))

    if amount_str in desc or amount_int_str in desc:
        score = max(score, 0.6)
        matches.append(f"amount_in_desc:{amount_str}")

    # Check for common settlement description patterns
    settlement_patterns = [
        r"setl[_\-]?\w+",
        r"razorpay\s+settlement",
        r"rzp\s+setl",
        r"merchant\s+settlement",
    ]
    for pattern in settlement_patterns:
        if re.search(pattern, desc):
            score = max(score, 0.4)
            matches.append(f"pattern:{pattern}")

    explanation = "Description pattern matched." if score > 0 else "No description pattern match."

    return MatchScore("description", score, WEIGHTS["description"], explanation, {
        "matches": matches,
    })


# ---------------------------------------------------------------------------
# Ensemble Matcher
# ---------------------------------------------------------------------------

def match_settlement_to_bank(
    settlement: Settlement,
    bank_stmt: BankStatement,
    settlement_transactions: list[Transaction] | None = None,
) -> EnsembleResult:
    """
    Run all 5 strategies and combine scores with weighted average.
    Returns an EnsembleResult with final score and match type.
    """
    scores = [
        score_utr(settlement, bank_stmt),
        score_amount(settlement, bank_stmt),
        score_date(settlement, bank_stmt),
        score_category(settlement, bank_stmt, settlement_transactions or []),
        score_description(settlement, bank_stmt),
    ]

    final_score = sum(s.weighted_score for s in scores)

    # Determine match type
    if final_score >= AUTO_MATCH_THRESHOLD:
        match_type = "auto_match"
    elif final_score >= SUGGEST_MATCH_THRESHOLD:
        match_type = "suggested"
    else:
        match_type = "manual_review"
        
    aggregate_explanation = " | ".join([f"{s.strategy.upper()}: {s.explanation}" for s in scores])

    return EnsembleResult(
        settlement_id=settlement.id,
        bank_stmt_id=bank_stmt.id,
        scores=scores,
        final_score=round(final_score, 4),
        match_type=match_type,
        explanation=aggregate_explanation,
        details={
            "strategy_scores": {s.strategy: round(s.score, 4) for s in scores},
            "weighted_scores": {s.strategy: round(s.weighted_score, 4) for s in scores},
            "aggregate_explanation": aggregate_explanation,
        },
    )


def find_best_matches(
    settlements: list[Settlement],
    bank_stmts: list[BankStatement],
    txns_by_settlement: dict[str, list[Transaction]] | None = None,
) -> list[EnsembleResult]:
    """
    For each settlement, find the best matching bank statement using ensemble scoring.
    Returns a list of best matches sorted by confidence (highest first).
    """
    if not txns_by_settlement:
        txns_by_settlement = {}

    results = []
    used_bank_ids: set[int] = set()

    # Score all combinations
    all_combos: list[EnsembleResult] = []
    for setl in settlements:
        for bank in bank_stmts:
            result = match_settlement_to_bank(
                setl, bank, txns_by_settlement.get(setl.id, [])
            )
            all_combos.append(result)

    # Sort by score descending (greedy assignment)
    all_combos.sort(key=lambda r: r.final_score, reverse=True)

    used_setl_ids: set[str] = set()
    for combo in all_combos:
        if combo.settlement_id in used_setl_ids or combo.bank_stmt_id in used_bank_ids:
            continue
        if combo.final_score > 0:
            results.append(combo)
            used_setl_ids.add(combo.settlement_id)
            used_bank_ids.add(combo.bank_stmt_id)

    return results
