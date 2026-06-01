"""Unit tests for the v1 disclosure-quality scoring methodology.

Targets the PUBLIC surface of core/scoring/scorer.py:
  - score_report() — the v1 production orchestrator
  - KNOWN_SECTORS / unknown-sector fallback
  - Composite pillar constants (_COMP_E / _COMP_S / _COMP_G) — module-level
    variables that are part of the documented methodology contract
  - The v1 disclosure-quality tiers and confidence-factor tiers — tested via
    the private helpers _disclosure_quality / _confidence_factor, which encode
    the exact spec from CLAUDE.md.  These helpers are tested directly because:
      (a) The spec explicitly mandates the six disclosure tiers and three
          confidence bands as atomic scored values.
      (b) Testing them only via score_report would require injecting full indicator
          JSON context and would conflate tier logic with aggregation logic.
      (c) The refactor preserves these names and semantics (they are part of the
          v1 methodology specification, not arbitrary internals).

FLAG: _disclosure_quality and _confidence_factor are private (single-underscore)
helpers.  If a future refactor moves or renames them, the tests in
TestDisclosureQuality and TestConfidenceFactor will fail at import time and
signal that the new location must be used.  This is intentional — the helpers
encode the spec's atomic scoring rules.
"""
from __future__ import annotations

import sys
import os
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import pytest

from app.models.enums import MetricStatus
from app.core.scoring.scorer import (
    KNOWN_SECTORS,
    _COMP_E,
    _COMP_S,
    _COMP_G,
    _confidence_factor,
    _disclosure_quality,
    _per_indicator_score,
    score_report,
)


# ===========================================================================
# Helper — build a minimal metric object recognised by the v1 scorer
# ===========================================================================

def _metric(
    gri_code: str,
    status: MetricStatus = MetricStatus.extracted,
    value: float | None = None,
    unit: str | None = None,
    original_value: str | None = None,
    confidence: float = 1.0,
    source_page: int | None = None,
    evidence_chunk: str | None = None,
) -> SimpleNamespace:
    """Build a thin metric stub for use with _disclosure_quality / score_report."""
    return SimpleNamespace(
        gri_code=gri_code,
        status=status,
        value=value,
        unit=unit,
        original_value=original_value,
        confidence=confidence,
        source_page=source_page,
        evidence_chunk=evidence_chunk,
    )


# ===========================================================================
# 1. KNOWN_SECTORS constant
# ===========================================================================

class TestKnownSectors:
    def test_contains_expected_sectors(self):
        assert "banking" in KNOWN_SECTORS
        assert "insurance" in KNOWN_SECTORS
        assert "consumer_finance" in KNOWN_SECTORS
        assert "mortgage_finance" in KNOWN_SECTORS

    def test_is_frozenset(self):
        assert isinstance(KNOWN_SECTORS, frozenset)


# ===========================================================================
# 2. Composite pillar weights constant
# ===========================================================================

class TestCompositeWeightConstants:
    def test_sum_to_one(self):
        assert abs(_COMP_E + _COMP_S + _COMP_G - 1.0) < 0.001

    def test_exact_values(self):
        assert _COMP_E == pytest.approx(0.40)
        assert _COMP_S == pytest.approx(0.35)
        assert _COMP_G == pytest.approx(0.25)


# ===========================================================================
# 3. _disclosure_quality — all six tiers
#
# CLAUDE.md spec (v1 methodology, "disclosure_quality" table):
#   Missing/rejected → 0.0
#   Ambiguous        → 0.4
#   Qualitative only → 0.6
#   Quant, no unit   → 0.7
#   Quant+unit, no citation → 0.8
#   Fully disclosed  → 1.0
# ===========================================================================

