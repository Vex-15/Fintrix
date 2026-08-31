import pytest
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.models import Base
from app.utils.synthetic_data import generate_dataset
from sqlalchemy.dialects.postgresql import insert

import pytest_asyncio

@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest_asyncio.fixture(scope="function")
async def db_engine():
    # Use in-memory SQLite for tests
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    yield engine
    
    await engine.dispose()

@pytest_asyncio.fixture(scope="function")
async def db_session(db_engine):
    session_maker = async_sessionmaker(
        db_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_maker() as session:
        yield session

@pytest_asyncio.fixture(scope="function")
async def populated_db(db_session: AsyncSession):
    """Returns a DB session populated with the synthetic dataset."""
    from app.models import Transaction, Settlement, BankStatement
    
    data = generate_dataset()
    
    # 1. Insert Settlements
    setl_records = data["settlements"]
    for s in setl_records:
        db_session.add(Settlement(**s))
    await db_session.flush()

    # 2. Insert Transactions
    txn_records = [{**t, "source": "csv_batch"} for t in data["transactions"]]
    for t in txn_records:
        db_session.add(Transaction(**t))
    await db_session.flush()

    # 3. Insert Bank Statements
    for b in data["bank_statements"]:
        db_session.add(BankStatement(**b))
    await db_session.flush()
    
    await db_session.commit()
    
    # Return the session and the ground truth dict
    return db_session, data["ground_truth"]
