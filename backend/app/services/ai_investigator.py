"""
AI Investigator — LLM-powered exception analysis with 4-step chain.

Investigation Chain:
  1. Fact Gathering — Collect all relevant data points with citations
  2. Hypothesis Generation — Generate 2-3 ranked hypotheses with evidence links
  3. Evidence Validation — Cross-reference each hypothesis against data
  4. Confidence Scoring — Final score based on evidence strength

Only called for exceptions that deterministic rules cannot explain.
Every call is bounded, gated, and audited.

Supports: Google Gemini.
Graceful degradation: if LLM is unavailable, escalate all exceptions.
"""

import json
import time
import traceback
from datetime import datetime

import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.config import settings
from app.models import Exception_, Investigation, Transaction, Settlement, BankStatement
from app.utils.audit import log_audit

# The system prompt that defines the AI investigator's role and constraints
SYSTEM_PROMPT = """You are a financial reconciliation investigator for a payment gateway (similar to Razorpay).

You analyze discrepancies between payments, settlements, refunds, fees, taxes, and bank transactions.

You must follow a structured investigation chain:

STEP 1 - FACT GATHERING: List all relevant facts from the provided data, citing specific IDs and amounts.
STEP 2 - HYPOTHESIS GENERATION: Generate 2-3 ranked hypotheses for the root cause, each with supporting evidence references.
STEP 3 - EVIDENCE VALIDATION: For each hypothesis, list supporting and contradicting evidence.
STEP 4 - CONFIDENCE SCORING: Assign a final confidence score based on evidence strength.

RULES:
1. You MUST cite specific transaction IDs, amounts, and timestamps as evidence.
2. You MUST provide a confidence score between 0.0 and 1.0.
3. You MUST recommend exactly one action: "auto_resolve", "escalate", or "needs_data".
4. You must NOT fabricate transaction IDs or amounts not present in the context.
5. Your explanation must be concise (2-4 sentences) and actionable.

RESPOND IN THIS EXACT JSON FORMAT:
{
  "chain_of_thought": {
    "fact_gathering": ["Fact 1 citing specific ID/amount", "Fact 2", ...],
    "hypotheses": [
      {"hypothesis": "Description", "supporting_evidence": ["Evidence 1", ...], "contradicting_evidence": ["Evidence 1", ...]},
      ...
    ],
    "evidence_validation": {"strongest_hypothesis": "...", "evidence_strength": "strong|moderate|weak", "gaps": ["Gap 1", ...]},
    "scoring_rationale": "Why this confidence level"
  },
  "root_cause": "Brief description of the most likely root cause",
  "evidence": ["Evidence point 1 citing specific IDs/amounts", "Evidence point 2", ...],
  "confidence": 0.85,
  "recommended_action": "auto_resolve",
  "category": "timing_mismatch"
}

Categories: timing_mismatch, fee_change, missing_refund, partial_settlement, duplicate_charge, system_error, rounding, manual_adjustment, unknown"""


def _build_investigation_prompt(exception: Exception_, related_data: dict) -> str:
    """Build the user prompt with all context for the LLM."""
    context_parts = [
        f"## Exception Details",
        f"- Type: {exception.type}",
        f"- Severity: {exception.severity}",
        f"- Amount at risk: {exception.amount_at_risk} paise (₹{exception.amount_at_risk / 100:.2f})",
        f"- Context: {json.dumps(exception.context, indent=2, default=str)}",
    ]

    if related_data.get("transactions"):
        context_parts.append("\n## Related Transactions")
        for txn in related_data["transactions"]:
            context_parts.append(
                f"- {txn['id']}: type={txn['type']}, amount={txn['amount']} paise, "
                f"fee={txn['fee']}, tax={txn['tax']}, status={txn['status']}, "
                f"settlement_id={txn.get('settlement_id', 'N/A')}, "
                f"method={txn.get('method', 'N/A')}, "
                f"created_at={txn.get('created_at', 'N/A')}"
            )

    if related_data.get("settlement"):
        s = related_data["settlement"]
        context_parts.append(
            f"\n## Related Settlement\n"
            f"- {s['id']}: amount={s['amount']} paise, fees={s['fees']}, "
            f"tax={s['tax']}, utr={s.get('utr', 'N/A')}, "
            f"status={s['status']}, created_at={s.get('created_at', 'N/A')}"
        )

    if related_data.get("bank_statement"):
        b = related_data["bank_statement"]
        context_parts.append(
            f"\n## Related Bank Statement\n"
            f"- ID: {b['id']}, bank_account={b['bank_account']}, "
            f"entry_date={b['entry_date']}, "
            f"credit={b['credit']} paise, debit={b['debit']} paise, "
            f"reference={b.get('reference', 'N/A')}, "
            f"description={b.get('description', 'N/A')}"
        )

    context_parts.append(
        "\n## Task\n"
        "Follow the 4-step investigation chain: "
        "1) Gather facts with citations, "
        "2) Generate hypotheses with evidence, "
        "3) Validate evidence for/against each hypothesis, "
        "4) Score confidence based on evidence strength. "
        "Then provide your root cause, evidence, confidence, and recommended action."
    )

    return "\n".join(context_parts)


