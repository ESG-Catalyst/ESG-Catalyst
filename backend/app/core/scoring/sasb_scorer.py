"""SASB sector-specific scoring — weight metrics by materiality score.

Loads sector materiality from ``data/sasb_standards.json``.
Never hardcode sector maps here.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)

_DATA_FILE = Path(__file__).resolve().parents[4] / "data" / "sasb_standards.json"


@lru_cache(maxsize=1)
def _load_sasb_standards() -> dict:
    """Load and cache SASB standards from JSON."""
    with open(_DATA_FILE) as f:
        return json.load(f)


def compute_sasb_score(metrics: list, sector: str) -> float:
    """Compute a 0–100 SASB score for the given sector.

    Args:
        metrics: Extracted metrics with ``sasb_code``, ``status``, ``confidence``.
        sector: Sector key (e.g. ``"banking"``, ``"software"``).

    Returns:
        Float 0–100 SASB coverage score.
    """
    try:
        standards = _load_sasb_standards()
    except FileNotFoundError:
        logger.warning("sasb_scorer.file_missing", path=str(_DATA_FILE))
        return 0.0

    sector_data = standards.get("sectors", {}).get(sector) or standards.get("sectors", {}).get(
        "default", {}
    )
    material_codes: dict[str, float] = sector_data.get("material_topics", {})

    if not material_codes:
        return 0.0

    metric_map = {m.sasb_code: m for m in metrics if m.sasb_code}
    total_weight = sum(material_codes.values())
    if total_weight == 0:
        return 0.0

    weighted_score = 0.0
    for code, weight in material_codes.items():
        metric = metric_map.get(code)
        if metric is not None and metric.confidence > 0:
            weighted_score += weight * metric.confidence

    return round(weighted_score / total_weight * 100, 1)
