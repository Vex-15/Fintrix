"""
Settlement Q&A Agent — Natural-language question answering over financial data.

Converts user questions into safe SELECT-only SQL via Groq,
executes them against the DB, and returns a prose summary.

Graceful degradation: if Groq is unavailable, returns pre-computed
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
8. When asked to count or list exceptions/transactions/etc., include ALL records regardless of status unless the user specifically asks about a particular status (e.g. don't add "WHERE status = 'detected'" unless requested).

RESPOND IN THIS EXACT JSON FORMAT:
{{"sql": "SELECT ...", "explanation": "This query ..."}}
"""

# Disallowed SQL keywords (case-insensitive)
_FORBIDDEN_KEYWORDS = re.compile(
    r'\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|GRANT|REVOKE|EXEC|EXECUTE|INTO)\b',
    re.IGNORECASE,
)


def _deterministic_query(question: str) -> tuple[str, str] | None:
    """Map high-signal operational questions to known safe queries.

    These paths make the agent useful without an LLM key and avoid asking an
    LLM to rediscover straightforward dashboard data.
    """
    normalized = question.lower().strip()
    date_filter = " AND date(created_at) = CURRENT_DATE" if "today" in normalized else ""

    if "unresolved" in normalized or "open exception" in normalized or "pending exception" in normalized:
        return (
            "SELECT id, type, severity, status, amount_at_risk / 100.0 AS amount_at_risk_rupees, created_at "
            "FROM exceptions WHERE status NOT IN ('resolved') ORDER BY amount_at_risk DESC LIMIT 50",
            "Here are the unresolved exceptions ordered by amount at risk.",
        )

    if "auto-resolved" in normalized or "auto resolved" in normalized or "automatically resolved" in normalized:
        return (
            "SELECT COUNT(*) AS auto_resolved_count FROM investigations WHERE resolution_type = 'auto'",
            "This is the number of exceptions resolved automatically by the agent.",
        )

    if "fee discrep" in normalized or "fee mismatch" in normalized or "top fee" in normalized:
        return (
            "SELECT id, amount / 100.0 AS amount_rupees, fee / 100.0 AS fee_rupees, "
            "tax / 100.0 AS tax_rupees, settlement_id, created_at "
            "FROM transactions WHERE type = 'payment' AND status = 'captured' "
            "AND fee IS NOT NULL ORDER BY ABS(fee - amount * 0.02) DESC LIMIT 5",
            "Here are the five captured payments with the largest deviation from the expected 2% MDR fee.",
        )

    if "gst" in normalized or "tax" in normalized:
        return (
            "SELECT COUNT(*) AS captured_payments, "
            "SUM(tax) / 100.0 AS total_gst_rupees, "
            "SUM(fee) / 100.0 AS total_fee_rupees "
            f"FROM transactions WHERE type = 'payment' AND status = 'captured'{date_filter}",
            "This summarizes GST and fees recorded on captured payments.",
        )

    if "failed payment" in normalized or "failed transaction" in normalized:
        return (
            f"SELECT id, amount / 100.0 AS amount_rupees, method, created_at "
            f"FROM transactions WHERE type = 'payment' AND status = 'failed'{date_filter} "
            "ORDER BY created_at DESC LIMIT 50",
            "Here are the failed payment attempts for the requested period.",
        )

    if "refund" in normalized:
        return (
            f"SELECT COUNT(*) AS refund_count, SUM(amount) / 100.0 AS total_refunded_rupees "
            f"FROM transactions WHERE type = 'refund'{date_filter}",
            "This summarizes refunds recorded for the requested period.",
        )

    if "reconciliation" in normalized and ("latest" in normalized or "last" in normalized or "accuracy" in normalized):
        return (
            "SELECT id, status, total_records, matched, mismatched, unmatched, exceptions_count, "
            "ROUND(CAST(matched AS FLOAT) / NULLIF(total_records, 0) * 100, 2) AS accuracy_percent, "
            "completed_at FROM reconciliation_runs ORDER BY completed_at DESC LIMIT 1",
            "This is the latest reconciliation run with its accuracy and exception totals.",
        )

    if "high severity" in normalized or "critical exception" in normalized:
        return (
            "SELECT id, type, severity, status, amount_at_risk / 100.0 AS amount_at_risk_rupees, created_at "
            "FROM exceptions WHERE severity IN ('high', 'critical') AND status != 'resolved' "
            "ORDER BY amount_at_risk DESC LIMIT 50",
            "Here are the unresolved high-severity and critical exceptions ordered by financial exposure.",
        )

    if "settlement summary" in normalized or "settlement total" in normalized or "how many settlement" in normalized:
        return (
            "SELECT status, COUNT(*) AS settlement_count, "
            "SUM(amount) / 100.0 AS total_amount_rupees "
            "FROM settlements GROUP BY status ORDER BY total_amount_rupees DESC LIMIT 50",
            "This summarizes settlement counts and amounts by status.",
        )

    if "amount at risk" in normalized or "risk" in normalized:
        return (
            "SELECT COUNT(*) AS exception_count, "
            "SUM(amount_at_risk) / 100.0 AS amount_at_risk_rupees "
            "FROM exceptions WHERE status != 'resolved'",
            "This shows the current unresolved exception count and amount at risk.",
        )

    return None


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