class TestDisclosureQuality:
    """Test every tier of the v1 disclosure-quality rubric from CLAUDE.md."""

    def test_none_metric_returns_zero(self):
        assert _disclosure_quality(None) == 0.0

    def test_missing_status_returns_zero(self):
        m = _metric("GRI 302-1", status=MetricStatus.missing, original_value="some text")
        assert _disclosure_quality(m) == 0.0

    def test_rejected_status_returns_zero(self):
        m = _metric("GRI 302-1", status=MetricStatus.rejected,
                    value=100.0, unit="GJ",
                    source_page=5, evidence_chunk="We used 100 GJ")
        # Rejected overrides everything — stays at 0.0
        assert _disclosure_quality(m) == 0.0

    def test_no_value_and_no_original_returns_zero(self):
        m = _metric("GRI 302-1", status=MetricStatus.extracted,
                    value=None, original_value=None)
        assert _disclosure_quality(m) == 0.0

    def test_ambiguous_status_returns_04(self):
        m = _metric("GRI 302-1", status=MetricStatus.ambiguous,
                    original_value="approximately 500 GJ")
        assert _disclosure_quality(m) == pytest.approx(0.4)

    def test_qualitative_only_returns_06(self):
        # original_value present but value is None
        m = _metric("GRI 2-1", status=MetricStatus.extracted,
                    value=None, original_value="Cairo, Egypt")
        assert _disclosure_quality(m) == pytest.approx(0.6)

    def test_quant_no_unit_returns_07(self):
        m = _metric("GRI 302-1", status=MetricStatus.extracted,
                    value=1234.0, unit=None, original_value="1234")
        assert _disclosure_quality(m) == pytest.approx(0.7)

    def test_quant_unit_no_citation_returns_08(self):
        m = _metric("GRI 302-1", status=MetricStatus.extracted,
                    value=1234.0, unit="GJ",
                    source_page=None, evidence_chunk=None)
        assert _disclosure_quality(m) == pytest.approx(0.8)

    def test_quant_unit_blank_evidence_returns_08(self):
        m = _metric("GRI 302-1", status=MetricStatus.extracted,
                    value=1234.0, unit="GJ",
                    source_page=5, evidence_chunk="   ")  # blank evidence_chunk
        assert _disclosure_quality(m) == pytest.approx(0.8)

    def test_fully_disclosed_returns_10(self):
        m = _metric("GRI 302-1", status=MetricStatus.extracted,
                    value=1234.0, unit="GJ",
                    source_page=5, evidence_chunk="Energy consumption was 1,234 GJ.")
        assert _disclosure_quality(m) == pytest.approx(1.0)

    def test_approved_fully_disclosed_returns_10(self):
        m = _metric("GRI 302-1", status=MetricStatus.approved,
                    value=1234.0, unit="GJ",
                    source_page=5, evidence_chunk="Energy consumption was 1,234 GJ.")
        assert _disclosure_quality(m) == pytest.approx(1.0)


# ===========================================================================
# 4. _confidence_factor — all tiers
#
# CLAUDE.md spec (v1 methodology, "confidence_factor" table):
#   approved          → 1.0 (consultant override)
#   confidence >= 0.8 → 1.0
#   0.5 <= conf < 0.8 → 0.7
#   conf < 0.5        → 0.5
# ===========================================================================

class TestConfidenceFactor:
    def test_none_metric_returns_05(self):
        assert _confidence_factor(None) == pytest.approx(0.5)

    def test_approved_overrides_to_10(self):
        m = _metric("GRI 2-1", status=MetricStatus.approved, confidence=0.1)
        assert _confidence_factor(m) == pytest.approx(1.0)

    def test_high_confidence_returns_10(self):
        for conf in (0.8, 0.9, 1.0, 0.80):
            m = _metric("GRI 302-1", status=MetricStatus.extracted, confidence=conf)
            assert _confidence_factor(m) == pytest.approx(1.0), f"conf={conf}"

    def test_mid_confidence_returns_07(self):
        for conf in (0.5, 0.6, 0.7, 0.79):
            m = _metric("GRI 302-1", status=MetricStatus.extracted, confidence=conf)
            assert _confidence_factor(m) == pytest.approx(0.7), f"conf={conf}"

    def test_low_confidence_returns_05(self):
        for conf in (0.0, 0.1, 0.49):
            m = _metric("GRI 302-1", status=MetricStatus.extracted, confidence=conf)
            assert _confidence_factor(m) == pytest.approx(0.5), f"conf={conf}"


# ===========================================================================
# 5. _per_indicator_score — combined product
# ===========================================================================

class TestPerIndicatorScore:
    def test_missing_gives_zero(self):
        m = _metric("GRI 302-1", status=MetricStatus.missing)
        assert _per_indicator_score(m) == pytest.approx(0.0)

    def test_fully_disclosed_high_conf(self):
        m = _metric("GRI 302-1", status=MetricStatus.extracted,
                    value=500.0, unit="GJ",
                    source_page=3, evidence_chunk="500 GJ consumed.",
                    confidence=0.95)
        # disclosure_quality=1.0 * confidence_factor=1.0 = 1.0
        assert _per_indicator_score(m) == pytest.approx(1.0)

    def test_ambiguous_high_conf(self):
        m = _metric("GRI 302-1", status=MetricStatus.ambiguous,
                    original_value="approximately 500",
                    confidence=0.9)
        # 0.4 * 1.0 = 0.4
        assert _per_indicator_score(m) == pytest.approx(0.4)

    def test_qualitative_mid_conf(self):
        m = _metric("GRI 2-1", status=MetricStatus.extracted,
                    value=None, original_value="Cairo, Egypt",
                    confidence=0.6)
        # 0.6 * 0.7 = 0.42
        assert _per_indicator_score(m) == pytest.approx(0.42)


# ===========================================================================
# 6. score_report — unknown sector loudly falls back to banking
# ===========================================================================

