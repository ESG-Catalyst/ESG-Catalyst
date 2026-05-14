"""FastAPI entrypoint for the ESG Catalyst API (Iteration 1)."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import documents, metrics, pipeline, reports, scoring
from app.config import settings
from app.database import Base, get_engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create tables on startup (SQLite dev convenience)."""
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield


app = FastAPI(
    title="ESG Catalyst API",
    description="AI-powered ESG reporting and scoring platform",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.include_router(documents.router)
app.include_router(pipeline.router)
app.include_router(metrics.router)
app.include_router(reports.router)
app.include_router(scoring.router)


@app.get("/health")
async def health():
    return {"status": "ok", "environment": settings.environment}
