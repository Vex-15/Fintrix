"""
Synthetic data generator for the Fintrix evaluation dataset.

Produces exactly 60 transaction records with planted discrepancies across these categories:
  - 34  clean matches  (payment → settlement → bank, everything reconciles)
  -  4  fee discrepancies  (recorded fee ≠ expected fee)
  -  3  missing settlements  (captured payment, no settlement)
  -  3  amount mismatches  (settlement total ≠ sum of constituents)
  -  3  timing mismatches  (refund after settlement creation)
  -  2  suspected duplicates  (same amount/method/order in a window)
  -  2  missing bank entries  (settlement processed, no bank credit)
  -  2  unexpected adjustments  (unexplained credit/debit)
  -  1  rounding difference  (sub-paise rounding)

All amounts in paise.  ₹1 = 100 paise.
"""

import csv
import io
import random
from datetime import datetime, date, timedelta, timezone

# Fixed seed for reproducibility
random.seed(42)

# Constants
MDR_RATE = 0.02        # 2% Merchant Discount Rate
GST_RATE = 0.18        # 18% GST on fees
BANK_ACCOUNT = "HDFC_MERCHANT_9281"
METHODS = ["card", "upi", "netbanking", "wallet"]

BASE_DATE = datetime(2026, 8, 1, 10, 0, 0, tzinfo=timezone.utc)


def _dt(day: int, hour: int = 10, minute: int = 0) -> datetime:
    return BASE_DATE + timedelta(days=day, hours=hour - 10, minutes=minute)


def _compute_fee(amount: int) -> int:
    """Standard MDR fee calculation."""
    return round(amount * MDR_RATE)


def _compute_tax(fee: int) -> int:
    """GST on fee."""
    return round(fee * GST_RATE)


