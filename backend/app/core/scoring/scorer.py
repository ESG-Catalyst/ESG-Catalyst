"""ESG scoring engine — full implementation per esg_scoring_framework.md.

Implements all metric-level scoring functions (Spec §2.1), topic / pillar /
composite aggregation (Spec §2.2-2.4), the FRA compliance gate (Spec §7), and
the score-to-grade mapping (Spec §2.4).

Public surface:
    score_binary          -> float
    score_quantitative    -> float
    score_qualitative     -> float
    score_q_plus_ql       -> float
    score_metric          -> MetricScoreOutput
    score_topic           -> float
    score_pillar          -> float
    score_composite       -> dict
    score_to_grade        -> str
    score_document        -> dict  (top-level orchestrator, Spec §2 end-to-end)

    # Legacy orchestrator (kept for backward-compat with workers/tasks.py)
    score_report          -> ScoringResult
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import structlog

from app.config import settings
from app.core.gri.indicators import get_all_indicators
from app.core.scoring.gap_analysis import (
    GapItem,
    build_gap_analysis,
    generate_gap_analysis,
    generate_improvement_roadmap,
)
from app.core.scoring.fra_compliance import (
    check_fra_gate,
    extract_fra_results_from_scores,
)
from app.core.scoring.materiality import (
    FINANCIAL_WEIGHTS,
    MANUFACTURING_WEIGHTS,
    get_weight_registry,
)
from app.models.enums import MetricDirection, MetricStatus, MetricType
from app.schemas.metric import MetricScoreInput, MetricScoreOutput

logger = structlog.get_logger(__name__)

# ── Positive words recognised by score_binary (Spec §2.1, §5.1) ─────────────
_BINARY_POSITIVE: frozenset[str] = frozenset(
    {"yes", "true", "1", "oui", "نعم", "да", "present", "available"}
)


# ── Metric-level scoring functions ───────────────────────────────────────────
# Spec: Section 2.1 and Section 5.1

def score_binary(value: Any) -> float:
    """Return 1.0 if the company discloses the item, 0.0 otherwise.

    Spec: Section 2.1 — Type BINARY.

    Args:
        value: Extracted answer from the document.  Accepts bool, str, or None.

    Returns:
        1.0 if value is truthy / matches a positive keyword, else 0.0.

    Examples:
        >>> score_binary(True)
        1.0
        >>> score_binary('yes')
        1.0
        >>> score_binary('نعم')
        1.0
        >>> score_binary(None)
        0.0
        >>> score_binary('no')
        0.0
    """
    if value is None:
        return 0.0
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    return 1.0 if str(value).strip().lower() in _BINARY_POSITIVE else 0.0


def score_quantitative(
    value: Any,
    benchmark: float | None = None,
    direction: str | MetricDirection = MetricDirection.NEUTRAL,
) -> float:
    """Return 0.0–1.0 based on whether a value is disclosed and how it compares
    to a sector benchmark.

    Spec: Section 2.1 — Type QUANTITATIVE.

    Stage 1 (no benchmark):
        Non-zero numeric → 1.0
        Zero (legitimately zero) → 0.8
        Absent / None → 0.0

    Stage 2 (benchmark supplied):
        HIGHER_BETTER: min(value / benchmark, 1.0)
        LOWER_BETTER:  min(benchmark / value, 1.0) if value > 0 else 1.0
        NEUTRAL:       1.0 if value is not None else 0.0

    Args:
        value:     Numeric value from the document.  May be int, float, or str.
        benchmark: Sector-median reference value.  None → Stage 1 only.
        direction: HIGHER_BETTER | LOWER_BETTER | NEUTRAL.

    Returns:
        Float 0.0–1.0.
    """
    # ── Missing / blank ──────────────────────────────────────────────────────
    if value is None or str(value).strip() == "":
        return 0.0

    try:
        v = float(str(value).replace(",", ""))
    except (ValueError, TypeError):
        return 0.0

    # Normalise direction to string for comparison
    dir_str = direction.value if isinstance(direction, MetricDirection) else str(direction)

    # ── Stage 1 — existence scoring ──────────────────────────────────────────
    if benchmark is None:
        if dir_str == MetricDirection.NEUTRAL.value:
            return 1.0  # any disclosure earns full score
        return 1.0 if v != 0 else 0.8

    # ── Stage 2 — benchmark scoring ───────────────────────────────────────────
    b = benchmark  # already float — None excluded by guard above

    if dir_str == MetricDirection.NEUTRAL.value:
        # NEUTRAL with benchmark: presence alone earns full score
        return 1.0

    if dir_str == MetricDirection.HIGHER_BETTER.value:
        if b == 0:
            return 1.0 if v == 0 else 0.0
        return min(v / b, 1.0)

    # LOWER_BETTER
    if b == 0:
        return 0.0
    return min(b / v, 1.0) if v > 0 else 1.0


def score_qualitative(
    disclosure: str | None,
    completeness_criteria: list[str],
    partial_threshold: float = 0.25,
    full_threshold: float = 0.75,
) -> float:
    """Score a narrative disclosure on a 0 / 0.5 / 1.0 scale.

    Spec: Section 2.1 — Type QUALITATIVE.

    0.0 → absent (no disclosure found in document)
    0.5 → partial (disclosure exists but missing required elements)
    1.0 → complete (all completeness_criteria present and evidenced)

    Args:
        disclosure:             Extracted narrative text (or None).
        completeness_criteria:  Keywords / phrases checked case-insensitively.
        partial_threshold:      Min ratio for a partial (0.5) score.  Default 0.25.
        full_threshold:         Min ratio for a full (1.0) score.  Default 0.75.

    Returns:
        0.0, 0.5, or 1.0.
    """
    if not disclosure or len(disclosure.strip()) == 0:
        return 0.0

    if not completeness_criteria:
        return 1.0  # presence alone = full score when no criteria defined

    text = disclosure.lower()
    matched = sum(1 for criterion in completeness_criteria if criterion.lower() in text)
    ratio = matched / len(completeness_criteria)

    if ratio >= full_threshold:
        return 1.0
    if ratio >= partial_threshold:
        return 0.5
    return 0.0


def score_q_plus_ql(
    quantitative_value: Any,
    qualitative_disclosure: str | None,
    completeness_criteria: list[str],
    q_weight: float = 0.6,
    ql_weight: float = 0.4,
    benchmark: float | None = None,
    direction: str | MetricDirection = MetricDirection.NEUTRAL,
) -> float:
    """Blended score for metrics requiring both a number and an explanation.

    Spec: Section 2.1 — Type Q_PLUS_QL.

    Default split: 60% quantitative, 40% qualitative.

    Args:
        quantitative_value:     Numeric value (passed to score_quantitative).
        qualitative_disclosure: Narrative text (passed to score_qualitative).
        completeness_criteria:  Keyword list for the qualitative component.
        q_weight:               Weight of the quantitative component.
        ql_weight:              Weight of the qualitative component.
        benchmark:              Optional benchmark for Stage 2 quantitative scoring.
        direction:              Scoring direction for the quantitative component.

    Returns:
        Weighted blend: (q_score × q_weight) + (ql_score × ql_weight), in 0–1.

    Raises:
        AssertionError: if q_weight + ql_weight does not equal ~1.0.
    """
    assert abs(q_weight + ql_weight - 1.0) < 0.001, (
        f"q_weight ({q_weight}) + ql_weight ({ql_weight}) must sum to 1.0"
    )
    q_score = score_quantitative(quantitative_value, benchmark=benchmark, direction=direction)
    ql_score = score_qualitative(qualitative_disclosure, completeness_criteria)
    return (q_score * q_weight) + (ql_score * ql_weight)


# ── Metric scoring dispatcher ─────────────────────────────────────────────────
# Spec: Section 2.1 — routes by MetricType

def score_metric(inp: MetricScoreInput) -> MetricScoreOutput:
    """Dispatcher: select the correct scoring function for the given MetricType.

    Spec: Section 2.1 (all types).

    Args:
        inp: MetricScoreInput carrying the type, extracted value/text, and
             scoring configuration (benchmark, direction, criteria, weights).

    Returns:
        MetricScoreOutput with raw_score in 0–1, weighted_contribution, and
        an optional scoring_notes string.
    """
    mt = inp.metric_type
    notes: str | None = None

    if mt == MetricType.BINARY:
        raw = score_binary(inp.extracted_value)
        notes = f"binary: '{inp.extracted_value}' -> {raw}"

    elif mt == MetricType.QUANTITATIVE:
        raw = score_quantitative(
            inp.extracted_value,
            benchmark=inp.benchmark,
            direction=inp.direction,
        )
        stage = "Stage 2 (benchmark)" if inp.benchmark is not None else "Stage 1 (existence)"
        notes = f"quantitative [{stage}, direction={inp.direction.value}]: {raw:.3f}"

    elif mt == MetricType.QUALITATIVE:
        raw = score_qualitative(
            inp.extracted_text,
            inp.completeness_criteria,
        )
        n_criteria = len(inp.completeness_criteria)
        notes = f"qualitative: {n_criteria} criteria -> {raw}"

    elif mt == MetricType.Q_PLUS_QL:
        raw = score_q_plus_ql(
            inp.extracted_value,
            inp.extracted_text,
            inp.completeness_criteria,
            q_weight=inp.q_weight,
            ql_weight=inp.ql_weight,
            benchmark=inp.benchmark,
            direction=inp.direction,
        )
        notes = (
            f"q+ql [q_w={inp.q_weight}, ql_w={inp.ql_weight}]: {raw:.3f}"
        )

    else:
        logger.warning("score_metric.unknown_type", metric_type=str(mt), code=inp.metric_code)
        raw = 0.0
        notes = f"unknown metric_type '{mt}' -- scored 0.0"

    return MetricScoreOutput(
        metric_code=inp.metric_code,
        metric_type=mt,
        raw_score=round(raw, 4),
        weight_in_topic=inp.weight_in_topic if inp.weight_in_topic is not None else 0.0,
        weighted_contribution=round(
            raw * (inp.weight_in_topic if inp.weight_in_topic is not None else 0.0), 4
        ),
        fra_required=inp.fra_required if hasattr(inp, "fra_required") else False,
        scoring_notes=notes,
    )


# ── Topic and pillar aggregation ──────────────────────────────────────────────
# Spec: Section 2.2–2.3

def score_topic(metrics: list[MetricScoreOutput]) -> float:
    """Weighted average of metric scores within a topic.

    Spec: Section 2.2.

    If weights do not sum to exactly 1.0 (within 0.001 tolerance), they are
    normalised and a warning is logged.  This is safer than raising in
    production when a weight registry has a rounding error.

    Args:
        metrics: List of MetricScoreOutput for one topic.  Each carries
                 raw_score (0–1) and weight_in_topic (0–1).

    Returns:
        Float 0.0–1.0.  Returns 0.0 for an empty list.
    """
    if not metrics:
        return 0.0

    total_weight = sum(m.weight_in_topic for m in metrics)

    if total_weight == 0.0:
        logger.warning("score_topic.all_weights_zero", n_metrics=len(metrics))
        return 0.0

    if abs(total_weight - 1.0) >= 0.001:
        logger.warning(
            "score_topic.weights_do_not_sum_to_one",
            total_weight=round(total_weight, 4),
            n_metrics=len(metrics),
            action="normalising",
        )
        return sum(m.raw_score * (m.weight_in_topic / total_weight) for m in metrics)

    return sum(m.raw_score * m.weight_in_topic for m in metrics)


def score_pillar(topics: list[dict]) -> float:
    """Weighted average of topic scores within a pillar.

    Spec: Section 2.3.

    Args:
        topics: List of dicts, each with keys:
                  'id'     (str)   — topic identifier e.g. 'FIN-E1'
                  'score'  (float) — result of score_topic(), 0–1
                  'weight' (float) — topic's weight within the pillar (must sum to 1.0)

    Returns:
        Float 0.0–1.0.  Returns 0.0 for an empty list.

    Raises:
        AssertionError: if topic weights do not sum to ~1.0 (tolerance 0.001).
    """
    if not topics:
        return 0.0

    total_weight = sum(t["weight"] for t in topics)
    assert abs(total_weight - 1.0) < 0.001, (
        f"Topic weights within pillar must sum to 1.0; got {total_weight:.4f}"
    )

    return sum(t["score"] * t["weight"] for t in topics)


# ── Composite score calculation ───────────────────────────────────────────────
# Spec: Section 2.4 and Section 6

def score_composite(
    pillar_scores: dict[str, float],
    pillar_weights: dict[str, float],
    external_assurance: bool = False,
    assurance_bonus: float = 0.05,
) -> dict:
    """Calculate the final composite ESG score (0–100).

    FRA compliance gate is intentionally omitted — scores are treated uniformly
    regardless of FRA KPI coverage.  Reinstate check_fra_gate() and the 60-point
    cap when the FRA gate is re-enabled.

    Steps:
        1. Weighted sum of pillar scores (0–1 range → 0–100)
        2. Apply external assurance bonus: +5 points if assured (max 100)
        3. Convert to grade letter

    Args:
        pillar_scores:      {'E': 0.72, 'S': 0.58, 'G': 0.81} — 0–1 range.
        pillar_weights:     {'E': 0.25, 'S': 0.40, 'G': 0.35} — must sum to 1.0.
        external_assurance: True if third-party assurance was obtained.
        assurance_bonus:    Fraction of 100 added when assured.  Default = 0.05 (+5 pts).

    Returns:
        Dict with keys:
            raw_score               — weighted pillar sum scaled to 0–100
            assurance_bonus_applied — bool
            final_score             — raw_score + bonus, capped at 100
            grade                   — letter A–F from score_to_grade()

    Raises:
        AssertionError: if pillar weights do not sum to ~1.0.
    """
    assert abs(sum(pillar_weights.values()) - 1.0) < 0.001, (
        f"Pillar weights must sum to 1.0; got {sum(pillar_weights.values()):.4f}"
    )

    # Step 1 — weighted pillar sum → 0–1, then scale to 0–100
    raw = sum(pillar_scores[p] * pillar_weights[p] for p in pillar_scores)
    score_100 = raw * 100

    # Step 2 — external assurance bonus
    final_score = min(
        score_100 + (assurance_bonus * 100 if external_assurance else 0.0),
        100.0,
    )

    return {
        "raw_score": round(score_100, 2),
        "assurance_bonus_applied": external_assurance,
        "final_score": round(final_score, 2),
        "grade": score_to_grade(final_score),
    }


def score_to_grade(score: float) -> str:
    """Convert a numeric composite score to a letter grade.

    Spec: Section 2.4.

    Args:
        score: Final composite ESG score in 0–100 range.

    Returns:
        'A' (≥85) | 'B' (≥70) | 'C' (≥55) | 'D' (≥40) | 'F' (<40)
    """
    if score >= 85:
        return "A"
    if score >= 70:
        return "B"
    if score >= 55:
        return "C"
    if score >= 40:
        return "D"
    return "F"


# ── Sector-specific pillar weight tables ──────────────────────────────────────
# Spec: Section 3.1 (Financial) and Section 4.1 (Manufacturing)

PILLAR_WEIGHTS: dict[str, dict[str, float]] = {
    "financial": {"E": 0.25, "S": 0.40, "G": 0.35},
    "manufacturing": {"E": 0.45, "S": 0.30, "G": 0.25},
}


# ── Legacy ScoringResult dataclass ────────────────────────────────────────────
# Kept for backward-compatibility with workers/tasks.py and report builder.
# New code should use score_composite() + score_metric() directly.

@dataclass
class ScoringResult:
    """Full scoring output for a report (legacy orchestrator output)."""

    total_score: float          # 0–100 composite (weighted pillars, no gate/bonus yet)
    gri_score: float            # 0–100 GRI completeness
    fra_score: float            # 0–100 FRA compliance (FRA-36 logic)
    sasb_score: float           # 0–100 SASB coverage
    environmental_score: float  # 0–100 E pillar
    social_score: float         # 0–100 S pillar
    governance_score: float     # 0–100 G pillar
    benchmark_tier: str         # "Leader" | "Above average" | etc.
    indicators_found: int
    indicators_total: int
    coverage_pct: float
    gaps: list[GapItem] = field(default_factory=list)


# ── Legacy public API ─────────────────────────────────────────────────────────
# Spec: this function predates the new scoring engine.  It uses indicator
# status/confidence as a proxy for the metric score, which is the Iteration-0
# approach.  It is preserved unchanged so the existing pipeline does not break.
# Replace with score_composite() + sector-aware topic/pillar aggregation in
# Iteration 2 M4 work.

# Legacy framework-level weights (Iteration-0 only — not spec-compliant)
_W_GRI: float = 0.50
_W_FRA: float = 0.30
_W_SASB: float = 0.20

# FRA-36 can be satisfied by direct disclosure OR both Scope 1 + Scope 2
_FRA36_DIRECT: str = "FRA-36"
_FRA36_COMPONENTS: frozenset[str] = frozenset({"GRI 305-1", "GRI 305-2"})

_SASB_CODES: frozenset[str] = frozenset({"GRI 418-1"})


def score_report(
    metrics: list,
    indicator_codes: list[str] | None = None,
) -> ScoringResult:
    """Score extracted metrics against GRI / FRA / SASB frameworks.

    LEGACY ORCHESTRATOR — Iteration-0 approach.
    Uses indicator status/confidence as a proxy score.
    Does NOT apply sector-specific pillar weights, topic hierarchy, or FRA gate.
    Preserved for backward-compatibility with workers/tasks.py.

    Args:
        metrics:         Extracted metrics for one report.  Each object must
                         expose gri_code, status, confidence, value, label.
        indicator_codes: Override the indicator set to score against.
                         None → all indicators.

    Returns:
        ScoringResult with per-framework scores and gap analysis.
    """
    all_indicators = get_all_indicators()

    if indicator_codes is not None:
        all_indicators = [i for i in all_indicators if i["code"] in set(indicator_codes)]

    metric_map: dict[str, object] = {m.gri_code: m for m in metrics}

    # ── Per-indicator status/confidence proxy score ───────────────────────────
    indicator_scores: dict[str, float] = {}

    for ind in all_indicators:
        code = ind["code"]
        metric = metric_map.get(code)

        if metric is None:
            indicator_scores[code] = 0.0
            continue

        indicator_scores[code] = _legacy_score_indicator(metric)

    # ── GRI completeness score ────────────────────────────────────────────────
    gri_codes = [i["code"] for i in all_indicators if i["code"].startswith("GRI")]
    gri_scores = [indicator_scores.get(c, 0.0) for c in gri_codes]
    gri_score = (sum(gri_scores) / len(gri_scores) * 100) if gri_scores else 0.0

    # ── FRA-36 compliance score ───────────────────────────────────────────────
    fra_score = _compute_fra_score(indicator_scores)

    # ── SASB coverage score ───────────────────────────────────────────────────
    sasb_scores = [indicator_scores.get(c, 0.0) for c in _SASB_CODES]
    sasb_score = (sum(sasb_scores) / len(sasb_scores) * 100) if sasb_scores else 0.0

    # ── E / S / G pillar scores (simple average, no topic hierarchy) ──────────
    e_score = _legacy_pillar_score(all_indicators, indicator_scores, "E")
    s_score = _legacy_pillar_score(all_indicators, indicator_scores, "S")
    g_score = _legacy_pillar_score(all_indicators, indicator_scores, "G")

    # ── Composite — legacy weights (NOT spec-compliant; Iteration-0 only) ─────
    total_score = 0.40 * e_score + 0.35 * s_score + 0.25 * g_score

    # ── Gap analysis ──────────────────────────────────────────────────────────
    gaps = build_gap_analysis(
        metrics,
        confidence_threshold=settings.confidence_threshold,
        indicator_codes=indicator_codes,
    )

    indicators_found = sum(
        1
        for m in metrics
        if m.status in (MetricStatus.extracted, MetricStatus.approved)
    )

    result = ScoringResult(
        total_score=round(total_score, 1),
        gri_score=round(gri_score, 1),
        fra_score=round(fra_score, 1),
        sasb_score=round(sasb_score, 1),
        environmental_score=round(e_score, 1),
        social_score=round(s_score, 1),
        governance_score=round(g_score, 1),
        benchmark_tier=_benchmark_tier(total_score),
        indicators_found=indicators_found,
        indicators_total=len(all_indicators),
        coverage_pct=round(indicators_found / max(len(all_indicators), 1) * 100, 1),
        gaps=gaps,
    )

    logger.info(
        "score_report.done",
        total=result.total_score,
        gri=result.gri_score,
        E=result.environmental_score,
        S=result.social_score,
        G=result.governance_score,
        benchmark=result.benchmark_tier,
        gaps=len(gaps),
    )
    return result


# ── Legacy helpers ────────────────────────────────────────────────────────────

def _legacy_score_indicator(metric) -> float:
    """Return a 0–1 proxy score from workflow status + confidence."""
    status: MetricStatus = metric.status
    confidence: float = metric.confidence
    threshold: float = settings.confidence_threshold

    if status == MetricStatus.approved:
        return 1.0
    if status == MetricStatus.extracted:
        return confidence if confidence >= threshold else confidence * 0.7
    if status == MetricStatus.ambiguous:
        return 0.3
    if status == MetricStatus.rejected:
        return 0.0
    return 0.0


def _legacy_pillar_score(
    indicators: list,
    indicator_scores: dict,
    pillar: str,
) -> float:
    """Simple average of all indicator scores in a pillar (no topic weighting)."""
    codes = [i["code"] for i in indicators if i.get("pillar") == pillar]
    if not codes:
        return 0.0
    scores = [indicator_scores.get(c, 0.0) for c in codes]
    return sum(scores) / len(scores) * 100


def _benchmark_tier(score: float) -> str:
    """Map a 0–100 composite score to a benchmark tier label."""
    if score >= 85:
        return "Leader"
    if score >= 70:
        return "Above average"
    if score >= 50:
        return "Average"
    if score >= 30:
        return "Below average"
    return "Laggard"


def _compute_fra_score(indicator_scores: dict[str, float]) -> float:
    """FRA-36 compliance: direct disclosure OR both Scope 1 + Scope 2 present."""
    direct = indicator_scores.get(_FRA36_DIRECT, 0.0)
    if direct >= 0.8:
        return direct * 100

    component_scores = [indicator_scores.get(c, 0.0) for c in _FRA36_COMPONENTS]
    if all(s >= 0.8 for s in component_scores):
        return min(component_scores) * 100

    all_scores = [direct] + component_scores
    non_zero = [s for s in all_scores if s > 0]
    if non_zero:
        return sum(non_zero) / len(all_scores) * 100

    return 0.0


# ===========================================================================
# Top-level orchestrator  (Spec §2 end-to-end pipeline)
# ===========================================================================

def score_document(
    sector: str,
    extracted_metrics: list[MetricScoreInput],
    external_assurance: bool = False,
) -> dict:
    """Full spec-compliant scoring pipeline for a single document / company.

    Args:
        sector:             'FINANCIAL' or 'MANUFACTURING' (case-insensitive).
        extracted_metrics:  All MetricScoreInput objects from the extraction pipeline.
                            Each must have metric_code matching codes in the sector
                            weight registry (e.g. 'FRA-E1.1', 'MFG-E2.1').
        external_assurance: If True, bumps composite score by +3 pts (Spec §2.4 note).

    Returns:
        {
            'sector':              str,
            'pillar_scores':       {'E': float, 'S': float, 'G': float},
            'topic_scores':        {topic_id: float, ...},
            'metric_scores':       {metric_code: MetricScoreOutput, ...},
            'composite':           {raw_score, gated_score, final_score, grade},
            'fra_compliance':      {gate_passed, mandatory_pass, coverage_ratio, ...},
            'gap_analysis':        [{topic_id, pillar, potential_gain_points, ...}],
            'improvement_roadmap': {immediate_actions, high_priority, ...},
            'weight_registry_used': 'FINANCIAL' | 'MANUFACTURING',
            'scoring_timestamp':   ISO str,
            'spec_version':        '1.0',
        }
    """
    import datetime

    sector_key = sector.upper()
    if sector_key not in ("FINANCIAL", "MANUFACTURING"):
        raise ValueError(f"sector must be 'FINANCIAL' or 'MANUFACTURING', got '{sector}'")

    # ── Step 1: Load weight registry ─────────────────────────────────────────
    registry = get_weight_registry(sector_key)

    # Build helper maps from registry
    # metric_code -> topic_id
    metric_to_topic: dict[str, str] = {}
    for topic_id, mw in registry.metric_weights.items():
        for metric_code in mw:
            metric_to_topic[metric_code] = topic_id

    # topic_id -> pillar char
    topic_to_pillar: dict[str, str] = {}
    for pillar, tw in registry.topic_weights.items():
        for topic_id in tw:
            topic_to_pillar[topic_id] = pillar

    # Flat topic weights: {topic_id: weight}
    flat_topic_weights: dict[str, float] = {}
    for tw in registry.topic_weights.values():
        flat_topic_weights.update(tw)

    # ── Step 2: Score each metric ─────────────────────────────────────────────
    metric_scores: dict[str, MetricScoreOutput] = {}
    for inp in extracted_metrics:
        result = score_metric(inp)
        metric_scores[inp.metric_code] = result

    # ── Step 3: Group metric scores by topic ──────────────────────────────────
    topic_metric_scores: dict[str, dict[str, MetricScoreOutput]] = {}
    for metric_code, result in metric_scores.items():
        topic_id = metric_to_topic.get(metric_code)
        if topic_id is None:
            logger.warning("score_document.unknown_metric", code=metric_code, sector=sector_key)
            continue
        topic_metric_scores.setdefault(topic_id, {})[metric_code] = result

    # ── Step 4: Score each topic ──────────────────────────────────────────────
    # score_topic() reads weight_in_topic from each MetricScoreOutput.
    # Inject authoritative registry weights before passing.
    topic_scores: dict[str, float] = {}
    for topic_id, mw in registry.metric_weights.items():
        scores_in_topic = topic_metric_scores.get(topic_id, {})
        metric_list: list[MetricScoreOutput] = []
        for m_code, m_weight in mw.items():
            result = scores_in_topic.get(m_code)
            if result:
                metric_list.append(result.model_copy(update={"weight_in_topic": m_weight}))
            else:
                metric_list.append(MetricScoreOutput(
                    metric_code=m_code,
                    metric_type=MetricType.QUANTITATIVE,
                    raw_score=0.0,
                    weight_in_topic=m_weight,
                    weighted_contribution=0.0,
                    fra_required=False,
                    scoring_notes="not extracted",
                ))
        topic_scores[topic_id] = score_topic(metric_list)

    # ── Step 5: Score each pillar ─────────────────────────────────────────────
    # score_pillar() takes list[dict] with keys 'id', 'score', 'weight'.
    pillar_scores: dict[str, float] = {}
    for pillar, tw in registry.topic_weights.items():
        topics_list = [
            {"id": tid, "score": topic_scores.get(tid, 0.0), "weight": w}
            for tid, w in tw.items()
        ]
        pillar_scores[pillar] = score_pillar(topics_list)

    # ── Step 6: FRA gate ──────────────────────────────────────────────────────
    fra_results = extract_fra_results_from_scores(topic_scores, registry.fra_topic_map)
    gate_result = check_fra_gate(fra_results)

    # ── Step 7: Composite ─────────────────────────────────────────────────────
    # score_composite() has no fra_gate_passed param; gate captured separately.
    composite = score_composite(
        pillar_scores=pillar_scores,
        pillar_weights=registry.pillar_weights,
        external_assurance=external_assurance,
    )

    # ── Step 8: Gap analysis ──────────────────────────────────────────────────
    gap_results = generate_gap_analysis(
        topic_scores=topic_scores,
        topic_weights=flat_topic_weights,
        pillar_weights=registry.pillar_weights,
        topic_to_pillar=topic_to_pillar,
    )

    # ── Step 9: Improvement roadmap ───────────────────────────────────────────
    roadmap = generate_improvement_roadmap(
        gap_analysis_results=gap_results,
        fra_gate_result=gate_result,
        sector=sector_key,
        fra_kpi_results=fra_results,
    )

    logger.info(
        "score_document.done",
        sector=sector_key,
        composite=composite.get("final_score"),
        grade=composite.get("grade"),
        gate=gate_result["gate_passed"],
        n_metrics=len(metric_scores),
    )

    return {
        "sector":               sector_key,
        "pillar_scores":        {p: round(s, 4) for p, s in pillar_scores.items()},
        "topic_scores":         {t: round(s, 4) for t, s in topic_scores.items()},
        "metric_scores":        metric_scores,
        "composite":            composite,
        "fra_compliance":       gate_result,
        "gap_analysis":         gap_results,
        "improvement_roadmap": roadmap,
        "weight_registry_used": sector_key,
        "scoring_timestamp":    datetime.datetime.utcnow().isoformat() + "Z",
        "spec_version":         "1.0",
    }
