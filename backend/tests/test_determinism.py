"""
Determinism Test — Prove identical input batches always produce identical results.

Runs reconciliation multiple times on the exact same synthetic dataset and
asserts that all outputs are byte-for-byte identical.
"""

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.models import Base, Exception_
from app.utils.synthetic_data import generate_dataset
from app.services.reconciliation_engine import run_reconciliation
from app.models import Transaction, Settlement, BankStatement


async def _populate_and_run(engine) -> dict:
    """Populate a fresh DB and run reconciliation, returning a summary dict."""
    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_maker() as session:
        data = generate_dataset()

        # Insert in order: settlements first (FK target), then transactions, then bank
        for s in data["settlements"]:
            session.add(Settlement(**s))
        await session.flush()

        for t in data["transactions"]:
            session.add(Transaction(**{**t, "source": "csv_batch"}))
        await session.flush()

        for b in data["bank_statements"]:
            session.add(BankStatement(**b))
        await session.flush()

        await session.commit()

        # Run reconciliation
        run = await run_reconciliation(session, trigger_type="determinism_test")
        await session.commit()

        # Collect exception details
        from sqlalchemy import select
        exc_result = await session.execute(
            select(Exception_).where(Exception_.run_id == run.id)
        )
        exceptions = exc_result.scalars().all()

        # Build a sorted, hashable representation of exceptions
        exc_details = sorted(
            [
                {
                    "type": e.type,
                    "amount_at_risk": e.amount_at_risk,
                    "severity": e.severity,
                }
                for e in exceptions
            ],
            key=lambda x: (x["type"], x["amount_at_risk"]),
        )

        return {
            "total_records": run.total_records,
            "matched": run.matched,
            "mismatched": run.mismatched,
            "unmatched": run.unmatched,
            "exceptions_count": run.exceptions_count,
            "exception_types": run.summary.get("exception_types", {}),
            "exception_details": exc_details,
        }


@pytest.mark.asyncio
async def test_determinism_two_runs():
    """
    Prove that running reconciliation twice on identical data produces
    identical results (matched, mismatched, unmatched, exceptions).
    """
    # Run 1
    engine1 = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine1.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    result1 = await _populate_and_run(engine1)
    await engine1.dispose()

    # Run 2
    engine2 = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine2.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    result2 = await _populate_and_run(engine2)
    await engine2.dispose()

    # Assert identical top-level metrics
    assert result1["total_records"] == result2["total_records"], \
        f"total_records: {result1['total_records']} != {result2['total_records']}"
    assert result1["matched"] == result2["matched"], \
        f"matched: {result1['matched']} != {result2['matched']}"
    assert result1["mismatched"] == result2["mismatched"], \
        f"mismatched: {result1['mismatched']} != {result2['mismatched']}"
    assert result1["unmatched"] == result2["unmatched"], \
        f"unmatched: {result1['unmatched']} != {result2['unmatched']}"
    assert result1["exceptions_count"] == result2["exceptions_count"], \
        f"exceptions_count: {result1['exceptions_count']} != {result2['exceptions_count']}"

    # Assert identical exception type distribution
    assert result1["exception_types"] == result2["exception_types"], \
        f"exception_types differ:\n  Run1: {result1['exception_types']}\n  Run2: {result2['exception_types']}"

    # Assert identical exception details (sorted)
    assert result1["exception_details"] == result2["exception_details"], \
        "Exception details (type + amount_at_risk) differ between runs"


@pytest.mark.asyncio
async def test_determinism_triple_confirmation():
    """
    Triple-run determinism: run 3 times and confirm all are identical.
    """
    results = []
    for i in range(3):
        engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        result = await _populate_and_run(engine)
        results.append(result)
        await engine.dispose()

    # All three runs must produce identical output
    for i in range(1, 3):
        assert results[0]["total_records"] == results[i]["total_records"]
        assert results[0]["matched"] == results[i]["matched"]
        assert results[0]["mismatched"] == results[i]["mismatched"]
        assert results[0]["unmatched"] == results[i]["unmatched"]
        assert results[0]["exceptions_count"] == results[i]["exceptions_count"]
        assert results[0]["exception_types"] == results[i]["exception_types"]
        assert results[0]["exception_details"] == results[i]["exception_details"]
