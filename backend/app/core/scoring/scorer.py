"""ESG scoring orchestrator — GRI completeness + FRA compliance + gap analysis.

Pure Python functions with no LLM or database calls.  Takes a list of
extracted metrics and returns scores plus an actionable gap list.

Usage:
    from app.core.scoring.scorer import score_report

    result = score_report(metrics)
    print(f"GRI: {result.gri_score}/100, Gaps: {len(result.gaps)}")
"""

from __future__ import annotations

from dataclasses import dataclass, field

import structlog

from app.config import settings
from app.core.gri.indicators import get_all_indicators
from app.core.scoring.gap_analysis import GapItem, build_gap_analysis
from app.models.enums import MetricStatus

logger = structlog.get_logger(__name__)

# ── Weights for total score ───────────────────────────────────────────────
_W_GRI = 0.50
_W_FRA = 0.30
_W_SASB = 0.20

# ── FRA-36 can be satisfied by direct disclosure OR both Scope 1 + Scope 2
_FRA36_DIRECT = "FRA-36"
_FRA36_COMPONENTS = {"GRI 305-1", "GRI 305-2"}

_SASB_CODES = {"GRI 418-1"}  # FN-CB-230a.1


# ── Data classes ─────────────────────────────────────────────────────────
@dataclass
class ScoringResult:
    """Full scoring output for a report."""

    total_score: float          # 0–100 weighted composite
    gri_score: float            # 0–100 GRI completeness
    fra_score: float            # 0–100 FRA compliance
    sasb_score: float           # 0–100 SASB coverage
    environmental_score: float  # 0–100 E pillar
    social_score: float         # 0–100 S pillar
    governance_score: float     # 0–100 G pillar
    benchmark_tier: str         # "Leader" | "Above average" | etc.
    indicators_found: int
    indicators_total: int
    coverage_pct: float
    gaps: list[GapItem] = field(default_factory=list)


# ── Public API ───────────────────────────────────────────────────────────
def score_report(
    metrics: list,
    indicator_codes: list[str] | None = None,
) -> ScoringResult:
    """Score extracted metrics against GRI / FRA / SASB frameworks.

    Args:
        metrics: Extracted metrics for one report.  Each object must expose
            ``gri_code``, ``status``, ``confidence``, ``value``, ``label``.
        indicator_codes: Override the indicator set to score against.
            ``None`` → all indicators.

    Returns:
        ``ScoringResult`` with per-framework scores and gap analysis.
    """
    all_indicators = get_all_indicators()

    if indicator_codes is not None:
        all_indicators = [i for i in all_indicators if i["code"] in set(indicator_codes)]

    metric_map: dict[str, object] = {m.gri_code: m for m in metrics}

    # ── Per-indicator scoring ────────────────────────────────────────
    indicator_scores: dict[str, float] = {}

    for ind in all_indicators:
        code = ind["code"]
        metric = metric_map.get(code)

        if metric is None:
            indicator_scores[code] = 0.0
            continue

        score, _ = _score_indicator(ind, metric)
        indicator_scores[code] = score

    # ── GRI score ────────────────────────────────────────────────────
    gri_codes = [i["code"] for i in all_indicators if i["code"].startswith("GRI")]
    gri_scores = [indicator_scores.get(c, 0.0) for c in gri_codes]
    gri_score = (sum(gri_scores) / len(gri_scores) * 100) if gri_scores else 0.0

    # ── FRA score ────────────────────────────────────────────────────
    fra_score = _compute_fra_score(indicator_scores, metric_map)

    # ── SASB score ───────────────────────────────────────────────────
    sasb_scores = [indicator_scores.get(c, 0.0) for c in _SASB_CODES]
    sasb_score = (sum(sasb_scores) / len(sasb_scores) * 100) if sasb_scores else 0.0

    # ── E / S / G pillar scores ──────────────────────────────────────
    e_score = _pillar_score(all_indicators, indicator_scores, "E")
    s_score = _pillar_score(all_indicators, indicator_scores, "S")
    g_score = _pillar_score(all_indicators, indicator_scores, "G")

    # ── Total composite (CLAUDE.md weights: E=40%, S=35%, G=25%) ────
    total_score = 0.40 * e_score + 0.35 * s_score + 0.25 * g_score

    # ── Gap analysis ─────────────────────────────────────────────────
    gaps = build_gap_analysis(
        metrics,
        confidence_threshold=settings.confidence_threshold,
        indicator_codes=indicator_codes,
    )

    indicators_found = sum(
        1 for m in metrics
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
        "scorer.done",
        total=result.total_score,
        gri=result.gri_score,
        E=result.environmental_score,
        S=result.social_score,
        G=result.governance_score,
        benchmark=result.benchmark_tier,
        gaps=len(gaps),
    )
    return result


# ── Per-indicator scoring logic ──────────────────────────────────────────
def _score_indicator(indicator: dict, metric) -> tuple[float, GapItem | None]:
    """Return a 0.0–1.0 score for one indicator."""
    status: MetricStatus = metric.status
    confidence: float = metric.confidence
    threshold: float = settings.confidence_threshold

    if status == MetricStatus.approved:
        return 1.0, None

    if status == MetricStatus.extracted:
        if confidence >= threshold:
            return confidence, None
        return confidence * 0.7, None

    if status == MetricStatus.ambiguous:
        return 0.3, None

    if status == MetricStatus.rejected:
        return 0.0, None

    return 0.0, None


def _pillar_score(indicators: list, indicator_scores: dict, pillar: str) -> float:
    """Average score across all indicators in a given ESG pillar."""
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


# ── FRA-36 specific logic ─────────────────────────────────────────────────
def _compute_fra_score(
    indicator_scores: dict[str, float],
    metric_map: dict[str, object],
) -> float:
    """FRA-36 compliance: direct disclosure OR both Scope 1 + Scope 2."""
    direct = indicator_scores.get(_FRA36_DIRECT, 0.0)
    if direct >= 0.8:
        return direct * 100

    component_scores = [indicator_scores.get(c, 0.0) for c in _FRA36_COMPONENTS]
    if all(s >= 0.8 for s in component_scores):
        return min(component_scores) * 100

    all_scores = [direct] + component_scores
    non_zero = [s for s in all_scores if s > 0]
    if non_zero:
        return sum(non_zero) / len([direct] + list(_FRA36_COMPONENTS)) * 100

    return 0.0
