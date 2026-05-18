"""Scoring-engine schema migration: add the spec §1–2 scoring columns
(plus the contract-level ``pillar`` / ``topic`` fields) to extracted_metrics.

This is the companion to ``migrate_extracted_metrics_iter2.py``. iter2 added the
7 finance-sector / SASB columns; this script adds the 15 scoring-engine columns
declared on the ``ExtractedMetric`` ORM model (esg_scoring_framework.md) **and**
the two metric-contract columns ``pillar`` / ``topic`` that the review UI and
report generator group by.

There is no Alembic in this project (Base.metadata.create_all is used). For a
fresh database nothing needs to be done — SQLAlchemy creates the columns
automatically. For an existing Postgres (or SQLite) database with rows you want
to keep, this script issues idempotent ALTER TABLE statements (it checks
information_schema / PRAGMA before adding each column, and is safe to re-run).

Enum-typed columns are stored as VARCHAR — the same convention iter2 chose, so
the SQLAlchemy ``Enum`` result processor coerces the string back to the Python
enum on read and binds the enum value on write without needing native PG enum
types.

Run with (project root):
    PYTHONPATH=backend python scripts/migrate_extracted_metrics_scoring.py

Reads DATABASE_URL from settings. Run iter2 first, then this one.
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
from sqlalchemy import Enum as SAEnum
from sqlalchemy import text

from app.database import get_engine  # noqa: E402
from app.models.metric import ExtractedMetric  # noqa: E402

logger = structlog.get_logger(__name__)


# (column_name, postgres_ddl_fragment, sqlite_ddl_fragment)
# Enum columns use VARCHAR to mirror migrate_extracted_metrics_iter2.py.
# NOT NULL columns carry a DEFAULT so existing rows back-fill cleanly.
_NEW_COLUMNS: list[tuple[str, str, str]] = [
    # ── Scoring-engine columns (esg_scoring_framework.md §1–2) ──────────────
    ("metric_code", "VARCHAR(100)", "VARCHAR(100)"),
    ("framework_source", "VARCHAR(20)", "VARCHAR(20)"),
    ("sector", "VARCHAR(20)", "VARCHAR(20)"),
    # SQLAlchemy's native Enum() binds the enum MEMBER NAME ("GOVERNANCE"),
    # not its value ("G"), so this must fit the longest PillarType name.
    ("pillar", "VARCHAR(20)", "VARCHAR(20)"),
    ("topic_id", "VARCHAR(20)", "VARCHAR(20)"),
    ("weight_in_topic", "FLOAT", "FLOAT"),
    ("fra_required", "BOOLEAN NOT NULL DEFAULT false", "BOOLEAN NOT NULL DEFAULT 0"),
    ("fra_kpi_code", "VARCHAR(10)", "VARCHAR(10)"),
    ("direction", "VARCHAR(20)", "VARCHAR(20)"),
    ("benchmark", "FLOAT", "FLOAT"),
    ("completeness_criteria", "JSONB", "TEXT"),
    ("q_weight", "FLOAT NOT NULL DEFAULT 0.6", "FLOAT NOT NULL DEFAULT 0.6"),
    ("ql_weight", "FLOAT NOT NULL DEFAULT 0.4", "FLOAT NOT NULL DEFAULT 0.4"),
    ("extraction_keywords", "JSONB", "TEXT"),
    ("data_availability_score", "FLOAT", "FLOAT"),
    # ── Metric-contract columns (ExtractedMetricSchema pillar/topic) ────────
    # `pillar` is already in the scoring block above (Enum PillarType).
    ("topic", "VARCHAR(120)", "VARCHAR(120)"),
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


def _create_native_enum_types(sync_conn) -> list[str]:
    """Create the native Postgres enum types the ORM's Enum() columns cast to.

    iter2/this script store enum columns as VARCHAR, but the ORM declares them
    as SQLAlchemy ``Enum(PyEnum)`` (native_enum default True). On INSERT,
    SQLAlchemy emits ``$n::<typename>`` casts, which fail unless the PG enum
    type exists. We let SQLAlchemy itself emit ``CREATE TYPE`` (correct labels,
    idempotent via checkfirst) for every Enum column on extracted_metrics.
    """
    created: list[str] = []
    for col in ExtractedMetric.__table__.columns:
        coltype = col.type
        if isinstance(coltype, SAEnum) and coltype.native_enum:
            coltype.create(sync_conn, checkfirst=True)
            created.append(coltype.name or col.name)
    return created


async def main() -> None:
    engine = get_engine()
    dialect = engine.dialect.name
    logger.info("migration.start", dialect=dialect, script="scoring")

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

        # Correct an earlier under-sized pillar column (a prior version of this
        # script created it as VARCHAR(2)). Idempotent: only widens if needed.
        if dialect == "postgresql":
            cur_len = (await conn.execute(text(
                "SELECT character_maximum_length FROM information_schema.columns "
                "WHERE table_name='extracted_metrics' AND column_name='pillar'"
            ))).scalar()
            if cur_len is not None and cur_len < 20:
                logger.info("migration.widening_pillar", from_len=cur_len, to_len=20)
                await conn.execute(text(
                    "ALTER TABLE extracted_metrics ALTER COLUMN pillar TYPE VARCHAR(20)"
                ))

        enum_types: list[str] = []
        if dialect == "postgresql":
            enum_types = await conn.run_sync(_create_native_enum_types)
            logger.info("migration.enum_types_ensured", types=sorted(set(enum_types)))

        logger.info(
            "migration.complete",
            added=added,
            skipped=sorted(existing & {c[0] for c in _NEW_COLUMNS}),
            enum_types_ensured=sorted(set(enum_types)),
        )


if __name__ == "__main__":
    asyncio.run(main())