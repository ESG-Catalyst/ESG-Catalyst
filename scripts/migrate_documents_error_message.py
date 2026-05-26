"""Documents schema migration: add ``error_message`` column.

Adds a nullable TEXT column so the ingestion task can persist a
human-readable failure reason (e.g. "image OCR is not yet implemented")
that the UI can surface instead of a generic spinner.

There is no Alembic in this project (Base.metadata.create_all is used).
For a fresh database nothing needs to be done — SQLAlchemy creates the
column automatically. For an existing Postgres (or SQLite) database
with rows you want to keep, this script issues an idempotent
ALTER TABLE (information_schema / PRAGMA checked first; safe to re-run).

Run with (project root):
    PYTHONPATH=backend python scripts/migrate_documents_error_message.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import structlog
from sqlalchemy import text

from app.database import get_engine  # noqa: E402

logger = structlog.get_logger(__name__)

_NEW_COLUMNS: list[tuple[str, str, str]] = [
    ("error_message", "TEXT", "TEXT"),
]


async def _existing_columns_postgres(conn) -> set[str]:
    result = await conn.execute(
        text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'documents'"
        )
    )
    return {row[0] for row in result.fetchall()}


async def _existing_columns_sqlite(conn) -> set[str]:
    result = await conn.execute(text("PRAGMA table_info(documents)"))
    return {row[1] for row in result.fetchall()}


async def main() -> None:
    engine = get_engine()
    dialect = engine.dialect.name
    logger.info("migration.start", dialect=dialect, script="documents_error_message")

    async with engine.begin() as conn:
        if dialect == "postgresql":
            existing = await _existing_columns_postgres(conn)
            ddl_idx = 1
        elif dialect == "sqlite":
            existing = await _existing_columns_sqlite(conn)
            ddl_idx = 2
        else:
            logger.warning("migration.unknown_dialect_using_generic_types", dialect=dialect)
            existing = set()
            ddl_idx = 1

        added: list[str] = []
        for name, *ddls in _NEW_COLUMNS:
            if name in existing:
                logger.info("migration.column_exists_skip", column=name)
                continue
            ddl = ddls[ddl_idx - 1]
            stmt = f"ALTER TABLE documents ADD COLUMN {name} {ddl}"
            logger.info("migration.adding_column", column=name, ddl=ddl)
            await conn.execute(text(stmt))
            added.append(name)

        logger.info("migration.complete", added=added, skipped=sorted(existing & {c[0] for c in _NEW_COLUMNS}))


if __name__ == "__main__":
    asyncio.run(main())