def _extract_qa_json(text: str) -> dict:
    """Extract JSON object from text or markdown code block."""
    text = text.strip()
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        return json.loads(match.group(1))
    brace_start = text.find("{")
    brace_end = text.rfind("}")
    if brace_start != -1 and brace_end != -1 and brace_end > brace_start:
        return json.loads(text[brace_start:brace_end + 1])
    return json.loads(text)


async def _call_groq_qa(question: str) -> dict:
    """Call Groq API to generate SQL from a natural-language question."""
    import httpx

    prompt = f"{QA_SYSTEM_PROMPT}\n\nUser question: {question}"

    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.groq_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": settings.groq_model,
                "messages": [
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.1,
                "response_format": {"type": "json_object"},
            },
        )
        response.raise_for_status()
        data = response.json()
        content = data["choices"][0]["message"]["content"]
        return _extract_qa_json(content)


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
        select(func.count(Exception_.id)).where(
            Exception_.status == "resolved")
    )).scalar() or 0

    escalated = (await db.execute(
        select(func.count(Exception_.id)).where(
            Exception_.status == "escalated")
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
            "source": str,       # "groq" | "fallback"
        }
    """
    deterministic = _deterministic_query(question)
    if deterministic:
        sql, explanation = deterministic
        result = await db.execute(text(sql))
        data = [dict(row) for row in result.mappings().all()[:50]]
        answer = _summarize_rows(explanation, data)
        return {
            "question": question,
            "answer": answer,
            "data": data,
            "sql": sql,
            "source": "deterministic",
        }

    # Q&A is intentionally Groq-only. Gemini is used by other legacy paths,
    # but must not silently take over this agent when Groq is unavailable.
    llm_source = None
    llm_result = None

    if settings.groq_api_key:
        try:
            llm_result = await _call_groq_qa(question)
            llm_source = "groq"
        except Exception:
            pass

    if llm_result:
        try:
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
                        answer = _summarize_rows(explanation, data)
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
                        "source": llm_source or "llm",
                    }
                except Exception as e:
                    # SQL execution failed — fall through to fallback
                    return {
                        "question": question,
                        "answer": f"Generated query failed to execute: {str(e)}. "
                                  f"Explanation: {explanation}",
                        "data": [],
                        "sql": sql,
                        "source": f"{llm_source}_error" if llm_source else "llm_error",
                    }
            elif sql is None:
                # LLM explicitly said it can't answer
                return {
                    "question": question,
                    "answer": explanation or "I cannot answer this question with the available data.",
                    "data": [],
                    "sql": None,
                    "source": llm_source or "llm",
                }
            else:
                # SQL was generated but failed validation — blocked
                return {
                    "question": question,
                    "answer": "The generated query was blocked by safety validation. "
                              "Only SELECT queries are permitted.",
                    "data": [],
                    "sql": None,
                    "source": f"{llm_source}_blocked" if llm_source else "llm_blocked",
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


def _summarize_rows(explanation: str, data: list[dict]) -> str:
    """Turn query output into an operator-friendly, grounded answer."""
    if not data:
        return f"{explanation} No results found."

    row = data[0]
    if len(data) == 1:
        details = ", ".join(
            f"{key.replace('_', ' ')}: {value}"
            for key, value in row.items()
            if value is not None
        )
        return f"{explanation} {details}."
    return f"{explanation} Found {len(data)} result(s); the highest-priority item is {row.get('id', 'the first result')}."