async def _gather_related_data(db: AsyncSession, exception: Exception_) -> dict:
    """Gather all related entities for the investigation context."""
    related: dict = {"transactions": [], "settlement": None, "bank_statement": None}
    ctx = exception.context or {}

    # Get related transactions
    txn_ids = []
    if "transaction_id" in ctx:
        txn_ids.append(ctx["transaction_id"])
    if "original_id" in ctx:
        txn_ids.append(ctx["original_id"])
    if "duplicate_id" in ctx:
        txn_ids.append(ctx["duplicate_id"])
    if "payment_ids" in ctx:
        txn_ids.extend(ctx["payment_ids"])
    if "refund_ids" in ctx:
        txn_ids.extend(ctx["refund_ids"])

    if txn_ids:
        result = await db.execute(
            select(Transaction).where(Transaction.id.in_(txn_ids))
        )
        for txn in result.scalars().all():
            related["transactions"].append({
                "id": txn.id,
                "type": txn.type,
                "amount": txn.amount,
                "fee": txn.fee,
                "tax": txn.tax,
                "status": txn.status,
                "settlement_id": txn.settlement_id,
                "method": txn.method,
                "order_id": txn.order_id,
                "created_at": txn.created_at.isoformat() if txn.created_at else None,
                "captured_at": txn.captured_at.isoformat() if txn.captured_at else None,
            })

    # Get related settlement
    setl_id = ctx.get("settlement_id")
    if setl_id:
        result = await db.execute(
            select(Settlement).where(Settlement.id == setl_id)
        )
        setl = result.scalar_one_or_none()
        if setl:
            related["settlement"] = {
                "id": setl.id,
                "amount": setl.amount,
                "fees": setl.fees,
                "tax": setl.tax,
                "utr": setl.utr,
                "status": setl.status,
                "created_at": setl.created_at.isoformat() if setl.created_at else None,
            }

    # Get related bank statement
    utr = ctx.get("utr")
    if utr:
        result = await db.execute(
            select(BankStatement).where(BankStatement.reference == utr)
        )
        bank = result.scalar_one_or_none()
        if bank:
            related["bank_statement"] = {
                "id": bank.id,
                "bank_account": bank.bank_account,
                "entry_date": bank.entry_date.isoformat() if bank.entry_date else None,
                "description": bank.description,
                "reference": bank.reference,
                "credit": bank.credit,
                "debit": bank.debit,
                "balance": bank.balance,
            }

    return related


async def _call_gemini(prompt: str) -> dict:
    """Call Google Gemini API. Returns parsed JSON response."""
    import google.generativeai as genai

    genai.configure(api_key=settings.gemini_api_key)
    model = genai.GenerativeModel("gemini-2.0-flash")

    response = model.generate_content(
        [
            {"role": "user", "parts": [{"text": SYSTEM_PROMPT + "\n\n" + prompt}]},
        ],
        generation_config=genai.types.GenerationConfig(
            response_mime_type="application/json",
            temperature=0.2,
        ),
    )

    text = response.text.strip()
    return json.loads(text)


async def _call_llm(prompt: str) -> tuple[dict, str, int, int]:
    """
    Call the configured LLM provider.

    Returns: (parsed_response, model_name, prompt_tokens, response_tokens)
    """
    if settings.gemini_api_key:
        try:
            result = await _call_gemini(prompt)
            return result, "gemini-2.0-flash", len(prompt) // 4, 500  # approximate tokens
        except Exception as e:
            raise ConnectionError(f"LLM provider failed: {e}") from e

    raise ConnectionError("No LLM provider available")