def _random_amount(low: int = 50000, high: int = 500000) -> int:
    """Random amount in paise (₹500 - ₹5,000)."""
    return random.randint(low // 100, high // 100) * 100


def generate_dataset() -> dict:
    """
    Generate a complete synthetic dataset.

    Returns dict with keys:
        transactions: list[dict]
        settlements:  list[dict]
        bank_statements: list[dict]
        ground_truth: dict  (expected results for evaluation)
    """
    # Reset seed at the start of every call for deterministic output
    random.seed(42)

    transactions = []
    settlements = []
    bank_statements = []
    ground_truth = {
        "total_transactions": 0,
        "expected_matched": 0,
        "planted_exceptions": [],
    }

    pay_counter = 0
    rfnd_counter = 0
    adj_counter = 0

    def next_pay_id():
        nonlocal pay_counter
        pay_counter += 1
        return f"pay_{pay_counter:03d}"

    def next_rfnd_id():
        nonlocal rfnd_counter
        rfnd_counter += 1
        return f"rfnd_{rfnd_counter:03d}"

    def next_adj_id():
        nonlocal adj_counter
        adj_counter += 1
        return f"adj_{adj_counter:03d}"

    def make_payment(order_num: int, amount: int, day: int, hour: int,
                     settlement_id: str | None = None,
                     fee_override: int | None = None) -> dict:
        fee = fee_override if fee_override is not None else _compute_fee(amount)
        tax = _compute_tax(fee)
        pay_id = next_pay_id()
        return {
            "id": pay_id,
            "type": "payment",
            "order_id": f"order_{order_num:03d}",
            "amount": amount,
            "currency": "INR",
            "status": "captured",
            "fee": fee,
            "tax": tax,
            "settlement_id": settlement_id,
            "method": random.choice(METHODS),
            "description": f"Order #{order_num:03d} payment",
            "captured_at": _dt(day, hour),
            "created_at": _dt(day, hour - 1),
        }

    # -------------------------------------------------------------------------
    # SETTLEMENT 1-5: Clean matches (28 payments)
    # -------------------------------------------------------------------------
    for setl_num in range(1, 5):
        setl_id = f"setl_{setl_num:03d}"
        day = setl_num * 2
        setl_payments = []

        for j in range(7):
            order_num = (setl_num - 1) * 7 + j + 1
            amount = _random_amount(50000, 500000)
            txn = make_payment(order_num, amount, day, 10 + j, setl_id)
            transactions.append(txn)
            setl_payments.append(txn)

        total_gross = sum(t["amount"] for t in setl_payments)
        total_fees = sum(t["fee"] for t in setl_payments)
        total_tax = sum(t["tax"] for t in setl_payments)
        net_amount = total_gross - total_fees - total_tax

        utr = f"UTIB{2026:04d}{8:02d}{day:02d}{setl_num:05d}"
        settlements.append({
            "id": setl_id,
            "amount": net_amount,
            "fees": total_fees,
            "tax": total_tax,
            "utr": utr,
            "status": "processed",
            "created_at": _dt(day, 18),
        })
        bank_statements.append({
            "bank_account": BANK_ACCOUNT,
            "entry_date": _dt(day + 2).date(),
            "description": f"RAZORPAY SETTLEMENT {setl_id}",
            "reference": utr,
            "credit": net_amount,
            "debit": 0,
            "balance": None,
        })

        ground_truth["expected_matched"] += len(setl_payments)

    # -------------------------------------------------------------------------
    # SETTLEMENT 5: Clean (6 more payments = 34 clean total)
    # -------------------------------------------------------------------------
    setl_id = "setl_005"
    day = 10
    setl_payments = []

        # 4 settlements * 7 = 28 payments. Add 6 more to reach 34 clean.
    for j in range(6):
        order_num = 25 + j
        amount = _random_amount(100000, 800000)
        txn = make_payment(order_num, amount, day, 10 + j, setl_id)
        transactions.append(txn)
        setl_payments.append(txn)

    total_gross = sum(t["amount"] for t in setl_payments)
    total_fees = sum(t["fee"] for t in setl_payments)
    total_tax = sum(t["tax"] for t in setl_payments)
    net_amount = total_gross - total_fees - total_tax

    utr = f"UTIB20260810{5:05d}"
    settlements.append({
        "id": setl_id,
        "amount": net_amount,
        "fees": total_fees,
        "tax": total_tax,
        "utr": utr,
        "status": "processed",
        "created_at": _dt(day, 18),
    })
    bank_statements.append({
        "bank_account": BANK_ACCOUNT,
        "entry_date": _dt(day + 2).date(),
        "description": f"RAZORPAY SETTLEMENT {setl_id}",
        "reference": utr,
        "credit": net_amount,
        "debit": 0,
        "balance": None,
    })
    ground_truth["expected_matched"] += len(setl_payments)

    # -------------------------------------------------------------------------
    # SETTLEMENT 6: Fee discrepancy (4 payments with wrong recorded fees)
    # -------------------------------------------------------------------------
    setl_id = "setl_006"
    day = 12
    setl_payments = []

    for j in range(4):
        order_num = 31 + j
        amount = _random_amount(100000, 600000)
        # Record a WRONG fee (use 3% instead of 2%)
        wrong_fee = round(amount * 0.03)  # 3% instead of 2%
        txn = make_payment(order_num, amount, day, 10 + j, setl_id, fee_override=wrong_fee)
        transactions.append(txn)
        setl_payments.append(txn)

    # Settlement uses CORRECT fee math (2% MDR)
    total_gross = sum(t["amount"] for t in setl_payments)
    correct_fees = sum(_compute_fee(t["amount"]) for t in setl_payments)
    correct_tax = sum(_compute_tax(_compute_fee(t["amount"])) for t in setl_payments)
    net_amount = total_gross - correct_fees - correct_tax

    utr = f"UTIB20260812{6:05d}"
    settlements.append({
        "id": setl_id,
        "amount": net_amount,
        "fees": correct_fees,
        "tax": correct_tax,
        "utr": utr,
        "status": "processed",
        "created_at": _dt(day, 18),
    })
    bank_statements.append({
        "bank_account": BANK_ACCOUNT,
        "entry_date": _dt(day + 2).date(),
        "description": f"RAZORPAY SETTLEMENT {setl_id}",
        "reference": utr,
        "credit": net_amount,
        "debit": 0,
        "balance": None,
    })
    
    ground_truth["planted_exceptions"].append({
        "transaction_id": setl_id,
        "type": "amount_mismatch",
        "detail": "Settlement amount mismatch due to transaction fee discrepancies"
    })

    for t in setl_payments:
        ground_truth["planted_exceptions"].append({
            "transaction_id": t["id"],
            "type": "fee_discrepancy",
            "detail": f"Recorded fee {t['fee']} but expected {_compute_fee(t['amount'])} (2% MDR)",
        })

    # -------------------------------------------------------------------------
    # SETTLEMENT 7: Timing mismatch (3 refunds created after settlement)
    # -------------------------------------------------------------------------
    setl_id = "setl_007"
    day = 14
    setl_payments = []

    for j in range(3):
        order_num = 35 + j
        amount = _random_amount(200000, 500000)
        txn = make_payment(order_num, amount, day, 10 + j, setl_id)
        transactions.append(txn)
        setl_payments.append(txn)

    total_gross = sum(t["amount"] for t in setl_payments)
    total_fees = sum(t["fee"] for t in setl_payments)
    total_tax = sum(t["tax"] for t in setl_payments)
    net_amount = total_gross - total_fees - total_tax

    utr = f"UTIB20260814{7:05d}"
    settlements.append({
        "id": setl_id,
        "amount": net_amount,
        "fees": total_fees,
        "tax": total_tax,
        "utr": utr,
        "status": "processed",
        "created_at": _dt(day, 18),  # Settlement at 6 PM
    })
    # Bank gets the ORIGINAL amount (before refunds are deducted)
    bank_statements.append({
        "bank_account": BANK_ACCOUNT,
        "entry_date": _dt(day + 2).date(),
        "description": f"RAZORPAY SETTLEMENT {setl_id}",
        "reference": utr,
        "credit": net_amount,
        "debit": 0,
        "balance": None,
    })
    
    ground_truth["planted_exceptions"].append({
        "transaction_id": setl_id,
        "type": "amount_mismatch",
        "detail": "Settlement amount mismatch due to refunds"
    })

    # 3 refunds created AFTER settlement — these will cause a timing mismatch
    for j, pay_txn in enumerate(setl_payments):
        rfnd_id = next_rfnd_id()
        rfnd_amount = round(pay_txn["amount"] * 0.5)  # 50% refund
        transactions.append({
            "id": rfnd_id,
            "type": "refund",
            "order_id": pay_txn["order_id"],
            "amount": rfnd_amount,
            "currency": "INR",
            "status": "processed",
            "fee": 0,
            "tax": 0,
            "settlement_id": setl_id,
            "method": pay_txn["method"],
            "description": f"Refund for {pay_txn['id']}",
            "captured_at": None,
            "created_at": _dt(day, 20 + j),  # Created AFTER settlement
        })
        ground_truth["planted_exceptions"].append({
            "transaction_id": rfnd_id,
            "type": "timing_mismatch",
            "detail": f"Refund created at hour {20 + j} but settlement created at hour 18",
        })

    # -------------------------------------------------------------------------
    # SETTLEMENT 8: Amount mismatch (settlement amount is WRONG)
    # -------------------------------------------------------------------------
    setl_id = "setl_008"
    day = 16
    setl_payments = []

    for j in range(3):
        order_num = 38 + j
        amount = _random_amount(150000, 400000)
        txn = make_payment(order_num, amount, day, 10 + j, setl_id)
        transactions.append(txn)
        setl_payments.append(txn)

    total_gross = sum(t["amount"] for t in setl_payments)
    total_fees = sum(t["fee"] for t in setl_payments)
    total_tax = sum(t["tax"] for t in setl_payments)
    correct_net = total_gross - total_fees - total_tax
    # Deliberately WRONG settlement amount (off by ₹1,247 / 124700 paise)
    wrong_net = correct_net - 124700

    utr = f"UTIB20260816{8:05d}"
    settlements.append({
        "id": setl_id,
        "amount": wrong_net,  # WRONG!
        "fees": total_fees,
        "tax": total_tax,
        "utr": utr,
        "status": "processed",
        "created_at": _dt(day, 18),
    })
    bank_statements.append({
        "bank_account": BANK_ACCOUNT,
        "entry_date": _dt(day + 2).date(),
        "description": f"RAZORPAY SETTLEMENT {setl_id}",
        "reference": utr,
        "credit": wrong_net,  # Bank matches the wrong settlement amount
        "debit": 0,
        "balance": None,
    })

    ground_truth["planted_exceptions"].append({
        "transaction_id": setl_id,
        "type": "amount_mismatch",
        "detail": f"Settlement amount {wrong_net} but txns sum to {correct_net}. Difference: 124700 paise (₹1,247)",
    })

    # -------------------------------------------------------------------------
    # MISSING SETTLEMENTS: 3 captured payments with NO settlement
    # -------------------------------------------------------------------------
    for j in range(3):
        order_num = 41 + j
        amount = _random_amount(80000, 300000)
        txn = make_payment(order_num, amount, day=18, hour=10 + j, settlement_id=None)
        transactions.append(txn)
        ground_truth["planted_exceptions"].append({
            "transaction_id": txn["id"],
            "type": "missing_settlement",
            "detail": "Captured payment has no settlement_id",
        })

    # -------------------------------------------------------------------------
    # SUSPECTED DUPLICATES: 2 pairs (same amount, method, order_id)
    # -------------------------------------------------------------------------
    for j in range(2):
        amount = _random_amount(100000, 200000)
        order_num = 44 + j
        method = random.choice(METHODS)

        # First (legitimate) payment
        pay_id_1 = next_pay_id()
        txn1 = {
            "id": pay_id_1,
            "type": "payment",
            "order_id": f"order_{order_num:03d}",
            "amount": amount,
            "currency": "INR",
            "status": "captured",
            "fee": _compute_fee(amount),
            "tax": _compute_tax(_compute_fee(amount)),
            "settlement_id": "setl_999",  # dummy settlement to avoid missing_settlement exception
            "method": method,
            "description": f"Order #{order_num:03d} payment",
            "captured_at": _dt(19, 10 + j),
            "created_at": _dt(19, 9 + j),
        }
        transactions.append(txn1)

        # Duplicate payment (same amount, order, method, close timestamp)
        pay_id_2 = next_pay_id()
        txn2 = {
            "id": pay_id_2,
            "type": "payment",
            "order_id": f"order_{order_num:03d}",  # SAME order
            "amount": amount,                       # SAME amount
            "currency": "INR",
            "status": "captured",
            "fee": _compute_fee(amount),
            "tax": _compute_tax(_compute_fee(amount)),
            "settlement_id": "setl_999",
            "method": method,                       # SAME method
            "description": f"Order #{order_num:03d} payment (retry)",
            "captured_at": _dt(19, 10 + j, 5),  # 5 min later
            "created_at": _dt(19, 9 + j, 5),
        }
        transactions.append(txn2)

        ground_truth["planted_exceptions"].append({
            "transaction_id": f"{pay_id_1},{pay_id_2}",
            "type": "duplicate_suspected",
            "detail": f"Same order_{order_num:03d}, amount {amount}, method {method}, 5 min apart",
        })

    # -------------------------------------------------------------------------
    # MISSING BANK ENTRIES: Settlement 9 processed but no bank credit
    # -------------------------------------------------------------------------
    setl_id = "setl_009"
    day = 20
    setl_payments = []

    for j in range(2):
        order_num = 46 + j
        amount = _random_amount(200000, 600000)
        txn = make_payment(order_num, amount, day, 10 + j, setl_id)
        transactions.append(txn)
        setl_payments.append(txn)

    total_gross = sum(t["amount"] for t in setl_payments)
    total_fees = sum(t["fee"] for t in setl_payments)
    total_tax = sum(t["tax"] for t in setl_payments)
    net_amount = total_gross - total_fees - total_tax

    utr = f"UTIB20260820{9:05d}"
    settlements.append({
        "id": setl_id,
        "amount": net_amount,
        "fees": total_fees,
        "tax": total_tax,
        "utr": utr,
        "status": "processed",
        "created_at": _dt(day, 18),
    })
    # NO bank statement entry — that's the exception!

    ground_truth["planted_exceptions"].append({
        "transaction_id": setl_id,
        "type": "missing_bank_entry",
        "detail": f"Settlement {setl_id} processed with UTR {utr} but no bank credit found",
    })

    # -------------------------------------------------------------------------
    # UNEXPECTED ADJUSTMENTS: 2 adjustment entries with no matching context
    # -------------------------------------------------------------------------
    for j in range(2):
        adj_id = next_adj_id()
        adj_amount = _random_amount(5000, 50000)
        transactions.append({
            "id": adj_id,
            "type": "adjustment",
            "order_id": None,
            "amount": adj_amount,
            "currency": "INR",
            "status": "captured",
            "fee": 0,
            "tax": 0,
            "settlement_id": None,
            "method": None,
            "description": f"Manual adjustment - ref RZPADJ{1000 + j}",
            "captured_at": None,
            "created_at": _dt(21, 14 + j),
        })
        ground_truth["planted_exceptions"].append({
            "transaction_id": adj_id,
            "type": "unexpected_adjustment",
            "detail": f"Adjustment {adj_id} for {adj_amount} paise with no matching order or settlement",
        })

    # -------------------------------------------------------------------------
    # ROUNDING DIFFERENCE: Add a bank entry with ₹2 off due to rounding
    # -------------------------------------------------------------------------
    # The bank credit for setl_001 is off by 2 paise (simulating sub-paise rounding)
    # We already created the correct bank entry for setl_001, so modify the last digit
    # Actually, let's add a SECOND entry for a different "rounding" settlement
    setl_id = "setl_010"
    day = 22
    setl_payments = []

    for j in range(2):
        order_num = 48 + j
        # Use odd amounts that create rounding issues
        amount = 333333 + j * 111111  # ₹3,333.33, ₹4,444.44
        txn = make_payment(order_num, amount, day, 10 + j, setl_id)
        transactions.append(txn)
        setl_payments.append(txn)

    total_gross = sum(t["amount"] for t in setl_payments)
    total_fees = sum(t["fee"] for t in setl_payments)
    total_tax = sum(t["tax"] for t in setl_payments)
    correct_net = total_gross - total_fees - total_tax

    utr = f"UTIB20260822{10:05d}"
    settlements.append({
        "id": setl_id,
        "amount": correct_net,
        "fees": total_fees,
        "tax": total_tax,
        "utr": utr,
        "status": "processed",
        "created_at": _dt(day, 18),
    })
    # Bank credits slightly different amount (off by 3 paise)
    bank_statements.append({
        "bank_account": BANK_ACCOUNT,
        "entry_date": _dt(day + 2).date(),
        "description": f"RAZORPAY SETTLEMENT {setl_id}",
        "reference": utr,
        "credit": correct_net - 3,  # Off by 3 paise!
        "debit": 0,
        "balance": None,
    })

    ground_truth["planted_exceptions"].append({
        "transaction_id": setl_id,
        "type": "rounding_difference",
        "detail": f"Bank credit is {correct_net - 3} but settlement amount is {correct_net}. Difference: 3 paise",
    })

    # -------------------------------------------------------------------------
    # Summary
    # -------------------------------------------------------------------------
    ground_truth["total_transactions"] = len(transactions)
    ground_truth["total_settlements"] = len(settlements)
    ground_truth["total_bank_statements"] = len(bank_statements)
    ground_truth["exception_counts"] = {}
    for exc in ground_truth["planted_exceptions"]:
        t = exc["type"]
        ground_truth["exception_counts"][t] = ground_truth["exception_counts"].get(t, 0) + 1

    return {
        "transactions": transactions,
        "settlements": settlements,
        "bank_statements": bank_statements,
        "ground_truth": ground_truth,
    }


def to_csv(records: list[dict], fields: list[str]) -> str:
    """Convert list of dicts to CSV string."""
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    
    formatted_records = []
    for rec in records:
        fmt_rec = {}
        for k, v in rec.items():
            if isinstance(v, (datetime, date)):
                fmt_rec[k] = v.isoformat()
            else:
                fmt_rec[k] = v
        formatted_records.append(fmt_rec)
        
    writer.writerows(formatted_records)
    return output.getvalue()


def generate_csv_files() -> dict[str, str]:
    """Generate dataset and return as three CSV strings."""
    data = generate_dataset()

    txn_fields = [
        "id", "type", "order_id", "amount", "currency", "status",
        "fee", "tax", "settlement_id", "method", "description",
        "captured_at", "created_at",
    ]
    setl_fields = ["id", "amount", "fees", "tax", "utr", "status", "created_at"]
    bank_fields = [
        "bank_account", "entry_date", "description", "reference",
        "credit", "debit", "balance",
    ]

    return {
        "transactions.csv": to_csv(data["transactions"], txn_fields),
        "settlements.csv": to_csv(data["settlements"], setl_fields),
        "bank_statements.csv": to_csv(data["bank_statements"], bank_fields),
        "ground_truth": data["ground_truth"],
    }
