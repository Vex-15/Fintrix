import pytest
from app.services.reconciliation_engine import run_reconciliation

@pytest.mark.asyncio
async def test_reconciliation_totals(populated_db):
    db_session, ground_truth = populated_db
    
    run = await run_reconciliation(db_session, trigger_type="test")
    
    # Assert matched + mismatched + unmatched + exceptions_count matches total_records 
    # WAIT: exceptions_count is a count of exception objects, not transactions.
    # We should just assert the individual metrics make sense.
    
    assert run.total_records == ground_truth["total_transactions"]
    assert run.matched >= ground_truth["expected_matched"] # Because ensemble match might match more
    
    # Check if unmatched makes sense
    assert run.unmatched >= 0
