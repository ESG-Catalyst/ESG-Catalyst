"""FastAPI entrypoint for the ESG Catalyst API (Iteration 1)."""

from __future__ import annotations

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api import auth, documents, metrics, pipeline, reports, scoring
from app.config import settings
from app.core.exceptions import (
    ESGCatalystError,
    ExtractionError,
    IngestionError,
    LLMUnavailableError,
    ReportError,
    ScoringError,
)
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
# Global exception handlers — map the shared core.exceptions hierarchy onto
# HTTP responses. These fire only if a request path raises one directly; the
# pipeline raises them inside the Celery worker (workers/tasks.py), so in
# practice they are a safety net for any future direct-raise route.
# Register most-specific first (FastAPI matches by exact type).
# ---------------------------------------------------------------------------


@app.exception_handler(LLMUnavailableError)
async def _llm_unavailable_handler(request: Request, exc: LLMUnavailableError) -> JSONResponse:
    """Both primary and fallback LLM failed (billing / quota) -> 503."""
    return JSONResponse(
        status_code=503,
        content={"detail": "LLM service is temporarily unavailable. Please try again later."},
    )


@app.exception_handler(IngestionError)
async def _ingestion_error_handler(request: Request, exc: IngestionError) -> JSONResponse:
    """File could not be parsed — bad input -> 422."""
    return JSONResponse(status_code=422, content={"detail": f"Document ingestion failed: {exc}"})


@app.exception_handler(ExtractionError)
async def _extraction_error_handler(request: Request, exc: ExtractionError) -> JSONResponse:
    """Metric extraction failed -> 422."""
    return JSONResponse(status_code=422, content={"detail": f"Metric extraction failed: {exc}"})


@app.exception_handler(ScoringError)
async def _scoring_error_handler(request: Request, exc: ScoringError) -> JSONResponse:
    """Scoring / gap-analysis failed -> 422."""
    return JSONResponse(status_code=422, content={"detail": f"ESG scoring failed: {exc}"})


@app.exception_handler(ReportError)
async def _report_error_handler(request: Request, exc: ReportError) -> JSONResponse:
    """Report builder / renderer failed -> 500."""
    return JSONResponse(status_code=500, content={"detail": f"Report generation failed: {exc}"})


@app.exception_handler(ESGCatalystError)
async def _esg_error_handler(request: Request, exc: ESGCatalystError) -> JSONResponse:
    """Catch-all for any unhandled pipeline-level error -> 500."""
    return JSONResponse(status_code=500, content={"detail": f"Pipeline error: {exc}"})

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
