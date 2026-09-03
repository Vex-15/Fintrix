"""
Settlement Q&A Agent — Natural-language question answering over financial data.

Converts user questions into safe SELECT-only SQL via Gemini,
executes them against the DB, and returns a prose summary.

Graceful degradation: if Gemini is unavailable, returns pre-computed
aggregate statistics to answer common questions.
"""

import json
import re
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text, select, func

from app.config import settings
from app.models import (
    Transaction, Settlement, BankStatement,
    Exception_, Investigation, ReconciliationRun,
)

# Schema description for the LLM — just the relevant columns, no secrets
DB_SCHEMA = """
Tables and columns (all monetary amounts in paise, ₹1 = 100 paise):

transactions:
  id (string PK), type (payment|refund|adjustment), order_id, amount (bigint paise),
  currency, status (created|authorized|captured|failed|refunded), fee (bigint),
  tax (bigint), settlement_id (FK), method (card|upi|netbanking|wallet),
  description, captured_at, created_at, merchant_id

settlements:
  id (string PK), amount (bigint paise), fees (bigint), tax (bigint),
  utr (string bank reference), status (created|processed|failed),
  created_at, merchant_id

bank_statements:
  id (int PK), bank_account, entry_date (date), description, reference (UTR),
  credit (bigint paise), debit (bigint paise), balance, merchant_id

exceptions:
  id (int PK), run_id (FK), type (amount_mismatch|fee_discrepancy|missing_settlement|
  missing_bank_entry|duplicate_suspected|timing_mismatch|unexpected_adjustment|rounding_difference),
  severity (low|medium|high|critical), status (detected|investigating|resolved|escalated),
  amount_at_risk (bigint paise), context (JSON), created_at, resolved_at, merchant_id

investigations:
  id (int PK), exception_id (FK), root_cause (text), evidence (JSON),
  confidence (float 0-1), recommended_action (auto_resolve|escalate|needs_data),
  explanation (text), resolution_type (auto|manual), resolved_by,
  model_used, latency_ms, created_at

reconciliation_runs:
  id (int PK), started_at, completed_at, status (running|completed|failed),
  trigger_type, total_records, matched, mismatched, unmatched,
  exceptions_count, duration_ms, summary (JSON), merchant_id
"""

QA_SYSTEM_PROMPT = f"""You are a financial data analyst for a payment reconciliation system.
Given a user question about settlements, transactions, exceptions, or reconciliation data,
generate a safe SQL SELECT query to answer it.

{DB_SCHEMA}

RULES:
1. Output ONLY a JSON object with two keys: "sql" and "explanation"
2. The "sql" must be a SELECT query ONLY — no INSERT, UPDATE, DELETE, DROP, ALTER, CREATE, or TRUNCATE
3. Use standard SQL compatible with SQLite
4. For monetary amounts, divide by 100 to show rupees (e.g., amount/100 AS amount_rupees)
5. Limit results to 50 rows max
6. The "explanation" should be a brief sentence describing what the query does
7. If you cannot answer the question with the available schema, set sql to null and explain why

RESPOND IN THIS EXACT JSON FORMAT:
{{"sql": "SELECT ...", "explanation": "This query ..."}}
"""

# Disallowed SQL keywords (case-insensitive)
_FORBIDDEN_KEYWORDS = re.compile(
    r'\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|GRANT|REVOKE|EXEC|EXECUTE|INTO)\b',
    re.IGNORECASE,
)


def _validate_sql(sql: str) -> bool:
    """Validate that the SQL is a safe SELECT-only query."""
    if not sql or not sql.strip():
        return False
    stripped = sql.strip().rstrip(";").strip()
    if not stripped.upper().startswith("SELECT"):
        return False
    if _FORBIDDEN_KEYWORDS.search(stripped):
        return False
    # Block semicolons in the middle (potential injection)
    if ";" in stripped:
        return False
    return True


async def _call_gemini_qa(question: str) -> dict:
    """Call Gemini to generate SQL from a natural-language question."""
    import google.generativeai as genai

    genai.configure(api_key=settings.gemini_api_key)
    model = genai.GenerativeModel("gemini-2.0-flash")

    prompt = f"{QA_SYSTEM_PROMPT}\n\nUser question: {question}"

    response = model.generate_content(
        [{"role": "user", "parts": [{"text": prompt}]}],
        generation_config=genai.types.GenerationConfig(
            response_mime_type="application/json",
            temperature=0.1,
        ),
    )

    text_resp = response.text.strip()
    return json.loads(text_resp)


