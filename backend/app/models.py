"""
SQLAlchemy ORM models — mirrors the schema from the architecture document.
All monetary amounts are stored as BIGINT in paise (₹1 = 100 paise).
"""

from datetime import datetime, date
from sqlalchemy import (
    String, BigInteger, Integer, Float, Text, Date, Boolean,
    DateTime, JSON, ForeignKey, Index, func, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


# ---------------------------------------------------------------------------
# Multi-tenancy & Auth
# ---------------------------------------------------------------------------

class Merchant(Base):
    __tablename__ = "merchants"

    id: Mapped[str] = mapped_column(String, primary_key=True)  # merchant_xxx
    name: Mapped[str] = mapped_column(String, nullable=False)
    razorpay_account_id: Mapped[str | None] = mapped_column(String)
    webhook_secret: Mapped[str | None] = mapped_column(String)
    oauth_access_token: Mapped[str | None] = mapped_column(Text)
    oauth_refresh_token: Mapped[str | None] = mapped_column(Text)
    oauth_token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    users: Mapped[list["User"]] = relationship(back_populates="merchant")
    api_keys: Mapped[list["APIKey"]] = relationship(back_populates="merchant")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[str] = mapped_column(String, default="viewer")  # admin | operator | viewer
    merchant_id: Mapped[str | None] = mapped_column(String, ForeignKey("merchants.id"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    merchant: Mapped["Merchant | None"] = relationship(back_populates="users")


class APIKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key_prefix: Mapped[str] = mapped_column(String, nullable=False)  # First 8 chars for display
    key_hash: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    merchant_id: Mapped[str | None] = mapped_column(String, ForeignKey("merchants.id"))
    scopes: Mapped[dict] = mapped_column(JSON, default=dict)  # {"read": true, "write": true}
    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    merchant: Mapped["Merchant | None"] = relationship(back_populates="api_keys")


# ---------------------------------------------------------------------------
# Core financial entities
# ---------------------------------------------------------------------------

class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[str] = mapped_column(String, primary_key=True)  # pay_ABC, rfnd_XYZ
    type: Mapped[str] = mapped_column(String, nullable=False)  # payment | refund | adjustment
    order_id: Mapped[str | None] = mapped_column(String)
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)  # paise
    currency: Mapped[str] = mapped_column(String, default="INR")
    status: Mapped[str] = mapped_column(String, nullable=False)  # created|authorized|captured|failed|refunded
    fee: Mapped[int] = mapped_column(BigInteger, default=0)
    tax: Mapped[int] = mapped_column(BigInteger, default=0)
    settlement_id: Mapped[str | None] = mapped_column(String, ForeignKey("settlements.id"))
    method: Mapped[str | None] = mapped_column(String)  # card|upi|netbanking|wallet
    description: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[dict] = mapped_column(JSON, default=dict)
    captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    source: Mapped[str] = mapped_column(String, nullable=False)  # csv_batch|api_realtime|webhook
    merchant_id: Mapped[str | None] = mapped_column(String, ForeignKey("merchants.id"))

    settlement: Mapped["Settlement | None"] = relationship(back_populates="transactions")

    __table_args__ = (
        Index("idx_txn_settlement", "settlement_id"),
        Index("idx_txn_status", "status"),
        Index("idx_txn_type", "type"),
        Index("idx_txn_merchant", "merchant_id"),
    )


class Settlement(Base):
    __tablename__ = "settlements"

    id: Mapped[str] = mapped_column(String, primary_key=True)  # setl_ABC
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)  # paise
    fees: Mapped[int] = mapped_column(BigInteger, default=0)
    tax: Mapped[int] = mapped_column(BigInteger, default=0)
    utr: Mapped[str | None] = mapped_column(String)  # bank UTR for matching
    status: Mapped[str] = mapped_column(String, nullable=False)  # created|processed|failed
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    merchant_id: Mapped[str | None] = mapped_column(String, ForeignKey("merchants.id"))

    transactions: Mapped[list["Transaction"]] = relationship(back_populates="settlement")

    __table_args__ = (
        Index("idx_setl_merchant", "merchant_id"),
        Index("idx_setl_utr", "utr"),
    )


class BankStatement(Base):
    __tablename__ = "bank_statements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bank_account: Mapped[str] = mapped_column(String, nullable=False)
    entry_date: Mapped[date] = mapped_column(Date, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    reference: Mapped[str | None] = mapped_column(String)  # UTR
    credit: Mapped[int] = mapped_column(BigInteger, default=0)  # paise
    debit: Mapped[int] = mapped_column(BigInteger, default=0)  # paise
    balance: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    merchant_id: Mapped[str | None] = mapped_column(String, ForeignKey("merchants.id"))

    __table_args__ = (
        Index("idx_bank_ref", "reference"),
        Index("idx_bank_date", "entry_date"),
        Index("idx_bank_merchant", "merchant_id"),
    )


# ---------------------------------------------------------------------------
# Reconciliation
# ---------------------------------------------------------------------------

class ReconciliationRun(Base):
    __tablename__ = "reconciliation_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String, default="running")  # running|completed|failed
    trigger_type: Mapped[str] = mapped_column(String, nullable=False)  # manual|scheduled|event
    total_records: Mapped[int] = mapped_column(Integer, default=0)
    matched: Mapped[int] = mapped_column(Integer, default=0)
    mismatched: Mapped[int] = mapped_column(Integer, default=0)
    unmatched: Mapped[int] = mapped_column(Integer, default=0)
    exceptions_count: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    summary: Mapped[dict] = mapped_column(JSON, default=dict)
    merchant_id: Mapped[str | None] = mapped_column(String, ForeignKey("merchants.id"))

    results: Mapped[list["ReconciliationResult"]] = relationship(back_populates="run")

    __table_args__ = (
        Index("idx_run_merchant", "merchant_id"),
    )


class ReconciliationResult(Base):
    __tablename__ = "reconciliation_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(Integer, ForeignKey("reconciliation_runs.id"))
    transaction_id: Mapped[str | None] = mapped_column(String, ForeignKey("transactions.id"))
    settlement_id: Mapped[str | None] = mapped_column(String, ForeignKey("settlements.id"))
    bank_stmt_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("bank_statements.id"))
    match_type: Mapped[str] = mapped_column(String, nullable=False)  # exact|aggregate|fuzzy|ensemble|none
    match_status: Mapped[str] = mapped_column(String, nullable=False)  # matched|mismatched|unmatched
    match_score: Mapped[float | None] = mapped_column(Float)  # Ensemble confidence score 0.0-1.0
    expected_amount: Mapped[int | None] = mapped_column(BigInteger)
    actual_amount: Mapped[int | None] = mapped_column(BigInteger)
    difference: Mapped[int] = mapped_column(BigInteger, default=0)
    match_details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    run: Mapped["ReconciliationRun"] = relationship(back_populates="results")


# ---------------------------------------------------------------------------
# Exceptions & AI Investigation
# ---------------------------------------------------------------------------

class Exception_(Base):
    """Named Exception_ to avoid shadowing Python's built-in Exception."""
    __tablename__ = "exceptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("reconciliation_runs.id"))
    result_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("reconciliation_results.id"))
    type: Mapped[str] = mapped_column(String, nullable=False)
    severity: Mapped[str] = mapped_column(String, nullable=False)  # low|medium|high|critical
    status: Mapped[str] = mapped_column(String, default="detected")  # detected|investigating|resolved|escalated
    amount_at_risk: Mapped[int] = mapped_column(BigInteger, default=0)  # paise
    context: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    merchant_id: Mapped[str | None] = mapped_column(String, ForeignKey("merchants.id"))

    investigation: Mapped["Investigation | None"] = relationship(back_populates="exception")
    notes: Mapped[list["ExceptionNote"]] = relationship(back_populates="exception", order_by="ExceptionNote.created_at")

    __table_args__ = (
        Index("idx_exceptions_status", "status"),
        Index("idx_exceptions_merchant", "merchant_id"),
        Index("idx_exceptions_severity", "severity"),
        Index("idx_exceptions_type", "type"),
    )


