"""GRI completeness scoring — approved_count / required_for_sector.

Scores completeness against required GRI indicators loaded from
``data/gri_indicators.json``.  Never hardcode indicator lists here.
"""

from __future__ import annotations

from app.core.gri.indicators import get_all_indicators
from app.models.enums import MetricStatus


def compute_gri_score(metrics: list, indicator_codes: list[str] | None = None) -> float:
    """Compute GRI completeness as a 0–100 score.

    Args:
        metrics: Extracted metrics (duck-typed: must have ``gri_code``, ``status``).
        indicator_codes: Restrict scoring to these codes. ``None`` → all indicators.

    Returns:
        Float 0–100 representing the percentage of required indicators present.
    """
    all_indicators = get_all_indicators()
    if indicator_codes is not None:
        all_indicators = [i for i in all_indicators if i["code"] in set(indicator_codes)]

    if not all_indicators:
        return 0.0

    approved_or_extracted = {MetricStatus.approved, MetricStatus.extracted}
    metric_map = {m.gri_code: m for m in metrics}

    covered = sum(
        1 for ind in all_indicators
        if ind["code"].startswith("GRI")
        and metric_map.get(ind["code"]) is not None
        and metric_map[ind["code"]].status in approved_or_extracted
    )

    gri_total = sum(1 for ind in all_indicators if ind["code"].startswith("GRI"))
    if gri_total == 0:
        return 0.0

    return round(covered / gri_total * 100, 1)
