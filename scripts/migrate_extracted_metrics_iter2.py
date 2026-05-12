"""Iteration-2 schema migration: add finance-sector / SASB columns to extracted_metrics.

There is no Alembic in this project (Base.metadata.create_all is used). For
fresh databases nothing needs to be done — SQLAlchemy creates the new columns
automatically. For existing Postgres databases with rows you want to keep,
this script issues ALTER TABLE statements that are idempotent (it checks
information_schema before adding each column).

Run with:
    PYTHONPATH=backend python scripts/migrate_extracted_metrics_iter2.py

Reads DATABASE_URL from settings.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Allow running from project root: ensure backend/ is on PYTHONPATH
BACKEND = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import structlog
from sqlalchemy import text

from app.database import get_engine  # noqa: E402

logger = structlog.get_logger(__name__)


# (column_name, postgres_ddl_fragment, sqlite_ddl_fragment)
_NEW_COLUMNS: list[tuple[str, str, str]] = [
    ("framework", "VARCHAR(20)", "VARCHAR(20)"),
    ("metric_type", "VARCHAR(20)", "VARCHAR(20)"),
    ("sector_standard_ref", "VARCHAR(50)", "VARCHAR(50)"),
    ("currency", "VARCHAR(10)", "VARCHAR(10)"),
    ("reporting_period_start", "DATE", "DATE"),
    ("reporting_period_end", "DATE", "DATE"),
    ("breakdown", "JSONB", "TEXT"),
]


async def _existing_columns_postgres(conn) -> set[str]:
    result = await conn.execute(
        text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'extracted_metrics'"
        )
    )
    return {row[0] for row in result.fetchall()}


async def _existing_columns_sqlite(conn) -> set[str]:
    result = await conn.execute(text("PRAGMA table_info(extracted_metrics)"))
    return {row[1] for row in result.fetchall()}


async def main() -> None:
    engine = get_engine()
    dialect = engine.dialect.name
    logger.info("migration.start", dialect=dialect)

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
            stmt = f"ALTER TABLE extracted_metrics ADD COLUMN {name} {ddl}"
            logger.info("migration.adding_column", column=name, ddl=ddl)
            await conn.execute(text(stmt))
            added.append(name)

        logger.info("migration.complete", added=added, skipped=sorted(existing & {c[0] for c in _NEW_COLUMNS}))


if __name__ == "__main__":
    asyncio.run(main())