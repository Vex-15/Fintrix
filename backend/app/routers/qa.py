"""
Q&A API — Natural-language question answering over financial data.
"""

from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.settlement_qa import ask_question

router = APIRouter()


class QARequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=500)


class QAResponse(BaseModel):
    question: str
    answer: str
    data: list = Field(default_factory=list)
    sql: str | None = None
    source: str


@router.post("/ask", response_model=QAResponse)
async def ask(
    body: QARequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Ask a natural-language question about settlements, exceptions,
    reconciliation data, risk, or financial metrics.

    Examples:
    - "How many exceptions were detected?"
    - "What is the total amount at risk?"
    - "Show me all high severity exceptions"
    - "What is the average AI investigation confidence?"
    - "List settlements with missing bank entries"
    """
    result = await ask_question(db, body.question)
    return result
