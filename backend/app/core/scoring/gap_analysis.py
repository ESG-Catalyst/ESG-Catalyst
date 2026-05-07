"""Gap analysis — identify missing disclosures and generate recommendations.

For each indicator that is missing, ambiguous, or low-confidence, generates
a structured GapItem with:
- Why it matters (materiality context)
- What document type would contain it
- Priority: high / medium / low based on materiality score
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.gri.indicators import get_all_indicators
from app.models.enums import MetricStatus


@dataclass
class GapItem:
    """One missing or incomplete indicator with a remediation hint."""

    code: str
    name: str
    pillar: str        # "E", "S", or "G"
    status: str        # "missing" | "ambiguous" | "low_confidence" | "rejected"
    confidence: float
    priority: str      # "high" | "medium" | "low"
    why_it_matters: str
    source_document: str
    recommendation: str


def build_gap_analysis(
    metrics: list,
    confidence_threshold: float = 0.80,
    indicator_codes: list[str] | None = None,
) -> list[GapItem]:
    """Generate gap items for all indicators that are not fully covered.

    Args:
        metrics: All extracted metrics for a report.
        confidence_threshold: Below this → flag as low_confidence.
        indicator_codes: Restrict to these codes. ``None`` → all indicators.

    Returns:
        Ordered list of ``GapItem`` (high priority first).
    """
    all_indicators = get_all_indicators()
    if indicator_codes is not None:
        all_indicators = [i for i in all_indicators if i["code"] in set(indicator_codes)]

    metric_map = {m.gri_code: m for m in metrics}
    gaps: list[GapItem] = []

    for ind in all_indicators:
        code = ind["code"]
        metric = metric_map.get(code)
        gap = _assess_indicator(ind, metric, confidence_threshold)
        if gap:
            gaps.append(gap)

    # Sort: high → medium → low
    priority_order = {"high": 0, "medium": 1, "low": 2}
    gaps.sort(key=lambda g: priority_order.get(g.priority, 3))
    return gaps


def _assess_indicator(
    indicator: dict,
    metric,
    confidence_threshold: float,
) -> GapItem | None:
    """Return a GapItem if the indicator needs attention, else None."""
    code = indicator["code"]
    name = indicator["name"]
    pillar = indicator.get("pillar", "E")
    materiality = indicator.get("materiality_score", 0.5)
    primary_source = indicator.get("primary_source", "sustainability report")

    priority = "high" if materiality >= 0.7 else "medium" if materiality >= 0.4 else "low"

    if metric is None:
        return GapItem(
            code=code,
            name=name,
            pillar=pillar,
            status="missing",
            confidence=0.0,
            priority=priority,
            why_it_matters=indicator.get("why_it_matters", "Required for framework compliance."),
            source_document=primary_source,
            recommendation=f"No data found. Look in: {primary_source}.",
        )

    if metric.status == MetricStatus.rejected:
        return GapItem(
            code=code,
            name=name,
            pillar=pillar,
            status="rejected",
            confidence=metric.confidence,
            priority=priority,
            why_it_matters=indicator.get("why_it_matters", "Required for framework compliance."),
            source_document=primary_source,
            recommendation=f"Value was rejected. Re-extract from: {primary_source}.",
        )

    if metric.status == MetricStatus.ambiguous:
        return GapItem(
            code=code,
            name=name,
            pillar=pillar,
            status="ambiguous",
            confidence=metric.confidence,
            priority=priority,
            why_it_matters=indicator.get("why_it_matters", "Required for framework compliance."),
            source_document=primary_source,
            recommendation=(
                f"Value is ambiguous (confidence {metric.confidence:.0%}). "
                f"Verify against: {primary_source}."
            ),
        )

    if metric.status == MetricStatus.extracted and metric.confidence < confidence_threshold:
        return GapItem(
            code=code,
            name=name,
            pillar=pillar,
            status="low_confidence",
            confidence=metric.confidence,
            priority=priority,
            why_it_matters=indicator.get("why_it_matters", "Required for framework compliance."),
            source_document=primary_source,
            recommendation=(
                f"Confidence {metric.confidence:.0%} below {confidence_threshold:.0%} threshold. "
                f"Review evidence or re-extract from: {primary_source}."
            ),
        )

    return None