def _validate_llm_response(response: dict) -> dict:
    """Validate and sanitize the LLM response. Enforce guardrails."""
    # Ensure required fields exist
    validated = {
        "root_cause": response.get("root_cause", "Unable to determine root cause"),
        "evidence": response.get("evidence", []),
        "confidence": 0.0,
        "recommended_action": "escalate",
        "category": response.get("category", "unknown"),
        "chain_of_thought": response.get("chain_of_thought", {}),
    }

    # Clamp confidence to [0, 1]
    try:
        conf = float(response.get("confidence", 0))
        validated["confidence"] = max(0.0, min(1.0, conf))
    except (TypeError, ValueError):
        validated["confidence"] = 0.0

    # Validate action
    action = response.get("recommended_action", "escalate")
    if action not in ("auto_resolve", "escalate", "needs_data"):
        action = "escalate"
    validated["recommended_action"] = action

    # Ensure evidence is a list of strings
    if not isinstance(validated["evidence"], list):
        validated["evidence"] = [str(validated["evidence"])]
    validated["evidence"] = [str(e) for e in validated["evidence"]]

    # Validate chain of thought structure
    cot = validated.get("chain_of_thought", {})
    if not isinstance(cot, dict):
        cot = {}
    validated["chain_of_thought"] = {
        "fact_gathering": cot.get("fact_gathering", []),
        "hypotheses": cot.get("hypotheses", []),
        "evidence_validation": cot.get("evidence_validation", {}),
        "scoring_rationale": cot.get("scoring_rationale", ""),
    }

    return validated


