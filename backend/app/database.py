from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

engine_options = {
    "echo": False,
    "pool_pre_ping": True,
}
if settings.database_url.startswith("sqlite"):
    engine_options["connect_args"] = {"timeout": 30}

engine = create_async_engine(settings.database_url, **engine_options)


def _configure_sqlite(connection, _record):
    """Allow reads during writes and wait briefly instead of failing on locks."""
    if settings.database_url.startswith("sqlite"):
        cursor = connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.close()


if settings.database_url.startswith("sqlite"):
    from sqlalchemy import event

    event.listen(engine.sync_engine, "connect", _configure_sqlite)

async_session = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    """FastAPI dependency: yields an async database session."""
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def ensure_database():
    """Auto-create the 'fintrix' database if it doesn't exist."""
    if settings.database_url.startswith("sqlite"):
        return

    import asyncpg

    # Parse connection details from the URL
    url = settings.database_url
    # postgresql+asyncpg://user:pass@host:port/dbname
    parts = url.split("://", 1)[1]  # user:pass@host:port/dbname
    creds_host, db_name = parts.rsplit("/", 1)

    # Connect to the default 'postgres' database to create ours
    admin_url = f"postgresql://{creds_host}/postgres"
    try:
        conn = await asyncpg.connect(admin_url)
        exists = await conn.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1", db_name
        )
        if not exists:
            await conn.execute(f'CREATE DATABASE "{db_name}"')
            print(f"[OK] Created database '{db_name}'")
        else:
            print(f"[OK] Database '{db_name}' already exists")
        await conn.close()
    except Exception as e:
        print(f"[WARN] Could not auto-create database: {e}")
        print("  Make sure PostgreSQL is running and credentials in .env are correct.")


async def init_db():
    """Ensure database exists, then create all tables."""
    await ensure_database()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("[OK] All tables ready")


async def close_db():
    """Dispose of the engine. Called on app shutdown."""
    await engine.dispose()
