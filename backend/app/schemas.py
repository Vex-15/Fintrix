"""
Pydantic schemas for API request/response contracts.
"""

from datetime import datetime, date
from typing import Optional
from pydantic import BaseModel, Field, EmailStr


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

class UserRegisterRequest(BaseModel):
    email: str
    password: str = Field(min_length=6)
    name: str
    merchant_id: Optional[str] = None


class UserLoginRequest(BaseModel):
    email: str
    password: str


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class UserProfileOut(BaseModel):
    id: int
    email: str
    name: str
    role: str
    merchant_id: Optional[str] = None
    is_active: bool
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class UserProfileUpdate(BaseModel):
    name: Optional[str] = None
    password: Optional[str] = Field(None, min_length=6)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserProfileOut


# ---------------------------------------------------------------------------
# API Keys
# ---------------------------------------------------------------------------

class APIKeyCreateRequest(BaseModel):
    name: str
    scopes: Optional[dict] = None  # {"read": true, "write": true}


class APIKeyOut(BaseModel):
    id: int
    key_prefix: str
    name: str
    scopes: dict
    is_active: bool
    last_used_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class APIKeyCreatedResponse(BaseModel):
    id: int
    raw_key: str  # Shown once only!
    key_prefix: str
    name: str
    scopes: dict
    created_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Transactions
# ---------------------------------------------------------------------------

class TransactionBase(BaseModel):
    id: str
    type: str  # payment | refund | adjustment
    order_id: Optional[str] = None
    amount: int  # paise
    currency: str = "INR"
    status: str
    fee: int = 0
    tax: int = 0
    settlement_id: Optional[str] = None
    method: Optional[str] = None
    description: Optional[str] = None
    notes: dict = Field(default_factory=dict)
    captured_at: Optional[datetime] = None
    created_at: Optional[datetime] = None


class TransactionOut(TransactionBase):
    ingested_at: datetime
    source: str
    merchant_id: Optional[str] = None

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Settlements
# ---------------------------------------------------------------------------

class SettlementBase(BaseModel):
    id: str
    amount: int
    fees: int = 0
    tax: int = 0
    utr: Optional[str] = None
    status: str
    created_at: Optional[datetime] = None


class SettlementOut(SettlementBase):
    merchant_id: Optional[str] = None

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Bank Statements
# ---------------------------------------------------------------------------

class BankStatementBase(BaseModel):
    bank_account: str
    entry_date: date
    description: Optional[str] = None
    reference: Optional[str] = None
    credit: int = 0
    debit: int = 0
    balance: Optional[int] = None


class BankStatementOut(BankStatementBase):
    id: int
    created_at: datetime
    merchant_id: Optional[str] = None

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Reconciliation
# ---------------------------------------------------------------------------

class ReconciliationRunOut(BaseModel):
    id: int
    started_at: datetime
    completed_at: Optional[datetime] = None
    status: str
    trigger_type: str
    total_records: int
    matched: int
    mismatched: int
    unmatched: int
    exceptions_count: int
    duration_ms: Optional[int] = None
    summary: dict = Field(default_factory=dict)

    model_config = {"from_attributes": True}


class ReconciliationResultOut(BaseModel):
    id: int
    run_id: int
    transaction_id: Optional[str] = None
    settlement_id: Optional[str] = None
    bank_stmt_id: Optional[int] = None
    match_type: str
    match_status: str
    match_score: Optional[float] = None
    expected_amount: Optional[int] = None
    actual_amount: Optional[int] = None
    difference: int = 0
    match_details: dict = Field(default_factory=dict)
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class ExceptionOut(BaseModel):
    id: int
    run_id: Optional[int] = None
    result_id: Optional[int] = None
    type: str
    severity: str
    status: str
    amount_at_risk: int
    context: dict = Field(default_factory=dict)
    created_at: datetime
    resolved_at: Optional[datetime] = None
    investigation: Optional["InvestigationOut"] = None

    model_config = {"from_attributes": True}


class ExceptionActionRequest(BaseModel):
    """Request body for approve/reject/escalate actions on exceptions."""
    action: str  # approve | reject | escalate
    reason: Optional[str] = None


class ExceptionNoteCreate(BaseModel):
    content: str


class ExceptionNoteOut(BaseModel):
    id: int
    exception_id: int
    user_id: Optional[int] = None
    content: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Investigations
# ---------------------------------------------------------------------------

class InvestigationOut(BaseModel):
    id: int
    exception_id: int
    root_cause: str
    evidence: dict
    confidence: float
    recommended_action: str
    explanation: str
    resolution_type: Optional[str] = None
    resolved_by: Optional[str] = None
    model_used: Optional[str] = None
    prompt_tokens: Optional[int] = None
    response_tokens: Optional[int] = None
    latency_ms: Optional[int] = None
    chain_of_thought: Optional[dict] = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------

class AuditLogOut(BaseModel):
    id: int
    timestamp: datetime
    entity_type: str
    entity_id: str
    action: str
    actor: str
    old_state: Optional[dict] = None
    new_state: Optional[dict] = None
    metadata_: dict = Field(default_factory=dict, alias="metadata_")

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Events (real-time ingestion)
# ---------------------------------------------------------------------------

class EventIn(BaseModel):
    """Incoming webhook-style event."""
    event_type: str  # transaction.created | settlement.processed | etc.
    payload: dict


class EventOut(BaseModel):
    id: int
    event_type: str
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Ingestion response
# ---------------------------------------------------------------------------

class IngestionResult(BaseModel):
    source: str  # csv_batch | api_realtime
    records_parsed: int
    records_stored: int
    errors: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Metrics (for the evaluation dashboard)
# ---------------------------------------------------------------------------

class ReconciliationMetrics(BaseModel):
    total_records: int
    matched: int
    mismatched: int
    unmatched: int
    exceptions_total: int
    auto_resolved: int
    escalated: int
    unresolved: int
    match_rate: float  # 0.0 - 1.0
    throughput_records_per_sec: float
    avg_ai_latency_ms: Optional[float] = None
    audit_completeness: float  # 0.0 - 1.0
