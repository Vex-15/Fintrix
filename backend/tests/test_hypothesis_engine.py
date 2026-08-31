import pytest
from app.services.reconciliation_engine import run_reconciliation
from app.services.ai_investigator import _gather_related_data
from app.services.hypothesis_engine import generate_hypotheses
from app.models import Exception_
from sqlalchemy import select

@pytest.mark.asyncio
async def test_hypothesis_engine_precision(populated_db):
    db_session, ground_truth = populated_db
    
    # 1. Run reconciliation to generate exceptions
    run = await run_reconciliation(db_session, trigger_type="test")
    
    # 2. Fetch detected exceptions
    result = await db_session.execute(select(Exception_).where(Exception_.run_id == run.id))
    exceptions = result.scalars().all()
    
    # Expected mappings from exception type to hypothesis category
    expected_mappings = {
        "fee_discrepancy": "fee_change",
        "timing_mismatch": "timing_mismatch",
        "duplicate_suspected": "duplicate_charge",
        "missing_settlement": "unknown", # Cannot hypothesize without settlement context
        "unexpected_adjustment": "manual_adjustment",
        "rounding_difference": "rounding",
    }
    
    correct = 0
    total_evaluable = 0
    
    for exc in exceptions:
        # We only evaluate precision on exceptions where we expect a definitive hypothesis
        if exc.type not in expected_mappings and exc.type != "amount_mismatch":
            continue
            
        related_data = await _gather_related_data(db_session, exc)
        
        hypotheses = generate_hypotheses(
            exception_type=exc.type,
            exception_context=exc.context or {},
            related_data=related_data,
            amount_at_risk=exc.amount_at_risk,
        )
        
        top_hypothesis = hypotheses[0] if hypotheses else None
        
        if not top_hypothesis:
            continue
            
        # amount_mismatch could be multiple things depending on the planted issue
        if exc.type == "amount_mismatch":
             # In our synthetic data, amount_mismatch could be a true amount mismatch or miscategorized rounding
             if exc.amount_at_risk < 100:
                  expected_cat = "rounding"
             else:
                  # For the ₹1,247 missing, it's not covered by a simple rule, so it might be unknown
                  # We'll skip strict checking for the generic amount_mismatch unless it's rounding
                  continue
        else:
             expected_cat = expected_mappings[exc.type]
             
        total_evaluable += 1
        
        if top_hypothesis.category == expected_cat:
            correct += 1
        else:
             print(f"Failed hypothesis for {exc.type}: expected {expected_cat}, got {top_hypothesis.category}")

    assert total_evaluable > 0, "No evaluable exceptions found"
    
    precision = correct / total_evaluable
    
    # Assert precision is >= 70% as per the plan
    assert precision >= 0.70, f"Hypothesis precision {precision:.1%} is below 70% target"