class Investigation(Base):
    __tablename__ = "investigations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    exception_id: Mapped[int] = mapped_column(Integer, ForeignKey("exceptions.id"))
    root_cause: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[dict] = mapped_column(JSON, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    recommended_action: Mapped[str] = mapped_column(String, nullable=False)  # auto_resolve|escalate|needs_data
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    resolution_type: Mapped[str | None] = mapped_column(String)  # auto|manual
    resolved_by: Mapped[str | None] = mapped_column(String)  # system|human_reviewer
    model_used: Mapped[str | None] = mapped_column(String)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer)
    response_tokens: Mapped[int | None] = mapped_column(Integer)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    chain_of_thought: Mapped[dict | None] = mapped_column(JSON)  # Steps: fact_gathering, hypothesis, validation, scoring
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    exception: Mapped["Exception_"] = relationship(back_populates="investigation")


class ExceptionNote(Base):
    """User notes/comments on exceptions."""
    __tablename__ = "exception_notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    exception_id: Mapped[int] = mapped_column(Integer, ForeignKey("exceptions.id"), nullable=False)
    user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    exception: Mapped["Exception_"] = relationship(back_populates="notes")

    __table_args__ = (
        Index("idx_notes_exception", "exception_id"),
    )


# ---------------------------------------------------------------------------
# Audit & Events
# ---------------------------------------------------------------------------

class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    entity_type: Mapped[str] = mapped_column(String, nullable=False)
    entity_id: Mapped[str] = mapped_column(String, nullable=False)
    action: Mapped[str] = mapped_column(String, nullable=False)
    actor: Mapped[str] = mapped_column(String, nullable=False)  # system|ai_investigator|human|user_email
    old_state: Mapped[dict | None] = mapped_column(JSON)
    new_state: Mapped[dict | None] = mapped_column(JSON)
    metadata_: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    merchant_id: Mapped[str | None] = mapped_column(String, ForeignKey("merchants.id"))

    __table_args__ = (
        Index("idx_audit_entity", "entity_type", "entity_id"),
        Index("idx_audit_time", "timestamp"),
        Index("idx_audit_merchant", "merchant_id"),
    )


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String, default="pending")  # pending|processing|processed|failed
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    merchant_id: Mapped[str | None] = mapped_column(String, ForeignKey("merchants.id"))

    __table_args__ = (
        Index("idx_events_pending", "status", "created_at"),
    )


# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------

class ScheduledJob(Base):
    __tablename__ = "scheduled_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_type: Mapped[str] = mapped_column(String, nullable=False)  # reconciliation|razorpay_sync
    cron_expression: Mapped[str | None] = mapped_column(String)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_status: Mapped[str | None] = mapped_column(String)  # success|failed
    merchant_id: Mapped[str | None] = mapped_column(String, ForeignKey("merchants.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
