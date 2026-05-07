"""Materiality assessment — sector-specific topic relevance mapping.

Loads from ``data/sasb_standards.json``.  Never hardcode sector data.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)

_DATA_FILE = Path(__file__).resolve().parents[4] / "data" / "sasb_standards.json"


@lru_cache(maxsize=1)
def _load_sasb() -> dict:
    with open(_DATA_FILE) as f:
        return json.load(f)


def get_material_topics(sector: str) -> dict[str, float]:
    """Return the materiality map (topic → weight 0-1) for a sector.

    Falls back to ``"default"`` sector if the given sector is unknown.

    Args:
        sector: Sector key (e.g. ``"banking"``, ``"software"``).

    Returns:
        Dict mapping SASB topic code → materiality weight.
    """
    try:
        data = _load_sasb()
    except FileNotFoundError:
        logger.warning("materiality.file_missing", path=str(_DATA_FILE))
        return {}

    sectors = data.get("sectors", {})
    sector_data = sectors.get(sector) or sectors.get("default", {})
    return sector_data.get("material_topics", {})


def get_industry_average(sector: str) -> float | None:
    """Return the industry average ESG score for benchmark comparison.

    Args:
        sector: Sector key.

    Returns:
        Industry average as a 0–100 float, or ``None`` if unavailable.
    """
    try:
        data = _load_sasb()
    except FileNotFoundError:
        return None

    sectors = data.get("sectors", {})
    sector_data = sectors.get(sector) or sectors.get("default", {})
    return sector_data.get("industry_average_score")
