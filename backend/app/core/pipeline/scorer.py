"""ESG scoring — GRI completeness + FRA compliance + gap analysis.

Pure Python functions with no LLM or database calls.  Takes a list of
extracted metrics and returns scores plus an actionable gap list.

Usage:
    from app.core.pipeline.scorer import score_report

    result = score_report(metrics)
    print(f"GRI: {result.gri_score}/100, Gaps: {len(result.gaps)}")
"""

from __future__ import annotations

from dataclasses import dataclass, field

import structlog

from app.config import settings
from app.core.gri.indicators import get_all_indicators
from app.models.enums import MetricStatus

logger = structlog.get_logger(__name__)

# ── Weights for total score (banking sector Phase 1) ─────────────────────
_W_GRI = 0.50
_W_FRA = 0.30
_W_SASB = 0.20

# ── Indicator sets ───────────────────────────────────────────────────────
# FRA-36 can be satisfied by FRA-36 itself OR both Scope 1 + Scope 2
_FRA36_DIRECT = "FRA-36"
_FRA36_COMPONENTS = {"GRI 305-1", "GRI 305-2"}

# SASB-mapped indicators in Phase 1
_SASB_CODES = {"GRI 418-1"}  # FN-CB-230a.1


# ── Data classes ─────────────────────────────────────────────────────────
@dataclass
class GapItem:
    """One missing or incomplete indicator with a remediation hint."""

    code: str
    name: str
    status: str          # "missing" | "ambiguous" | "low_confidence" | "rejected"
    confidence: float
    recommendation: str


@dataclass
class ScoringResult:
    """Full scoring output for a report."""

    total_score: float          # 0–100 weighted composite
    gri_score: float            # 0–100 GRI completeness
    fra_score: float            # 0–100 FRA compliance
    sasb_score: float           # 0–100 SASB coverage
    indicators_found: int       # count with extracted | approved
    indicators_total: int
    coverage_pct: float         # indicators_found / indicators_total × 100
    gaps: list[GapItem] = field(default_factory=list)


# ── Public API ───────────────────────────────────────────────────────────
def score_report(
    metrics: list,  # ExtractedMetricSchema | ExtractedMetricCreate — duck-typed
    indicator_codes: list[str] | None = None,
) -> ScoringResult:
    """Score extracted metrics against GRI / FRA / SASB frameworks.

    Args:
        metrics: Extracted metrics for one report.  Each object must expose
            ``gri_code``, ``status``, ``confidence``, ``value``, ``label``.
        indicator_codes: Override the indicator set to score against.
            ``None`` → all 13 Phase 1 indicators.

    Returns:
        ``ScoringResult`` with per-framework scores and gap analysis.
    """
    all_indicators = get_all_indicators()

    if indicator_codes is not None:
        all_indicators = [i for i in all_indicators if i["code"] in set(indicator_codes)]

    # Build a lookup: gri_code → metric
    metric_map: dict[str, object] = {}
    for m in metrics:
        metric_map[m.gri_code] = m

    # ── Per-indicator scoring ────────────────────────────────────────
    indicator_scores: dict[str, float] = {}
    gaps: list[GapItem] = []

    for ind in all_indicators:
        code = ind["code"]
        metric = metric_map.get(code)

        if metric is None:
            indicator_scores[code] = 0.0
            gaps.append(GapItem(
                code=code,
                name=ind["name"],
                status="missing",
                confidence=0.0,
                recommendation=f"No data found. Check: {ind['primary_source']}.",
            ))
            continue

        score, gap = _score_indicator(ind, metric)
        indicator_scores[code] = score
        if gap:
            gaps.append(gap)

    # ── GRI score (all indicators equally weighted) ──────────────────
    gri_codes = [i["code"] for i in all_indicators if i["code"].startswith("GRI")]
    gri_scores = [indicator_scores.get(c, 0.0) for c in gri_codes]
    gri_score = (sum(gri_scores) / len(gri_scores) * 100) if gri_scores else 0.0

    # ── FRA score ────────────────────────────────────────────────────
    fra_score = _compute_fra_score(indicator_scores, metric_map)

    # ── SASB score ───────────────────────────────────────────────────
    sasb_scores = [indicator_scores.get(c, 0.0) for c in _SASB_CODES]
    sasb_score = (sum(sasb_scores) / len(sasb_scores) * 100) if sasb_scores else 0.0

    # ── Total composite ─────────────────────────────────────────────
    total_score = _W_GRI * gri_score + _W_FRA * fra_score + _W_SASB * sasb_score

    indicators_found = sum(
        1 for m in metrics
        if m.status in (MetricStatus.extracted, MetricStatus.approved)
    )

    result = ScoringResult(
        total_score=round(total_score, 1),
        gri_score=round(gri_score, 1),
        fra_score=round(fra_score, 1),
        sasb_score=round(sasb_score, 1),
        indicators_found=indicators_found,
        indicators_total=len(all_indicators),
        coverage_pct=round(indicators_found / max(len(all_indicators), 1) * 100, 1),
        gaps=gaps,
    )

    logger.info(
        "scorer.done",
        total=result.total_score,
        gri=result.gri_score,
        fra=result.fra_score,
        sasb=result.sasb_score,
        gaps=len(gaps),
    )
    return result


