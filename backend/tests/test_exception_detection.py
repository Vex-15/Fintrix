import pytest
from app.services.reconciliation_engine import run_reconciliation
from app.models import Exception_
from sqlalchemy import select

@pytest.mark.asyncio
async def test_exception_detection_counts_and_types(populated_db):
    db_session, ground_truth = populated_db
    
    # Run the deterministic engine
    run = await run_reconciliation(db_session, trigger_type="test")
    
    # Assert total exceptions detected is at least what was planted
    assert run.exceptions_count >= len(ground_truth["planted_exceptions"])
    
    # Assert breakdown matches
    planted_counts = ground_truth["exception_counts"]
    detected_counts = run.summary.get("exception_types", {})
    
    for exc_type, count in planted_counts.items():
        assert detected_counts.get(exc_type, 0) >= count, f"Missed exceptions of type {exc_type}"

@pytest.mark.asyncio
async def test_all_planted_exceptions_are_detected(populated_db):
    db_session, ground_truth = populated_db
    
    run = await run_reconciliation(db_session, trigger_type="test")
    
    # Get all created exceptions
    result = await db_session.execute(select(Exception_).where(Exception_.run_id == run.id))
    exceptions = result.scalars().all()
    
    planted = ground_truth["planted_exceptions"]
    
    # Build a set of (type, related_txn/setl_id) from detected to match against planted
    detected_signatures = []
    for e in exceptions:
        ctx = e.context or {}
        # Try to find the primary ID this exception is about
        primary_id = (
            ctx.get("transaction_id") or 
            ctx.get("settlement_id") or 
            ctx.get("original_id") or # For duplicates
            ctx.get("payment_ids", [None])[0] # First payment id
        )
        if primary_id:
            detected_signatures.append((e.type, primary_id))
            
        # For duplicates, let's also add a signature that matches the planted format
        if e.type == "duplicate_suspected" and "original_id" in ctx and "duplicate_id" in ctx:
            detected_signatures.append((e.type, f"{ctx['original_id']},{ctx['duplicate_id']}"))

    # Verify every planted exception has a corresponding detected exception
    for p in planted:
        p_type = p["type"]
        p_id = p["transaction_id"]
        
        # Check if (p_type, p_id) is in detected_signatures
        match = any(t == p_type and (i == p_id or i in p_id or p_id in str(i)) for t, i in detected_signatures)
        
        # Rounding difference planted ID is 'setl_010', amount_mismatch is 'setl_008'
        if not match:
             assert False, f"Failed to detect planted exception: {p}"
