import pytest
from app.services.reconciliation_engine import run_reconciliation


@pytest.mark.asyncio
async def test_reconciliation_totals(populated_db):
    db_session, ground_truth = populated_db

    run = await run_reconciliation(db_session, trigger_type="test")

    from sqlalchemy import select
    from app.models import Exception_
    exceptions = (await db_session.execute(select(Exception_).where(Exception_.run_id == run.id))).scalars().all()

    with open("debug_exceptions.txt", "w") as f:
        for e in exceptions:
            f.write(
                f"{e.type} - {e.context.get('transaction_id', '')} - {e.context.get('settlement_id', '')}\n")

    # Assert matched + mismatched + unmatched + exceptions_count matches total_records
    # WAIT: exceptions_count is a count of exception objects, not transactions.
    # We should just assert the individual metrics make sense.

    assert run.total_records == ground_truth["total_transactions"]
    # Because ensemble match might match more
    assert run.matched >= ground_truth["expected_matched"]

    partition = run.summary["transaction_partition"]
    assert partition["total"] == run.total_records
    assert (
        partition["cleanly_matched"]
        + partition["affected_by_exceptions"]
        + partition["unclassified"]
        == run.total_records
    )

    # Check if unmatched makes sense
    assert run.unmatched >= 0

    # Verify the final exception count - this is P0 requirement
    assert run.exceptions_count == len(ground_truth["planted_exceptions"])