async def _get_aggregate_stats(db: AsyncSession) -> dict:
    """Pre-computed aggregate statistics for fallback answers."""
    total_txns = (await db.execute(
        select(func.count(Transaction.id))
    )).scalar() or 0

    total_settlements = (await db.execute(
        select(func.count(Settlement.id))
    )).scalar() or 0

    total_exceptions = (await db.execute(
        select(func.count(Exception_.id))
    )).scalar() or 0

    resolved = (await db.execute(
        select(func.count(Exception_.id)).where(Exception_.status == "resolved")
    )).scalar() or 0

    escalated = (await db.execute(
        select(func.count(Exception_.id)).where(Exception_.status == "escalated")
    )).scalar() or 0

    total_at_risk = (await db.execute(
        select(func.sum(Exception_.amount_at_risk))
    )).scalar() or 0

    total_settled = (await db.execute(
        select(func.sum(Settlement.amount))
    )).scalar() or 0

    latest_run = (await db.execute(
        select(ReconciliationRun)
        .where(ReconciliationRun.status == "completed")
        .order_by(ReconciliationRun.completed_at.desc())
        .limit(1)
    )).scalar_one_or_none()

    avg_confidence = (await db.execute(
        select(func.avg(Investigation.confidence))
    )).scalar() or 0

    exc_by_type = dict((await db.execute(
        select(Exception_.type, func.count(Exception_.id))
        .group_by(Exception_.type)
    )).all())

    exc_by_severity = dict((await db.execute(
        select(Exception_.severity, func.count(Exception_.id))
        .group_by(Exception_.severity)
    )).all())

    return {
        "total_transactions": total_txns,
        "total_settlements": total_settlements,
        "total_exceptions": total_exceptions,
        "resolved_exceptions": resolved,
        "escalated_exceptions": escalated,
        "total_amount_at_risk_paise": total_at_risk,
        "total_amount_at_risk_rupees": round(total_at_risk / 100, 2),
        "total_settled_amount_paise": total_settled,
        "total_settled_amount_rupees": round(total_settled / 100, 2),
        "average_investigation_confidence": round(avg_confidence, 3) if avg_confidence else None,
        "exceptions_by_type": exc_by_type,
        "exceptions_by_severity": exc_by_severity,
        "latest_run": {
            "id": latest_run.id,
            "matched": latest_run.matched,
            "total_records": latest_run.total_records,
            "exceptions_count": latest_run.exceptions_count,
            "duration_ms": latest_run.duration_ms,
        } if latest_run else None,
    }


async def ask_question(db: AsyncSession, question: str) -> dict:
    """
    Answer a natural-language question about settlement/reconciliation data.

    Returns:
        {
            "question": str,
            "answer": str,       # Prose answer
            "data": list[dict],  # Raw query results
            "sql": str | None,   # Generated SQL (if LLM was used)
            "source": str,       # "gemini" | "fallback"
        }
    """
    # Try Gemini path first
    if settings.gemini_api_key:
        try:
            llm_result = await _call_gemini_qa(question)
            sql = llm_result.get("sql")
            explanation = llm_result.get("explanation", "")

            if sql and _validate_sql(sql):
                # Execute the query
                try:
                    result = await db.execute(text(sql))
                    rows = result.mappings().all()
                    data = [dict(row) for row in rows[:50]]

                    # Generate prose answer from data
                    if data:
                        answer = f"{explanation} Found {len(data)} result(s)."
                        if len(data) == 1:
                            # Single result — include values in answer
                            row = data[0]
                            details = ", ".join(
                                f"{k}: {v}" for k, v in row.items()
                                if v is not None
                            )
                            answer = f"{explanation} Result: {details}."
                    else:
                        answer = f"{explanation} No results found."

                    return {
                        "question": question,
                        "answer": answer,
                        "data": data,
                        "sql": sql,
                        "source": "gemini",
                    }
                except Exception as e:
                    # SQL execution failed — fall through to fallback
                    return {
                        "question": question,
                        "answer": f"Generated query failed to execute: {str(e)}. "
                                  f"Explanation: {explanation}",
                        "data": [],
                        "sql": sql,
                        "source": "gemini_error",
                    }
            elif sql is None:
                # LLM explicitly said it can't answer
                return {
                    "question": question,
                    "answer": explanation or "I cannot answer this question with the available data.",
                    "data": [],
                    "sql": None,
                    "source": "gemini",
                }
            else:
                # SQL was generated but failed validation — blocked
                return {
                    "question": question,
                    "answer": "The generated query was blocked by safety validation. "
                              "Only SELECT queries are permitted.",
                    "data": [],
                    "sql": None,
                    "source": "gemini_blocked",
                }

        except Exception:
            pass  # Fall through to fallback

    # Fallback: return pre-computed stats
    stats = await _get_aggregate_stats(db)

    answer_lines = [
        f"Here's a summary of the current data (LLM unavailable for custom queries):",
        f"• Transactions: {stats['total_transactions']}",
        f"• Settlements: {stats['total_settlements']} (₹{stats['total_settled_amount_rupees']:,.2f} total)",
        f"• Exceptions: {stats['total_exceptions']} "
        f"({stats['resolved_exceptions']} resolved, {stats['escalated_exceptions']} escalated)",
        f"• Amount at Risk: ₹{stats['total_amount_at_risk_rupees']:,.2f}",
    ]

    if stats["exceptions_by_type"]:
        answer_lines.append("• Exception types: " + ", ".join(
            f"{t}: {c}" for t, c in stats["exceptions_by_type"].items()
        ))

    if stats.get("average_investigation_confidence"):
        answer_lines.append(
            f"• Average AI confidence: {stats['average_investigation_confidence']:.1%}"
        )

    return {
        "question": question,
        "answer": "\n".join(answer_lines),
        "data": [stats],
        "sql": None,
        "source": "fallback",
    }
