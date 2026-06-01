"""Async SQLAlchemy engine, session factory, and FastAPI dependency.

Design decisions
----------------
NullPool (INTENTIONAL — do not revert)
    Celery's solo pool calls ``asyncio.run()`` once per task, which creates and
    then closes a fresh event loop.  SQLAlchemy's default connection pool caches
    asyncpg transports that are bound to that now-closed loop.  On the second
    task, ``pool_pre_ping=True`` fires on those stale connections, which raises
    ``AttributeError: 'NoneType' object has no attribute 'send'`` deep inside
    asyncpg.  Switching to ``NullPool`` means every ``async with session:``
    opens a fresh asyncpg connection on the *current* loop and closes it on
    release — no cross-task transport sharing.  See CLAUDE.md session log
    2026-05-11 for the full investigation.

Lazy initialisation
    The engine and session factory are created on first use via ``lru_cache``,
    not at module import time.  This lets pipeline code import ORM models
    (which only need ``Base``) without triggering an asyncpg connection or
    requiring a live database.  Useful for CLI scripts, tests, and model-only
    usage.

Usage (FastAPI)
    from app.database import get_db

    @router.get("/items")
    async def list_items(db: AsyncSession = Depends(get_db)):
        ...

Usage (Celery tasks / scripts)
    from app.database import get_session_factory

    async def _run():
        async with get_session_factory()() as session:
            ...
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from functools import lru_cache

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from app.config import settings


# ---------------------------------------------------------------------------
# Declarative base — all ORM models inherit from this.
# Defined before the engine so model modules can import ``Base`` without
# triggering a database connection.
# ---------------------------------------------------------------------------
class Base(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models in this project."""


# ---------------------------------------------------------------------------
# Lazy engine — created once per process, cached by lru_cache.
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def get_engine() -> AsyncEngine:
    """Create and cache the async SQLAlchemy engine (one per process).

    Uses ``NullPool`` so every connection checkout opens a fresh asyncpg
    connection on the current event loop and closes it on release.  This is
    intentional — see module docstring for the full rationale.

    The ``echo`` flag mirrors ``settings.environment == "development"`` so
    SQL queries are printed to stdout during local development and suppressed
    in staging/production.

    Returns:
        A configured ``AsyncEngine`` instance.
    """
    return create_async_engine(
        settings.database_url,
        echo=settings.environment == "development",
        poolclass=NullPool,
    )


# ---------------------------------------------------------------------------
# Lazy session factory — created once per process, cached by lru_cache.
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Create and cache the async session factory (one per process).

    ``expire_on_commit=False`` prevents SQLAlchemy from expiring ORM objects
    after ``session.commit()``, which would require a re-query to access any
    attribute on a just-committed row.  This is the correct default for async
    code where lazy-loading is not available.

    Returns:
        An ``async_sessionmaker`` bound to the cached engine.
    """
    return async_sessionmaker(
        bind=get_engine(),
        expire_on_commit=False,
        class_=AsyncSession,
    )


# ---------------------------------------------------------------------------
# FastAPI dependency — yields a session per request.
# ---------------------------------------------------------------------------
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async database session for use as a FastAPI ``Depends`` dependency.

    Commits automatically on a clean exit.  Rolls back and re-raises on any
    exception so the caller's error handling is not masked.

    Yields:
        An ``AsyncSession`` scoped to the current request.
    """
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
