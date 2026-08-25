"""
Ingestion API — CSV upload, real-time event ingestion, and synthetic data generation.
"""

from fastapi import APIRouter, UploadFile, File, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy import select, func

from app.database import get_db
from app.models import Transaction, Settlement, BankStatement
from app.schemas import IngestionResult
from app.utils.csv_parser import (
    parse_transactions_csv,
    parse_settlements_csv,
    parse_bank_statements_csv,
)
from app.utils.audit import log_audit
from app.utils.synthetic_data import generate_dataset, generate_csv_files

router = APIRouter()


# ---------------------------------------------------------------------------
# CSV Upload Endpoints
# ---------------------------------------------------------------------------

@router.post("/csv/transactions", response_model=IngestionResult)
async def upload_transactions_csv(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """Upload a CSV of transactions (payments, refunds, adjustments)."""
    content = (await file.read()).decode("utf-8-sig")
    records, errors = parse_transactions_csv(content)

    if not records:
        return IngestionResult(
            source="csv_batch", records_parsed=0, records_stored=0, errors=errors
        )

    # Upsert: insert new records, skip duplicates
    stmt = insert(Transaction).values(records).on_conflict_do_nothing(index_elements=["id"])
    result = await db.execute(stmt)
    stored = result.rowcount  # type: ignore

    # Audit
    await log_audit(
        db, "ingestion", "transactions_csv",
        action="csv_uploaded",
        actor="system",
        new_state={"filename": file.filename, "parsed": len(records), "stored": stored},
    )

    return IngestionResult(
        source="csv_batch",
        records_parsed=len(records),
        records_stored=stored,
        errors=errors,
    )


@router.post("/csv/settlements", response_model=IngestionResult)
async def upload_settlements_csv(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """Upload a CSV of settlements."""
    content = (await file.read()).decode("utf-8-sig")
    records, errors = parse_settlements_csv(content)

    if not records:
        return IngestionResult(
            source="csv_batch", records_parsed=0, records_stored=0, errors=errors
        )

    stmt = insert(Settlement).values(records).on_conflict_do_nothing(index_elements=["id"])
    result = await db.execute(stmt)
    stored = result.rowcount  # type: ignore

    await log_audit(
        db, "ingestion", "settlements_csv",
        action="csv_uploaded",
        actor="system",
        new_state={"filename": file.filename, "parsed": len(records), "stored": stored},
    )

    return IngestionResult(
        source="csv_batch",
        records_parsed=len(records),
        records_stored=stored,
        errors=errors,
    )


@router.post("/csv/bank-statements", response_model=IngestionResult)
async def upload_bank_statements_csv(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """Upload a CSV of bank statement entries."""
    content = (await file.read()).decode("utf-8-sig")
    records, errors = parse_bank_statements_csv(content)

    if not records:
        return IngestionResult(
            source="csv_batch", records_parsed=0, records_stored=0, errors=errors
        )

    # Bank statements use auto-increment ID, so just insert all
    for rec in records:
        db.add(BankStatement(**rec))
    await db.flush()

    await log_audit(
        db, "ingestion", "bank_statements_csv",
        action="csv_uploaded",
        actor="system",
        new_state={"filename": file.filename, "parsed": len(records), "stored": len(records)},
    )

    return IngestionResult(
        source="csv_batch",
        records_parsed=len(records),
        records_stored=len(records),
        errors=errors,
    )


# ---------------------------------------------------------------------------
# Synthetic Data Generation
# ---------------------------------------------------------------------------

@router.post("/generate-synthetic-data")
async def generate_synthetic_data(
    db: AsyncSession = Depends(get_db),
):
    """
    Generate 50+ synthetic records with planted discrepancies and load them directly into the database.
    Returns the ground truth for evaluation.
    """
    data = generate_dataset()

    # Insert settlements first (transactions have FK to settlements)
    setl_records = data["settlements"]
    if setl_records:
        stmt = insert(Settlement).values(setl_records).on_conflict_do_nothing(index_elements=["id"])
        await db.execute(stmt)

    # Insert transactions
    txn_records = [{**t, "source": "csv_batch"} for t in data["transactions"]]
    if txn_records:
        stmt = insert(Transaction).values(txn_records).on_conflict_do_nothing(index_elements=["id"])
        await db.execute(stmt)

    # Insert bank statements
    for rec in data["bank_statements"]:
        db.add(BankStatement(**rec))
    await db.flush()

    # Audit
    await log_audit(
        db, "ingestion", "synthetic_data",
        action="synthetic_data_generated",
        actor="system",
        new_state={
            "transactions": len(data["transactions"]),
            "settlements": len(data["settlements"]),
            "bank_statements": len(data["bank_statements"]),
        },
    )

    return {
        "message": "Synthetic data loaded successfully",
        "counts": {
            "transactions": len(data["transactions"]),
            "settlements": len(data["settlements"]),
            "bank_statements": len(data["bank_statements"]),
        },
        "ground_truth": data["ground_truth"],
    }


@router.get("/download-synthetic-csv")
async def download_synthetic_csv():
    """Generate synthetic dataset and return as downloadable CSV files (as JSON with CSV strings)."""
    csv_data = generate_csv_files()
    return {
        "transactions_csv": csv_data["transactions.csv"],
        "settlements_csv": csv_data["settlements.csv"],
        "bank_statements_csv": csv_data["bank_statements.csv"],
        "ground_truth": csv_data["ground_truth"],
    }


# ---------------------------------------------------------------------------
# Data Status
# ---------------------------------------------------------------------------

@router.get("/status")
async def ingestion_status(db: AsyncSession = Depends(get_db)):
    """Get counts of all ingested data."""
    txn_count = (await db.execute(select(func.count(Transaction.id)))).scalar() or 0
    setl_count = (await db.execute(select(func.count(Settlement.id)))).scalar() or 0
    bank_count = (await db.execute(select(func.count(BankStatement.id)))).scalar() or 0

    return {
        "transactions": txn_count,
        "settlements": setl_count,
        "bank_statements": bank_count,
    }
