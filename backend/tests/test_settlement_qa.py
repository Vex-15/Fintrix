import pytest

from app.services.settlement_qa import ask_question, _deterministic_query, _validate_sql


def test_common_questions_have_safe_deterministic_queries():
    for question in (
        "Show unresolved exceptions",
        "Total GST deducted today",
        "Top 5 fee discrepancies",
        "How many auto-resolved?",
        "Settlement summary",
        "How many failed payments today?",
        "Total refunds",
        "Latest reconciliation accuracy",
        "Show high severity exceptions",
    ):
        query = _deterministic_query(question)
        assert query is not None
        assert _validate_sql(query[0])


@pytest.mark.asyncio
async def test_unresolved_exception_question_returns_rows(populated_db):
    db_session, _ = populated_db

    result = await ask_question(db_session, "Show unresolved exceptions")

    assert result["source"] == "deterministic"
    assert result["sql"].startswith("SELECT")
    assert isinstance(result["data"], list)
    assert "unresolved exceptions" in result["answer"]


@pytest.mark.asyncio
async def test_gst_question_returns_aggregate(populated_db):
    db_session, _ = populated_db

    result = await ask_question(db_session, "Total GST deducted today")

    assert result["source"] == "deterministic"
    assert len(result["data"]) == 1
    assert "total_gst_rupees" in result["data"][0]


def test_today_query_has_a_date_boundary():
    query = _deterministic_query("Total GST deducted today")

    assert query is not None
    assert "CURRENT_DATE" in query[0]


@pytest.mark.asyncio
async def test_operational_questions_return_real_data(populated_db):
    db_session, _ = populated_db

    failed = await ask_question(db_session, "How many failed payments today?")
    refunds = await ask_question(db_session, "Total refunds")
    reconciliation = await ask_question(db_session, "Latest reconciliation accuracy")

    assert failed["source"] == "deterministic"
    assert refunds["source"] == "deterministic"
    assert reconciliation["source"] == "deterministic"
    assert "failed" in failed["answer"].lower()
    assert "total_refunded_rupees" in refunds["data"][0]
