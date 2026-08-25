"""
Fintrix — AI Finance Controller
FastAPI application entry point.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import init_db, close_db, async_session
from app.routers import (
    ingest, reconciliation, exceptions, audit, events,
    auth, webhooks, api_keys, export, analytics, websocket,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: create tables, default admin, scheduler. Shutdown: close DB pool."""
    await init_db()

    # Create default admin user and merchant
    from app.services.auth import ensure_default_admin
    async with async_session() as db:
        await ensure_default_admin(db)

    # Start scheduler
    from app.services.scheduler import init_scheduler, stop_scheduler
    init_scheduler()

    yield

    stop_scheduler()
    await close_db()


app = FastAPI(
    title="Fintrix — AI Finance Controller",
    description="Automated financial reconciliation with AI-powered exception investigation.",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Auth & Security ──────────────────────────────────────────────────────────
app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(api_keys.router, prefix="/api/api-keys", tags=["API Keys"])
app.include_router(webhooks.router, prefix="/api/webhooks", tags=["Webhooks"])

# ── Core Features ────────────────────────────────────────────────────────────
app.include_router(ingest.router, prefix="/api/ingest", tags=["Ingestion"])
app.include_router(reconciliation.router, prefix="/api/reconciliation", tags=["Reconciliation"])
app.include_router(exceptions.router, prefix="/api/exceptions", tags=["Exceptions"])

# ── Audit & Events ───────────────────────────────────────────────────────────
app.include_router(audit.router, prefix="/api/audit", tags=["Audit"])
app.include_router(events.router, prefix="/api/events", tags=["Events"])

# ── Analytics & Export ───────────────────────────────────────────────────────
app.include_router(analytics.router, prefix="/api/analytics", tags=["Analytics"])
app.include_router(export.router, prefix="/api/export", tags=["Export"])

# ── Real-time ────────────────────────────────────────────────────────────────
app.include_router(websocket.router, prefix="/api", tags=["WebSocket"])


@app.get("/health")
async def health():
    return {"status": "ok", "service": "fintrix-backend", "version": "1.0.0"}


@app.get("/api/scheduler/status")
async def scheduler_status():
    """Get scheduler status and job information."""
    from app.services.scheduler import get_scheduler_status
    return get_scheduler_status()