# ── Per-indicator scoring logic ──────────────────────────────────────────
def _score_indicator(indicator: dict, metric) -> tuple[float, GapItem | None]:
    """Return a 0.0–1.0 score and an optional gap entry for one indicator."""
    status: MetricStatus = metric.status
    confidence: float = metric.confidence
    threshold: float = settings.confidence_threshold

    if status == MetricStatus.approved:
        return 1.0, None

    if status == MetricStatus.extracted:
        if confidence >= threshold:
            return confidence, None
        # Extracted but below threshold
        score = confidence * 0.7
        return score, GapItem(
            code=indicator["code"],
            name=indicator["name"],
            status="low_confidence",
            confidence=confidence,
            recommendation=(
                f"Confidence {confidence:.0%} is below {threshold:.0%} threshold. "
                f"Review the evidence and approve or re-extract from: {indicator['primary_source']}."
            ),
        )

    if status == MetricStatus.ambiguous:
        return 0.3, GapItem(
            code=indicator["code"],
            name=indicator["name"],
            status="ambiguous",
            confidence=confidence,
            recommendation=(
                f"Value is ambiguous (confidence {confidence:.0%}). "
                f"Verify against: {indicator['primary_source']}."
            ),
        )

    if status == MetricStatus.rejected:
        return 0.0, GapItem(
            code=indicator["code"],
            name=indicator["name"],
            status="rejected",
            confidence=confidence,
            recommendation=(
                f"Value was rejected by reviewer. "
                f"Re-extract from: {indicator['primary_source']}."
            ),
        )

    # missing or any other status
    return 0.0, GapItem(
        code=indicator["code"],
        name=indicator["name"],
        status="missing",
        confidence=0.0,
        recommendation=f"No data found. Check: {indicator['primary_source']}.",
    )


# ── FRA-36 specific logic ───────────────────────────────────────────────
def _compute_fra_score(
    indicator_scores: dict[str, float],
    metric_map: dict[str, object],
) -> float:
    """FRA-36 compliance: direct disclosure OR both Scope 1 + Scope 2.

    Returns 0–100.
    """
    # Path 1: FRA-36 reported directly
    direct = indicator_scores.get(_FRA36_DIRECT, 0.0)
    if direct >= 0.8:
        return direct * 100

    # Path 2: Both component scopes are present
    component_scores = [indicator_scores.get(c, 0.0) for c in _FRA36_COMPONENTS]
    if all(s >= 0.8 for s in component_scores):
        return min(component_scores) * 100

    # Partial credit: average of whatever is available
    all_scores = [direct] + component_scores
    non_zero = [s for s in all_scores if s > 0]
    if non_zero:
        return sum(non_zero) / len([direct] + list(_FRA36_COMPONENTS)) * 100

    return 0.0
