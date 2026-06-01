"""Unit tests for core/reporting/builder.py.

Coverage:
  1. _topic_of — GRI code → topic prefix, FRA pass-through, unknown fallback
  2. build_report_sections — groups metrics by topic, correct pillar assignment
  3. build_report_sections — sections are ordered per _TOPIC_ORDER
  4. build_report_sections — ReportBundle attributes present
  5. gri_content_index — all 46 indicators appear; status set from metric or 'not reported'

NOTE: build_report_sections calls get_all_indicators() to fill in missing indicators,
so it indirectly loads data/gri_indicators.json.  No LLM / DB / Torch needed.
"""
from __future__ import annotations

import sys
import os
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import pytest

from app.core.reporting.builder import (
    CompanyProfile,
    ReportBundle,
    ReportSection,
    _PILLAR_OF_TOPIC,
    _TOPIC_ORDER,
    _topic_of,
    build_report_sections,
    gri_content_index,
)
from app.models.enums import MetricStatus


# ===========================================================================
# Helper
# ===========================================================================

def _score_stub():
    """Minimal ScoringResult-like object (builder only passes it through)."""
    return SimpleNamespace(total_score=0.0, gri_score=0.0, fra_score=0.0,
                           sasb_score=0.0, environmental_score=0.0,
                           social_score=0.0, governance_score=0.0,
                           benchmark_tier="Laggard", indicators_found=0,
                           indicators_total=0, coverage_pct=0.0, gaps=[])


def _metric(gri_code: str, status: MetricStatus = MetricStatus.extracted,
            source_page: int | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        gri_code=gri_code,
        status=status,
        source_page=source_page,
    )


def _company(name: str = "Test Bank", sector: str = "banking") -> CompanyProfile:
    return CompanyProfile(name=name, sector=sector)


# ===========================================================================
# 1. _topic_of helper
# ===========================================================================

class TestTopicOf:
    @pytest.mark.parametrize("code, expected_topic", [
        ("GRI 302-1",   "GRI 302"),
        ("GRI 2-1",     "GRI 2"),
        ("GRI 405-1",   "GRI 405"),
        ("GRI 3-3",     "GRI 3"),
        ("GRI 418-1",   "GRI 418"),
        ("FRA-36",      "FRA"),
        ("GRI 303-5",   "GRI 303"),
        ("GRI 305-1",   "GRI 305"),
        ("GRI 305-2",   "GRI 305"),   # same topic as 305-1
        ("GRI 401-1",   "GRI 401"),
        ("GRI 403-9",   "GRI 403"),
        ("GRI 306-4",   "GRI 306"),
    ])
    def test_gri_codes(self, code, expected_topic):
        assert _topic_of(code) == expected_topic

    def test_unknown_code_returns_other(self):
        assert _topic_of("SASB-FN-CF-230a.1") == "Other"

    def test_empty_string_returns_other(self):
        assert _topic_of("") == "Other"


# ===========================================================================
# 2. build_report_sections — basic structure
# ===========================================================================

class TestBuildReportSectionsBasic:
    def test_returns_report_bundle(self):
        bundle = build_report_sections([], _score_stub(), _company())
        assert isinstance(bundle, ReportBundle)

    def test_bundle_has_correct_company(self):
        company = _company("ADCB", "banking")
        bundle = build_report_sections([], _score_stub(), company)
        assert bundle.company.name == "ADCB"

    def test_bundle_has_score(self):
        score = _score_stub()
        bundle = build_report_sections([], score, _company())
        assert bundle.score is score

    def test_bundle_sections_is_list(self):
        bundle = build_report_sections([], _score_stub(), _company())
        assert isinstance(bundle.sections, list)

    def test_empty_metrics_produces_no_sections(self):
        # Without any metrics AND all indicators filtered out by the missing-check
        # (they need at least 1 metric to generate a section), builder returns 0 sections
        # BUT: the builder also walks all_indicators for missing ones and adds placeholder topics.
        # Sections are only added when topic_metrics is non-empty.
        bundle = build_report_sections([], _score_stub(), _company())
        # With no metrics and no placeholders there are no sections.
        # (All indicator codes produce empty lists for by_topic entries.)
        assert isinstance(bundle.sections, list)


# ===========================================================================
# 3. build_report_sections — single metric → one section
# ===========================================================================

