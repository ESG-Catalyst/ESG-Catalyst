"""One-off, idempotent backfill of pillar / topic on existing ExtractedMetric rows.

`pillar` + `topic` were added to the ExtractedMetric contract on 2026-05-18.
New extractions populate them, but rows persisted before that have them NULL.
This script fills them deterministically from the GRI indicator catalogue:

  * pillar -> indicator["pillar"] ("E" | "S" | "G") for the row's gri_code
  * topic  -> extractor._derive_topic(gri_code)  (e.g. "GRI 305-1" -> "GRI 305")

Idempotent: only rows where pillar IS NULL or topic IS NULL are touched, and
each field is only set when it is currently NULL and a value can be derived.
Safe to re-run. Reads DATABASE_URL from settings.

Run (project root):
    PYTHONPATH=backend python scripts/backfill_metric_pillar_topic.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import structlog
from sqlalchemy import or_, select

from app.core.extraction.extractor import _derive_topic  # noqa: E402
from app.core.gri.indicators import get_all_indicators  # noqa: E402
from app.database import get_engine, get_session_factory  # noqa: E402
from app.models.enums import PillarType  # noqa: E402
from app.models.metric import ExtractedMetric  # noqa: E402

logger = structlog.get_logger(__name__)


async def main() -> None:
    pillar_by_code: dict[str, str] = {}
    for ind in get_all_indicators():
        code = ind.get("code")
        pillar = ind.get("pillar")
        if code and pillar in ("E", "S", "G"):
            pillar_by_code[code] = pillar

    Session = get_session_factory()
    scanned = pillar_set = topic_set = no_pillar = 0

    async with Session() as session:
        rows = (
            await session.execute(
                select(ExtractedMetric).where(
                    or_(
                        ExtractedMetric.pillar.is_(None),
                        ExtractedMetric.topic.is_(None),
                    )
                )
            )
        ).scalars().all()

        for m in rows:
            scanned += 1
            if m.pillar is None:
                p = pillar_by_code.get(m.gri_code)
                if p is not None:
                    m.pillar = PillarType(p)
                    pillar_set += 1
                else:
                    no_pillar += 1
            if m.topic is None:
                t = _derive_topic(m.gri_code)
                if t:
                    m.topic = t
                    topic_set += 1

        await session.commit()

    await get_engine().dispose()
    logger.info(
        "backfill.complete",
        scanned=scanned,
        pillar_set=pillar_set,
        topic_set=topic_set,
        rows_without_indicator_pillar=no_pillar,
    )


if __name__ == "__main__":
    asyncio.run(main())