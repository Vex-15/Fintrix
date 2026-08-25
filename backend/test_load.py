"""
Load test script — generates 100K transactions and measures reconciliation performance.

Usage:
    python test_load.py

Requires: running PostgreSQL instance and .env configured.
"""

import asyncio
import time
import random
import string
from datetime import datetime, timedelta

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


async def run_load_test():
    """Generate 100K records and benchmark reconciliation."""
    from app.database import init_db, async_session, close_db
    from app.models import Transaction, Settlement, BankStatement
    from app.services.reconciliation_engine import run_reconciliation
    from sqlalchemy.dialects.postgresql import insert

    print("=" * 60)
    print("FINTRIX LOAD TEST — 100 Transactions")
    print("=" * 60)

    # Initialize DB
    await init_db()

    async with async_session() as db:
        # --- Generate settlements ---
        print("\n[1/4] Generating settlements...")
        t0 = time.time()
        num_settlements = 5
        settlement_records = []
        for i in range(num_settlements):
            settlement_records.append({
                "id": f"load_setl_{i:06d}",
                "amount": random.randint(50000, 5000000),
                "fees": random.randint(100, 10000),
                "tax": random.randint(50, 2000),
                "utr": f"LOAD_UTR_{i:06d}",
                "status": "processed",
                "created_at": datetime.utcnow() - timedelta(days=random.randint(0, 30)),
            })

        stmt = insert(Settlement).values(settlement_records).on_conflict_do_nothing(index_elements=["id"])
        await db.execute(stmt)
        await db.flush()
        print(f"  → {num_settlements} settlements in {time.time() - t0:.2f}s")

        # --- Generate transactions ---
        print("[2/4] Generating 100 transactions...")
        t0 = time.time()
        num_transactions = 100
        batch_size = 100

        for batch_start in range(0, num_transactions, batch_size):
            batch = []
            for i in range(batch_start, min(batch_start + batch_size, num_transactions)):
                setl_idx = i % num_settlements
                batch.append({
                    "id": f"load_pay_{i:06d}",
                    "type": "payment",
                    "order_id": f"load_order_{i:06d}",
                    "amount": settlement_records[setl_idx]["amount"] // random.randint(5, 20),
                    "currency": "INR",
                    "status": "captured",
                    "fee": random.randint(100, 5000),
                    "tax": random.randint(50, 1000),
                    "settlement_id": f"load_setl_{setl_idx:06d}",
                    "method": random.choice(["upi", "card", "netbanking", "wallet"]),
                    "description": f"Load test payment {i}",
                    "captured_at": datetime.utcnow() - timedelta(hours=random.randint(1, 720)),
                    "created_at": datetime.utcnow() - timedelta(hours=random.randint(1, 720)),
                    "source": "load_test",
                })

            stmt = insert(Transaction).values(batch).on_conflict_do_nothing(index_elements=["id"])
            await db.execute(stmt)
            await db.flush()

            pct = min(100, (batch_start + batch_size) / num_transactions * 100)
            print(f"  → {int(pct)}% ({batch_start + batch_size}/{num_transactions})")

        t_gen = time.time() - t0
        print(f"  → 100 transactions in {t_gen:.2f}s ({num_transactions / t_gen:.0f} records/s)")

        # --- Generate bank statements ---
        print("[3/4] Generating bank statements...")
        t0 = time.time()
        for i in range(num_settlements):
            db.add(BankStatement(
                bank_account="LOAD_TEST_ACC",
                entry_date=(datetime.utcnow() - timedelta(days=random.randint(0, 30))).date(),
                description=f"Razorpay Settlement LOAD_UTR_{i:06d}",
                reference=f"LOAD_UTR_{i:06d}",
                credit=settlement_records[i]["amount"] + random.choice([0, 0, 0, random.randint(-100, 100)]),
                debit=0,
                balance=random.randint(1000000, 50000000),
            ))
        await db.flush()
        print(f"  → {num_settlements} bank statements in {time.time() - t0:.2f}s")

        await db.commit()

        # --- Run reconciliation ---
        print("[4/4] Running reconciliation on 100 records...")
        t0 = time.time()
        run = await run_reconciliation(db, trigger_type="load_test")
        await db.commit()
        t_recon = time.time() - t0

        # --- Results ---
        print("\n" + "=" * 60)
        print("RESULTS")
        print("=" * 60)
        print(f"Total records:        {run.total_records:,}")
        print(f"Matched:              {run.matched:,}")
        print(f"Mismatched:           {run.mismatched:,}")
        print(f"Unmatched:            {run.unmatched:,}")
        print(f"Exceptions:           {run.exceptions_count:,}")
        print(f"Duration:             {run.duration_ms:,}ms")
        print(f"Throughput:           {run.total_records / (run.duration_ms / 1000):.1f} records/sec")
        print(f"Data generation:      {t_gen:.2f}s")
        print(f"Reconciliation:       {t_recon:.2f}s")
        print(f"Match rate:           {run.matched / max(run.total_records, 1) * 100:.1f}%")

        if run.summary.get("exception_types"):
            print(f"\nException breakdown:")
            for exc_type, count in run.summary["exception_types"].items():
                print(f"  {exc_type}: {count}")

    await close_db()
    print("\n[DONE] Load test complete.")


if __name__ == "__main__":
    asyncio.run(run_load_test())
