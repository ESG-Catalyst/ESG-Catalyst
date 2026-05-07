from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import auth, companies, documents, metrics, pipeline, reports
from app.config import settings
from app.database import Base, get_engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create database tables on startup (for SQLite local dev)."""
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

# ── Routers ──────────────────────────────────────────────────────────────
app.include_router(auth.router)
app.include_router(companies.router)
app.include_router(documents.router)
app.include_router(pipeline.router)
app.include_router(metrics.router)
app.include_router(reports.router)


@app.get("/health")
async def health():
    return {"status": "ok", "environment": settings.environment}
