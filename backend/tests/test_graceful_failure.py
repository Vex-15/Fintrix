import pytest
from app.utils.csv_parser import parse_transactions_csv
from app.services.ai_investigator import investigate_exception
from app.models import Exception_, Investigation
from unittest.mock import patch

def test_malformed_csv_parsing():
    # A CSV with one valid row and one malformed row
    csv_content = """id,type,amount,currency,status
pay_1,payment,10000,INR,captured
pay_2,payment,INVALID_AMOUNT,INR,captured
pay_3,payment,20000,INR,captured
"""
    records, errors = parse_transactions_csv(csv_content)
    
    assert len(records) == 2, "Should parse the 2 valid rows"
    assert len(errors) == 1, "Should report 1 error"
    assert "pay_2" in errors[0] or "Row 2" in errors[0] or "Row 3" in errors[0] # Row 3 because of header

@pytest.mark.asyncio
async def test_llm_unreachable_fallback(populated_db):
    db_session, _ = populated_db
    
    # Create a dummy exception with no rule match
    exc = Exception_(
        run_id=1,
        type="missing_bank_entry", # No rule covers this
        severity="high",
        status="detected",
        amount_at_risk=50000,
        context={}
    )
    db_session.add(exc)
    await db_session.flush()
    
    # Mock LLM call to raise ConnectionError
    with patch("app.services.ai_investigator._call_llm", side_effect=ConnectionError("Mocked timeout")):
        inv = await investigate_exception(db_session, exc.id)
        
        assert inv is not None
        assert exc.status == "escalated"
        assert "escalate" in inv.recommended_action
        assert "unavailable" in inv.root_cause.lower() or "connection" in inv.root_cause.lower() or "error" in inv.root_cause.lower()
        assert inv.confidence == 0.0