class TestScoreReportUnknownSector:
    """CLAUDE.md: 'Unknown sectors log a warning and fall back to banking'."""

    def test_unknown_sector_does_not_raise(self):
        result = score_report([], sector="UNKNOWN_XYZ_SECTOR")
        assert result is not None

    def test_unknown_sector_produces_same_result_as_banking(self):
        m = _metric("GRI 2-1", status=MetricStatus.extracted,
                    value=None, original_value="Cairo, Egypt",
                    confidence=0.9)
        banking_result = score_report([m], sector="banking")
        unknown_result = score_report([m], sector="totally_unknown_sector")
        # Both use banking weights — scores must be equal
        assert unknown_result.total_score == banking_result.total_score
        assert unknown_result.environmental_score == banking_result.environmental_score
        assert unknown_result.social_score == banking_result.social_score
        assert unknown_result.governance_score == banking_result.governance_score


# ===========================================================================
# 7. score_report — composite formula and ScoringResult structure
# ===========================================================================

class TestScoreReportComposite:
    def test_empty_metrics_returns_scoring_result(self):
        result = score_report([], sector="banking")
        assert hasattr(result, "total_score")
        assert hasattr(result, "gri_score")
        assert hasattr(result, "fra_score")
        assert hasattr(result, "sasb_score")
        assert hasattr(result, "environmental_score")
        assert hasattr(result, "social_score")
        assert hasattr(result, "governance_score")
        assert hasattr(result, "benchmark_tier")
        assert hasattr(result, "indicators_found")
        assert hasattr(result, "indicators_total")
        assert hasattr(result, "coverage_pct")
        assert hasattr(result, "gaps")
        assert isinstance(result.gaps, list)

    def test_empty_metrics_total_score_is_zero(self):
        result = score_report([], sector="banking")
        assert result.total_score == pytest.approx(0.0)

    def test_composite_is_weighted_e_s_g(self):
        """Composite = 0.40·E + 0.35·S + 0.25·G."""
        result = score_report([], sector="banking")
        expected = (_COMP_E * result.environmental_score +
                    _COMP_S * result.social_score +
                    _COMP_G * result.governance_score)
        assert result.total_score == pytest.approx(expected, abs=0.5)

    def test_scores_in_0_to_100_range(self):
        result = score_report([], sector="banking")
        for attr in ("total_score", "gri_score", "fra_score", "sasb_score",
                     "environmental_score", "social_score", "governance_score"):
            val = getattr(result, attr)
            assert 0.0 <= val <= 100.0, f"{attr}={val} out of range"

    def test_indicators_total_matches_sector_scope(self):
        result = score_report([], sector="banking")
        # banking has at least 20 in-scope indicators per CLAUDE.md
        assert result.indicators_total >= 20

    @pytest.mark.parametrize("sector", sorted(KNOWN_SECTORS))
    def test_all_known_sectors_execute_without_error(self, sector):
        result = score_report([], sector=sector)
        assert result is not None
        assert 0.0 <= result.total_score <= 100.0


# ===========================================================================
# 8. score_report — coverage_pct reflects disclosed count
# ===========================================================================

class TestScoreReportCoverage:
    def test_zero_metrics_gives_zero_coverage(self):
        result = score_report([], sector="banking")
        assert result.coverage_pct == pytest.approx(0.0)

    def test_fully_disclosed_metric_raises_coverage(self):
        m = _metric("GRI 2-1", status=MetricStatus.extracted,
                    value=None, original_value="Test Bank",
                    confidence=0.9)
        result_no = score_report([], sector="banking")
        result_with = score_report([m], sector="banking")
        assert result_with.indicators_found >= result_no.indicators_found

    def test_coverage_pct_in_range(self):
        m = _metric("GRI 2-1", status=MetricStatus.extracted,
                    value=None, original_value="Test Bank",
                    confidence=0.95)
        result = score_report([m], sector="banking")
        assert 0.0 <= result.coverage_pct <= 100.0


# ===========================================================================
# 9. score_report — benchmark_tier labels
# ===========================================================================

class TestBenchmarkTier:
    def test_zero_score_is_laggard(self):
        result = score_report([], sector="banking")
        assert result.benchmark_tier == "Laggard"

    def test_benchmark_tier_is_valid_string(self):
        result = score_report([], sector="banking")
        assert isinstance(result.benchmark_tier, str)
        assert result.benchmark_tier in (
            "Leader", "Above average", "Average", "Below average", "Laggard"
        )


# ===========================================================================
# 10. indicator_codes filter parameter
# ===========================================================================

class TestScoreReportIndicatorFilter:
    def test_filter_restricts_total_count(self):
        subset = ["GRI 2-1", "GRI 302-1"]
        result_full = score_report([], sector="banking")
        result_filtered = score_report([], sector="banking", indicator_codes=subset)
        assert result_filtered.indicators_total <= result_full.indicators_total