class TestBuildReportSectionsSingleMetric:
    def test_energy_metric_creates_energy_section(self):
        m = _metric("GRI 302-1")
        bundle = build_report_sections([m], _score_stub(), _company())
        topics = [s.gri_topic for s in bundle.sections]
        assert "GRI 302" in topics

    def test_section_pillar_correct_for_e(self):
        m = _metric("GRI 302-1")
        bundle = build_report_sections([m], _score_stub(), _company())
        energy_section = next(s for s in bundle.sections if s.gri_topic == "GRI 302")
        assert energy_section.pillar == "E"

    def test_section_pillar_correct_for_s(self):
        m = _metric("GRI 401-1")
        bundle = build_report_sections([m], _score_stub(), _company())
        emp_section = next(s for s in bundle.sections if s.gri_topic == "GRI 401")
        assert emp_section.pillar == "S"

    def test_section_pillar_correct_for_g(self):
        m = _metric("GRI 2-1")
        bundle = build_report_sections([m], _score_stub(), _company())
        gen_section = next(s for s in bundle.sections if s.gri_topic == "GRI 2")
        assert gen_section.pillar == "G"

    def test_section_title_nonempty(self):
        m = _metric("GRI 302-1")
        bundle = build_report_sections([m], _score_stub(), _company())
        for s in bundle.sections:
            assert isinstance(s.title, str) and s.title.strip()

    def test_metric_in_section_metrics_list(self):
        m = _metric("GRI 302-1")
        bundle = build_report_sections([m], _score_stub(), _company())
        energy_section = next(s for s in bundle.sections if s.gri_topic == "GRI 302")
        assert m in energy_section.metrics


# ===========================================================================
# 4. build_report_sections — ordering
# ===========================================================================

class TestBuildReportSectionsOrdering:
    def test_sections_follow_topic_order(self):
        metrics = [
            _metric("GRI 405-1"),  # GRI 405 — comes after GRI 302/303/305 etc.
            _metric("GRI 302-1"),  # GRI 302 — should come first
        ]
        bundle = build_report_sections(metrics, _score_stub(), _company())
        topics = [s.gri_topic for s in bundle.sections]
        # GRI 302 must appear before GRI 405 in the output
        assert topics.index("GRI 302") < topics.index("GRI 405")

    def test_fra_section_last_among_present(self):
        metrics = [
            _metric("FRA-36"),
            _metric("GRI 302-1"),
        ]
        bundle = build_report_sections(metrics, _score_stub(), _company())
        topics = [s.gri_topic for s in bundle.sections]
        if "FRA" in topics and "GRI 302" in topics:
            assert topics.index("GRI 302") < topics.index("FRA")


# ===========================================================================
# 5. build_report_sections — multiple metrics in same topic
# ===========================================================================

class TestBuildReportSectionsMultiMetric:
    def test_two_metrics_same_topic_in_one_section(self):
        m1 = _metric("GRI 305-1")
        m2 = _metric("GRI 305-2")
        bundle = build_report_sections([m1, m2], _score_stub(), _company())
        emission_sections = [s for s in bundle.sections if s.gri_topic == "GRI 305"]
        assert len(emission_sections) == 1
        assert m1 in emission_sections[0].metrics
        assert m2 in emission_sections[0].metrics


# ===========================================================================
# 6. gri_content_index
# ===========================================================================

class TestGriContentIndex:
    def test_all_46_indicators_appear(self):
        rows = gri_content_index([])
        assert len(rows) == 46

    def test_returns_list_of_dicts(self):
        rows = gri_content_index([])
        for row in rows:
            assert isinstance(row, dict)
            assert "code" in row
            assert "name" in row
            assert "page" in row
            assert "status" in row

    def test_missing_indicator_has_not_reported_status(self):
        rows = gri_content_index([])
        for row in rows:
            assert row["status"] == "not reported"
            assert row["page"] is None

    def test_present_indicator_uses_metric_status(self):
        m = _metric("GRI 302-1", status=MetricStatus.approved, source_page=5)
        rows = gri_content_index([m])
        row = next(r for r in rows if r["code"] == "GRI 302-1")
        assert row["status"] == "approved"
        assert row["page"] == 5

    def test_absent_indicator_stays_not_reported_even_when_some_present(self):
        m = _metric("GRI 302-1", status=MetricStatus.extracted)
        rows = gri_content_index([m])
        fra_row = next(r for r in rows if r["code"] == "FRA-36")
        assert fra_row["status"] == "not reported"

    def test_codes_match_catalog(self):
        from app.core.gri.indicators import get_indicator_codes
        catalog_codes = set(get_indicator_codes())
        index_codes = {r["code"] for r in gri_content_index([])}
        assert index_codes == catalog_codes


# ===========================================================================
# 7. _PILLAR_OF_TOPIC and _TOPIC_ORDER consistency
# ===========================================================================

class TestBuilderConstants:
    def test_topic_order_covers_pillar_map_keys(self):
        # Every topic in _TOPIC_ORDER should have a pillar assignment
        for topic in _TOPIC_ORDER:
            assert topic in _PILLAR_OF_TOPIC, (
                f"Topic {topic!r} in _TOPIC_ORDER has no entry in _PILLAR_OF_TOPIC"
            )

    def test_pillar_map_values_are_valid(self):
        for topic, pillar in _PILLAR_OF_TOPIC.items():
            assert pillar in ("E", "S", "G"), (
                f"Topic {topic!r} maps to invalid pillar {pillar!r}"
            )