async def investigate_exception(db: AsyncSession, exception_id: int) -> Investigation | None:
    """
    Investigate a single exception using the LLM with 4-step chain.

    Implements:
    - Context assembly
    - LLM call with chain-of-thought
    - Response validation
    - Guardrails (bounded, gated)
    - Graceful degradation
    - Full audit trail
    """
    # Load exception
    result = await db.execute(
        select(Exception_).where(Exception_.id == exception_id)
    )
    exc = result.scalar_one_or_none()
    if not exc:
        return None

    # Don't re-investigate already resolved exceptions
    if exc.status in ("resolved", "escalated"):
        return None

    # Mark as investigating
    old_status = exc.status
    exc.status = "investigating"
    await db.flush()

    await log_audit(db, "exception", str(exception_id), "investigation_started", "ai_investigator",
                    old_state={"status": old_status}, new_state={"status": "investigating"})

    start_time = time.time()
    
    # -------------------------------------------------------------------------
    # DETERMINISTIC SHORT-CIRCUIT
    # Skip LLM for exceptions perfectly explained by deterministic rules.
    # -------------------------------------------------------------------------
    deterministic_types = ["fee_discrepancy", "rounding_difference", "timing_mismatch"]
    is_small_mismatch = exc.type == "amount_mismatch" and exc.amount_at_risk <= 5000  # 50 INR
    
    if exc.type in deterministic_types or is_small_mismatch:
        latency_ms = int((time.time() - start_time) * 1000)
        exc.status = "resolved"
        exc.resolved_at = datetime.utcnow()
        
        root_cause = f"Deterministic resolution for {exc.type}"
        explanation = f"Exception of type {exc.type} fully explained by deterministic reconciliation rules. No AI investigation required."
        
        investigation = Investigation(
            exception_id=exception_id,
            root_cause=root_cause,
            evidence={"points": ["Deterministic rule match"]},
            confidence=1.0,
            recommended_action="auto_resolve",
            explanation=explanation,
            resolution_type="auto",
            resolved_by="system",
            model_used="deterministic_engine",
            prompt_tokens=0,
            response_tokens=0,
            latency_ms=latency_ms,
            chain_of_thought={"fact_gathering": [], "hypotheses": [], "evidence_validation": {}, "scoring_rationale": "Deterministic logic"},
            agent_decision_trace={
                "model_name": "deterministic_engine",
                "final_decision": "auto_resolve",
                "reason": f"Matched deterministic rule: {exc.type}"
            }
        )
        db.add(investigation)
        await db.flush()
        
        await log_audit(
            db, "exception", str(exception_id),
            action="investigated",
            actor="deterministic_engine",
            new_state={
                "status": "resolved",
                "confidence": 1.0,
                "recommended_action": "auto_resolve",
                "final_action": "auto_resolve",
                "root_cause": root_cause,
                "model": "deterministic_engine",
                "latency_ms": latency_ms,
            },
        )
        return investigation

    try:
        # Gather context
        related_data = await _gather_related_data(db, exc)
        prompt = _build_investigation_prompt(exc, related_data)

        # Call LLM
        raw_response, model_name, prompt_tokens, response_tokens = await _call_llm(prompt)

        # Validate response
        validated = _validate_llm_response(raw_response)
        latency_ms = int((time.time() - start_time) * 1000)

        # Apply guardrails for auto-resolve decision
        can_auto_resolve = (
            validated["recommended_action"] == "auto_resolve"
            and validated["confidence"] >= settings.auto_resolve_confidence_threshold
            and exc.amount_at_risk <= settings.auto_resolve_max_amount_paise
        )

        must_escalate = exc.amount_at_risk >= settings.always_escalate_amount_paise

        if must_escalate:
            final_action = "escalate"
            resolution_type = None
            resolved_by = None
            exc.status = "escalated"
        elif can_auto_resolve:
            final_action = "auto_resolve"
            resolution_type = "auto"
            resolved_by = "system"
            exc.status = "resolved"
            exc.resolved_at = datetime.utcnow()
        else:
            final_action = "escalate"
            resolution_type = None
            resolved_by = None
            exc.status = "escalated"

        # Create investigation record
        decision_trace = {
            "model_name": model_name,
            "raw_chain_of_thought": validated["chain_of_thought"],
            "guardrails_evaluated": {
                "can_auto_resolve": can_auto_resolve,
                "must_escalate": must_escalate,
            },
            "final_decision": final_action
        }

        investigation = Investigation(
            exception_id=exception_id,
            root_cause=validated["root_cause"],
            evidence={"points": validated["evidence"]},
            confidence=validated["confidence"],
            recommended_action=validated["recommended_action"],
            explanation=f"{validated['root_cause']} (Category: {validated['category']})",
            resolution_type=resolution_type,
            resolved_by=resolved_by,
            model_used=model_name,
            prompt_tokens=prompt_tokens,
            response_tokens=response_tokens,
            latency_ms=latency_ms,
            chain_of_thought=validated["chain_of_thought"],
            agent_decision_trace=decision_trace
        )
        db.add(investigation)
        await db.flush()

        await log_audit(
            db, "exception", str(exception_id),
            action="investigated",
            actor="ai_investigator",
            new_state={
                "status": exc.status,
                "confidence": validated["confidence"],
                "recommended_action": validated["recommended_action"],
                "final_action": final_action,
                "root_cause": validated["root_cause"],
                "model": model_name,
                "latency_ms": latency_ms,
                "chain_steps": list(validated["chain_of_thought"].keys()),
                "guardrails": {
                    "can_auto_resolve": can_auto_resolve,
                    "must_escalate": must_escalate,
                    "amount_at_risk": exc.amount_at_risk,
                    "threshold": settings.auto_resolve_confidence_threshold,
                    "max_auto_amount": settings.auto_resolve_max_amount_paise,
                },
            },
        )

        return investigation

    except ConnectionError as e:
        # GRACEFUL DEGRADATION: LLM unavailable → escalate
        latency_ms = int((time.time() - start_time) * 1000)
        exc.status = "escalated"

        error_msg = str(e)
        investigation = Investigation(
            exception_id=exception_id,
            root_cause="AI service unavailable — escalated for manual review",
            evidence={"points": [f"LLM API connection failed: {error_msg}"]},
            confidence=0.0,
            recommended_action="escalate",
            explanation="AI investigation could not be completed due to LLM service unavailability. "
                        "Exception has been escalated for manual human review.",
            resolution_type=None,
            resolved_by=None,
            model_used="none (service_unavailable)",
            prompt_tokens=0,
            response_tokens=0,
            latency_ms=latency_ms,
            chain_of_thought={"error": "LLM service unavailable", "fallback": "escalate_all"},
        )
        db.add(investigation)
        await db.flush()

        await log_audit(
            db, "exception", str(exception_id),
            action="investigation_failed",
            actor="ai_investigator",
            new_state={
                "status": "escalated",
                "reason": "llm_unavailable",
                "latency_ms": latency_ms,
            },
        )

        return investigation

    except Exception as e:
        # Any other error → escalate with error details
        latency_ms = int((time.time() - start_time) * 1000)
        exc.status = "escalated"

        investigation = Investigation(
            exception_id=exception_id,
            root_cause=f"Investigation error: {str(e)}",
            evidence={"points": [traceback.format_exc()[:500]]},
            confidence=0.0,
            recommended_action="escalate",
            explanation=f"AI investigation encountered an error: {str(e)}. "
                        "Exception has been escalated for manual review.",
            resolution_type=None,
            resolved_by=None,
            model_used="none (error)",
            prompt_tokens=0,
            response_tokens=0,
            latency_ms=latency_ms,
            chain_of_thought={"error": str(e), "fallback": "escalate_all"},
        )
        db.add(investigation)
        await db.flush()

        await log_audit(
            db, "exception", str(exception_id),
            action="investigation_error",
            actor="ai_investigator",
            new_state={"status": "escalated", "error": str(e)},
        )

        return investigation


async def investigate_all_exceptions(db: AsyncSession, run_id: int) -> list[Investigation]:
    """
    Investigate all detected exceptions from a reconciliation run.
    Returns list of Investigation records.
    """
    result = await db.execute(
        select(Exception_)
        .where(Exception_.run_id == run_id, Exception_.status == "detected")
    )
    exceptions = result.scalars().all()

    investigations = []
    for exc in exceptions:
        inv = await investigate_exception(db, exc.id)
        if inv:
            investigations.append(inv)

    return investigations
