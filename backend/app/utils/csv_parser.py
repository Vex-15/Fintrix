"""
CSV parsing utilities for financial data ingestion.
Handles transactions, settlements, and bank statements.
"""

import csv
import io
from datetime import datetime, date
from typing import Any


def _parse_int(val: str, default: int = 0) -> int:
    """Parse string to int, returning default on failure."""
    if not val or val.strip() == "":
        return default
    try:
        return int(val.strip())
    except ValueError:
        try:
            return int(float(val.strip()))
        except ValueError:
            return default


def _parse_datetime(val: str) -> datetime | None:
    """Parse ISO-ish datetime string."""
    if not val or val.strip() == "":
        return None
    val = val.strip()
    for fmt in (
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M:%S%z",
        "%Y-%m-%d",
    ):
        try:
            return datetime.strptime(val, fmt)
        except ValueError:
            continue
    return None


def _parse_date(val: str) -> date | None:
    """Parse date string."""
    if not val or val.strip() == "":
        return None
    val = val.strip()
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(val, fmt).date()
        except ValueError:
            continue
    return None


def parse_transactions_csv(content: str) -> tuple[list[dict[str, Any]], list[str]]:
    """
    Parse transactions CSV.

    Expected columns:
        id, type, order_id, amount, currency, status, fee, tax,
        settlement_id, method, description, captured_at, created_at

    Returns (records, errors).
    """
    records: list[dict[str, Any]] = []
    errors: list[str] = []
    reader = csv.DictReader(io.StringIO(content))

    for i, row in enumerate(reader, start=2):  # row 1 is header
        try:
            txn_id = row.get("id", "").strip()
            if not txn_id:
                errors.append(f"Row {i}: missing 'id'")
                continue

            txn_type = row.get("type", "").strip()
            if txn_type not in ("payment", "refund", "adjustment"):
                errors.append(f"Row {i}: invalid type '{txn_type}'")
                continue

            amount = _parse_int(row.get("amount", "0"))
            if amount == 0 and txn_type != "adjustment":
                errors.append(f"Row {i}: amount is 0 or invalid")
                continue

            status = row.get("status", "").strip()
            if not status:
                errors.append(f"Row {i}: missing 'status'")
                continue

            records.append({
                "id": txn_id,
                "type": txn_type,
                "order_id": row.get("order_id", "").strip() or None,
                "amount": amount,
                "currency": row.get("currency", "INR").strip() or "INR",
                "status": status,
                "fee": _parse_int(row.get("fee", "0")),
                "tax": _parse_int(row.get("tax", "0")),
                "settlement_id": row.get("settlement_id", "").strip() or None,
                "method": row.get("method", "").strip() or None,
                "description": row.get("description", "").strip() or None,
                "captured_at": _parse_datetime(row.get("captured_at", "")),
                "created_at": _parse_datetime(row.get("created_at", "")) or datetime.utcnow(),
                "source": "csv_batch",
            })

        except Exception as e:
            errors.append(f"Row {i}: {str(e)}")

    return records, errors


def parse_settlements_csv(content: str) -> tuple[list[dict[str, Any]], list[str]]:
    """
    Parse settlements CSV.

    Expected columns:
        id, amount, fees, tax, utr, status, created_at

    Returns (records, errors).
    """
    records: list[dict[str, Any]] = []
    errors: list[str] = []
    reader = csv.DictReader(io.StringIO(content))

    for i, row in enumerate(reader, start=2):
        try:
            setl_id = row.get("id", "").strip()
            if not setl_id:
                errors.append(f"Row {i}: missing 'id'")
                continue

            records.append({
                "id": setl_id,
                "amount": _parse_int(row.get("amount", "0")),
                "fees": _parse_int(row.get("fees", "0")),
                "tax": _parse_int(row.get("tax", "0")),
                "utr": row.get("utr", "").strip() or None,
                "status": row.get("status", "processed").strip(),
                "created_at": _parse_datetime(row.get("created_at", "")) or datetime.utcnow(),
            })

        except Exception as e:
            errors.append(f"Row {i}: {str(e)}")

    return records, errors


def parse_bank_statements_csv(content: str) -> tuple[list[dict[str, Any]], list[str]]:
    """
    Parse bank statements CSV.

    Expected columns:
        bank_account, entry_date, description, reference, credit, debit, balance

    Returns (records, errors).
    """
    records: list[dict[str, Any]] = []
    errors: list[str] = []
    reader = csv.DictReader(io.StringIO(content))

    for i, row in enumerate(reader, start=2):
        try:
            bank_account = row.get("bank_account", "").strip()
            if not bank_account:
                errors.append(f"Row {i}: missing 'bank_account'")
                continue

            entry_date = _parse_date(row.get("entry_date", ""))
            if not entry_date:
                errors.append(f"Row {i}: invalid or missing 'entry_date'")
                continue

            records.append({
                "bank_account": bank_account,
                "entry_date": entry_date,
                "description": row.get("description", "").strip() or None,
                "reference": row.get("reference", "").strip() or None,
                "credit": _parse_int(row.get("credit", "0")),
                "debit": _parse_int(row.get("debit", "0")),
                "balance": _parse_int(row.get("balance", "")) if row.get("balance", "").strip() else None,
            })

        except Exception as e:
            errors.append(f"Row {i}: {str(e)}")

    return records, errors
