"""Gap analysis — spec Section 8 implementation.

New functions (spec §8.1–8.2):
    generate_gap_analysis()        — topic-level impact scoring
    generate_metric_gaps()         — metric-level drill-down
    generate_improvement_roadmap() — structured roadmap for report generator

Legacy (preserved for backward-compat with scorer.py:score_report()):
    GapItem dataclass
    build_gap_analysis()
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.core.gri.indicators import get_all_indicators
from app.core.scoring.fra_compliance import (
    MANDATORY_FRA_KPIS,
    FRA_KPI_REGISTRY,
    check_fra_gate,
)
from app.models.enums import MetricStatus, MetricType
from app.schemas.metric import MetricScoreOutput

# ---------------------------------------------------------------------------
# Spec §8.2 — Stage 2 readiness topics
# ---------------------------------------------------------------------------

FRA_STAGE_2_READINESS_TOPICS: dict[str, list[str]] = {
    "FINANCIAL":     ["FIN-S7", "FIN-S8", "FIN-S9"],
    "MANUFACTURING": ["MFG-E6", "MFG-S7", "MFG-S8", "MFG-G4"],
}

_PRIORITY_HIGH   = "HIGH"
_PRIORITY_MEDIUM = "MEDIUM"
_PRIORITY_LOW    = "LOW"

_HIGH_THRESHOLD   = 3.0   # potential gain points
_MEDIUM_THRESHOLD = 1.5


# ---------------------------------------------------------------------------
# 1. Topic-level gap analysis  (Spec §8.1)
# ---------------------------------------------------------------------------

def generate_gap_analysis(
    topic_scores: dict[str, float],
    topic_weights: dict[str, float],
    pillar_weights: dict[str, float],
    topic_to_pillar: dict[str, str],
) -> list[dict]:
    """Compute potential gain for each topic and assign priority.

    Spec: Section 8.1
    Impact = topic_weight * pillar_weight * (1 - current_score) * 100

    Args:
        topic_scores:    {topic_id: score_0_to_1}  e.g. {'FIN-E1': 0.72, ...}
        topic_weights:   {topic_id: weight_0_to_1} e.g. {'FIN-E1': 0.30, ...}
        pillar_weights:  {'E': 0.25, 'S': 0.40, 'G': 0.35}
        topic_to_pillar: {topic_id: pillar_char}   e.g. {'FIN-E1': 'E', ...}

    Returns:
        List of gap dicts sorted by potential_gain_points descending.
        Each dict has keys:
            topic_id, pillar, current_score, potential_gain_points,
            topic_weight, pillar_weight, priority
    """
    results: list[dict] = []

    for topic_id, score in topic_scores.items():
        t_weight = topic_weights.get(topic_id, 0.0)
        pillar   = topic_to_pillar.get(topic_id, "E")
        p_weight = pillar_weights.get(pillar, 0.0)

        gain = t_weight * p_weight * (1.0 - score) * 100

        if gain >= _HIGH_THRESHOLD:
            priority = _PRIORITY_HIGH
        elif gain >= _MEDIUM_THRESHOLD:
            priority = _PRIORITY_MEDIUM
        else:
            priority = _PRIORITY_LOW

        results.append({
            "topic_id":             topic_id,
            "pillar":               pillar,
            "current_score":        round(score, 4),
            "current_score_pct":    round(score * 100, 1),
            "potential_gain_points": round(gain, 2),
            "topic_weight":         round(t_weight, 4),
            "pillar_weight":        round(p_weight, 4),
            "priority":             priority,
        })

    results.sort(key=lambda x: x["potential_gain_points"], reverse=True)
    return results


# ---------------------------------------------------------------------------
# 2. Metric-level drill-down  (Spec §8.1)
# ---------------------------------------------------------------------------

_ACTION_TEMPLATES: dict[MetricType, str] = {
    MetricType.BINARY:       "Publish and disclose: {name}",
    MetricType.QUANTITATIVE: "Measure and report {name} with appropriate units",
    MetricType.QUALITATIVE:  "Expand disclosure to include: {criteria}",
    MetricType.Q_PLUS_QL:    "Report numeric value AND provide detailed narrative for: {name}",
}


def generate_metric_gaps(
    topic_id: str,
    metric_scores: dict[str, MetricScoreOutput],
    metric_weights: dict[str, float],
    metric_names: dict[str, str] | None = None,
    metric_types: dict[str, MetricType] | None = None,
    completeness_criteria: dict[str, list[str]] | None = None,
) -> list[dict]:
    """Drill into a single topic to show which metrics are missing or low.

    Spec: Section 8.1 (metric-level gap detail).

    Args:
        topic_id:             e.g. 'FIN-E1'
        metric_scores:        {metric_code: MetricScoreOutput}
        metric_weights:       {metric_code: weight_0_to_1}
        metric_names:         Optional {metric_code: human name}
        metric_types:         Optional {metric_code: MetricType}
        completeness_criteria: Optional {metric_code: [criteria strings]}

    Returns:
        List of metric gap dicts sorted by weighted_gap descending.
        Each dict has: metric_code, name, score, gap, weighted_gap,
                       fra_required, priority, action
    """
    metric_names_clean:    dict[str, str]       = metric_names or {}
    metric_types_clean:    dict[str, MetricType] = dict(metric_types or {})
    criteria_clean:        dict[str, list[str]]  = completeness_criteria or {}

    results: list[dict] = []

    all_codes = set(metric_weights) | set(metric_scores)
    for code in all_codes:
        result = metric_scores.get(code)
        score  = result.raw_score if result else 0.0
        gap    = 1.0 - score
        w      = metric_weights.get(code, 0.0)
        weighted_gap = gap * w

        mt   = metric_types_clean.get(code) or MetricType.QUANTITATIVE
        name = metric_names_clean.get(code) or code
        criteria_list = criteria_clean.get(code) or []
        criteria_str  = ", ".join(criteria_list) if criteria_list else name

        action_tpl = _ACTION_TEMPLATES.get(mt, _ACTION_TEMPLATES[MetricType.QUANTITATIVE])
        action = action_tpl.format(name=name, criteria=criteria_str)

        if weighted_gap >= 0.1:
            priority = _PRIORITY_HIGH
        elif weighted_gap >= 0.05:
            priority = _PRIORITY_MEDIUM
        else:
            priority = _PRIORITY_LOW

        results.append({
            "topic_id":     topic_id,
            "metric_code":  code,
            "name":         name,
            "metric_type":  mt.value,
            "score":        round(score, 4),
            "gap":          round(gap, 4),
            "weighted_gap": round(weighted_gap, 4),
            "weight":       round(w, 4),
            "fra_required": result.fra_required if result else False,
            "priority":     priority,
            "action":       action,
        })

    results.sort(key=lambda x: x["weighted_gap"], reverse=True)
    return results


# ---------------------------------------------------------------------------
# 3. Improvement roadmap  (Spec §8.2)
# ---------------------------------------------------------------------------

def generate_improvement_roadmap(
    gap_analysis_results: list[dict],
    fra_gate_result: dict,
    sector: str,
    fra_kpi_results: dict[str, dict] | None = None,
) -> dict:
    """Organize gaps into actionable categories for the report.

    Spec: Section 8.2.

    Categories:
        immediate_actions   — FRA mandatory KPIs that are absent (must fix first)
        high_priority       — topics with potential_gain >= 3.0 pts
        medium_priority     — topics with potential_gain >= 1.5 pts
        stage2_preparation  — sector-specific Stage 2 readiness topics

    Args:
        gap_analysis_results: Output of generate_gap_analysis().
        fra_gate_result:      Output of check_fra_gate().
        sector:               'financial' | 'manufacturing' (case-insensitive).
        fra_kpi_results:      Optional raw KPI results for richer immediate_actions detail.

    Returns:
        Structured roadmap dict suitable for JSON serialisation and report rendering.
    """
    sector_key = sector.upper()
    stage2_topics = set(FRA_STAGE_2_READINESS_TOPICS.get(sector_key, []))

    # -- Immediate: missing mandatory FRA KPIs --------------------------------
    missing_mandatory = fra_gate_result.get("missing_mandatory", [])
    immediate_actions: list[dict] = []
    for kpi_code in missing_mandatory:
        meta = FRA_KPI_REGISTRY.get(kpi_code, {})
        result = (fra_kpi_results or {}).get(kpi_code, {})
        immediate_actions.append({
            "fra_kpi":    kpi_code,
            "topic":      meta.get("topic", kpi_code),
            "pillar":     meta.get("pillar", "?"),
            "description": meta.get("description", ""),
            "current_score": round(float(result.get("score", 0.0)), 4),
            "action":     f"Disclose mandatory FRA KPI {kpi_code}: {meta.get('topic', '')}",
            "urgency":    "CRITICAL",
        })

    # -- High / Medium / Stage-2 from topic gap results -----------------------
    high_priority:   list[dict] = []
    medium_priority: list[dict] = []
    stage2_prep:     list[dict] = []

    for gap in gap_analysis_results:
        tid  = gap["topic_id"]
        gain = gap["potential_gain_points"]

        row = {
            "topic_id":             tid,
            "pillar":               gap["pillar"],
            "current_score_pct":    gap["current_score_pct"],
            "potential_gain_points": gain,
            "priority":             gap["priority"],
        }

        if tid in stage2_topics:
            stage2_prep.append({**row, "stage2_note": "Benchmark data required for Stage 2 scoring"})

        if gain >= _HIGH_THRESHOLD:
            high_priority.append(row)
        elif gain >= _MEDIUM_THRESHOLD:
            medium_priority.append(row)

    return {
        "sector":            sector,
        "gate_passed":       fra_gate_result.get("gate_passed", False),
        "immediate_actions": immediate_actions,
        "high_priority":     high_priority,
        "medium_priority":   medium_priority,
        "stage2_preparation": stage2_prep,
        "summary": {
            "n_immediate":  len(immediate_actions),
            "n_high":       len(high_priority),
            "n_medium":     len(medium_priority),
            "n_stage2":     len(stage2_prep),
        },
    }


# ---------------------------------------------------------------------------
# Legacy — GapItem dataclass + build_gap_analysis()
# Preserved byte-for-byte so scorer.py:score_report() does not break.
# ---------------------------------------------------------------------------

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

    LEGACY — uses indicator status/confidence as proxy.
    Use generate_gap_analysis() for the spec-compliant implementation.

    Args:
        metrics: All extracted metrics for a report.
        confidence_threshold: Below this threshold -> flag as low_confidence.
        indicator_codes: Restrict to these codes. None -> all indicators.

    Returns:
        Ordered list of GapItem (high priority first).
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

    priority_order = {"high": 0, "medium": 1, "low": 2}
    gaps.sort(key=lambda g: priority_order.get(g.priority, 3))
    return gaps


def _assess_indicator(indicator: dict, metric: Any, confidence_threshold: float) -> GapItem | None:
    """Return a GapItem if the indicator needs attention, or None if fully covered.

    Args:
        indicator: Indicator metadata dict from ``gri_indicators.json``.
        metric: Extracted metric ORM/schema object, or None if not present.
        confidence_threshold: LLM confidence below which a metric is flagged.

    Returns:
        A ``GapItem`` describing the gap or ``None`` if no action is required.
    """
    code           = indicator["code"]
    name           = indicator["name"]
    pillar         = indicator.get("pillar", "E")
    materiality    = indicator.get("materiality_score", 0.5)
    primary_source = indicator.get("primary_source", "sustainability report")

    priority = "high" if materiality >= 0.7 else "medium" if materiality >= 0.4 else "low"

    if metric is None:
        return GapItem(
            code=code, name=name, pillar=pillar, status="missing", confidence=0.0,
            priority=priority,
            why_it_matters=indicator.get("why_it_matters", "Required for framework compliance."),
            source_document=primary_source,
            recommendation=f"No data found. Look in: {primary_source}.",
        )

    if metric.status == MetricStatus.missing:
        return GapItem(
            code=code, name=name, pillar=pillar, status="missing", confidence=0.0,
            priority=priority,
            why_it_matters=indicator.get("why_it_matters", "Required for framework compliance."),
            source_document=primary_source,
            recommendation=f"No data found. Look in: {primary_source}.",
        )

    if metric.status == MetricStatus.rejected:
        return GapItem(
            code=code, name=name, pillar=pillar, status="rejected",
            confidence=metric.confidence, priority=priority,
            why_it_matters=indicator.get("why_it_matters", "Required for framework compliance."),
            source_document=primary_source,
            recommendation=f"Value was rejected. Re-extract from: {primary_source}.",
        )

    if metric.status == MetricStatus.ambiguous:
        return GapItem(
            code=code, name=name, pillar=pillar, status="ambiguous",
            confidence=metric.confidence, priority=priority,
            why_it_matters=indicator.get("why_it_matters", "Required for framework compliance."),
            source_document=primary_source,
            recommendation=(
                f"Value is ambiguous (confidence {metric.confidence:.0%}). "
                f"Verify against: {primary_source}."
            ),
        )

    if metric.status == MetricStatus.extracted and metric.confidence < confidence_threshold:
        return GapItem(
            code=code, name=name, pillar=pillar, status="low_confidence",
            confidence=metric.confidence, priority=priority,
            why_it_matters=indicator.get("why_it_matters", "Required for framework compliance."),
            source_document=primary_source,
            recommendation=(
                f"Confidence {metric.confidence:.0%} below {confidence_threshold:.0%} threshold. "
                f"Review evidence or re-extract from: {primary_source}."
            ),
        )

    return None
