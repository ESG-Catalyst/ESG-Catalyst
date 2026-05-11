from collections.abc import AsyncGenerator
from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from app.config import settings


# ---------------------------------------------------------------------------
# Declarative base — all ORM models inherit from this.
# Defined before engine so model modules can import it without triggering
# a database connection (asyncpg is only needed at runtime).
# ---------------------------------------------------------------------------
class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Lazy engine + session factory — created on first use, not at import time.
# This lets pipeline code import ORM models without requiring asyncpg or a
# live database (important for CLI scripts, tests, and model-only usage).
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def get_engine() -> AsyncEngine:
    """Create and cache the async engine (one per process).

    Uses ``NullPool`` so every checkout opens a fresh asyncpg connection on
    the current event loop and closes it on release. This avoids the
    'NoneType' has no attribute 'send' crash that happens when a pooled
    asyncpg transport survives across the ``asyncio.run()`` boundary that
    Celery's solo pool draws between tasks.
    """
    return create_async_engine(
        settings.database_url,
        echo=settings.environment == "development",
        poolclass=NullPool,
    )


@lru_cache(maxsize=1)
def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Create and cache the session factory (one per process)."""
    return async_sessionmaker(
        bind=get_engine(),
        expire_on_commit=False,
        class_=AsyncSession,
    )


# ---------------------------------------------------------------------------
# FastAPI dependency — yields a session per request, rolls back on error
# ---------------------------------------------------------------------------
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async database session for use as a FastAPI dependency."""
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
