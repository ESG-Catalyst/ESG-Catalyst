"""FastAPI entrypoint for the ESG Catalyst API (Iteration 1)."""

from __future__ import annotations

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI

from app.api import auth, documents, metrics, pipeline, reports, scoring
from app.config import settings
from app.database import Base, get_engine

log: structlog.BoundLogger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create tables on startup (SQLite dev convenience; production uses migrations)."""
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    log.info("app.startup", environment=settings.environment)
    yield
    log.info("app.shutdown")


app = FastAPI(
    title="ESG Catalyst API",
    description="AI-powered ESG reporting and scoring platform",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# RECONCILE: register core.exceptions handlers here
#
# Agent C (core/exceptions.py) will provide a shared exception hierarchy and
# a wire-up snippet for global FastAPI exception handlers.  Once that module
# exists, import it and call:
#
#     from app.core.exceptions import register_exception_handlers
#     register_exception_handlers(app)
#
# This should replace any bare ``except Exception`` → 500 paths that remain
# in this file and, optionally, supplement the per-router handlers added in
# this refactor pass.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Router registration (alphabetical within logical groups)
# ---------------------------------------------------------------------------

# Auth — no prefix clash; login/register at /api/v1/auth/*, admin at /api/v1/admin/*
app.include_router(auth.router)
app.include_router(auth.admin_router)

# Core pipeline flow
app.include_router(documents.router)
app.include_router(pipeline.router)
app.include_router(metrics.router)
app.include_router(reports.router)

# Scoring / analytics
app.include_router(scoring.router)


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


@app.get("/health", tags=["health"])
async def health() -> dict:
    """Return a minimal liveness probe response."""
    return {"status": "ok", "environment": settings.environment}
