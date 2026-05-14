"""Pytest tests for the ESG scoring module.

Coverage:
    1. Metric-level scoring functions (parametrized)
    2. Weight registry validation (FINANCIAL + MANUFACTURING)
    3. FRA compliance gate logic
    4. Composite score — ADCB-style worked example (spec §6)
    5. Gap analysis and improvement roadmap
"""
from __future__ import annotations

import sys
import os

# Ensure the backend package is importable when running from repo root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import pytest

from app.core.scoring.fra_compliance import (
    FRA_GATE_SCORE_CAP,
    FRA_KPI_REGISTRY,
    MANDATORY_FRA_KPIS,
    check_fra_gate,
    extract_fra_results_from_scores,
    get_fra_compliance_report,
)
from app.core.scoring.gap_analysis import (
    generate_gap_analysis,
    generate_improvement_roadmap,
)
from app.core.scoring.materiality import (
    FINANCIAL_WEIGHTS,
    MANUFACTURING_WEIGHTS,
    validate_weights,
)
from app.core.scoring.scorer import (
    score_binary,
    score_composite,
    score_metric,
    score_pillar,
    score_qualitative,
    score_quantitative,
    score_q_plus_ql,
    score_to_grade,
    score_topic,
)
from app.models.enums import MetricDirection, MetricType
from app.schemas.metric import MetricScoreInput, MetricScoreOutput


# ===========================================================================
# Fixtures
# ===========================================================================

@pytest.fixture()
def fin_pillar_weights() -> dict[str, float]:
    return FINANCIAL_WEIGHTS.pillar_weights


@pytest.fixture()
def adcb_pillar_scores() -> dict[str, float]:
    """Pillar scores from the spec §6 worked example."""
    return {"E": 0.65, "S": 0.55, "G": 0.80}


@pytest.fixture()
def full_fra_results() -> dict[str, dict]:
    """All 17 FRA KPIs present (gate should pass if coverage >= 50%)."""
    return {kpi: {"present": True, "score": 0.8} for kpi in FRA_KPI_REGISTRY}


@pytest.fixture()
def sparse_fra_results() -> dict[str, dict]:
    """Only mandatory KPIs present — coverage = 4/17 ≈ 24% (gate fails)."""
    return {kpi: {"present": True, "score": 0.7} for kpi in MANDATORY_FRA_KPIS}


@pytest.fixture()
def gap_topic_scores() -> dict[str, float]:
    return {
        "FIN-E1": 0.20,
        "FIN-E2": 0.80,
        "FIN-G2": 0.00,
        "FIN-G3": 0.70,
        "FIN-S7": 0.10,
    }


@pytest.fixture()
def gap_topic_weights() -> dict[str, float]:
    return {
        "FIN-E1": 0.30,
        "FIN-E2": 0.20,
        "FIN-G2": 0.20,
        "FIN-G3": 0.12,
        "FIN-S7": 0.22,
    }


@pytest.fixture()
def gap_pillar_weights() -> dict[str, float]:
    return {"E": 0.25, "S": 0.40, "G": 0.35}


@pytest.fixture()
def gap_topic_to_pillar() -> dict[str, str]:
    return {
        "FIN-E1": "E",
        "FIN-E2": "E",
        "FIN-G2": "G",
        "FIN-G3": "G",
        "FIN-S7": "S",
    }


# ===========================================================================
# 1. Metric scoring functions
# ===========================================================================

class TestScoreBinary:
    @pytest.mark.parametrize("value, expected", [
        (True,    1.0),
        ("yes",   1.0),
        ("YES",   1.0),
        ("true",  1.0),
        ("1",     1.0),
        ("oui",   1.0),
        ("نعم",   1.0),
        (False,   0.0),
        ("no",    0.0),
        ("false", 0.0),
        (None,    0.0),
        ("",      0.0),
        (0,       0.0),
    ])
    def test_binary_values(self, value, expected):
        assert score_binary(value) == expected


class TestScoreQuantitative:
    def test_none_returns_zero(self):
        assert score_quantitative(None) == 0.0

    def test_empty_string_returns_zero(self):
        assert score_quantitative("") == 0.0

    def test_zero_no_benchmark_returns_1(self):
        # 0 is a numeric value — Stage 1 treats it as "exists" -> 1.0
        assert score_quantitative(0) == 1.0

    def test_nonzero_no_benchmark_returns_1(self):
        assert score_quantitative(500.0) == 1.0

    def test_negative_no_benchmark_returns_1(self):
        # Any non-zero value = exists = 1.0 in Stage 1
        assert score_quantitative(-10) == 1.0

    @pytest.mark.parametrize("value, benchmark, direction, expected", [
        # HIGHER_BETTER: value/benchmark, capped at 1.0
        (80,  100, MetricDirection.HIGHER_BETTER, 0.80),
        (100, 100, MetricDirection.HIGHER_BETTER, 1.00),
        (150, 100, MetricDirection.HIGHER_BETTER, 1.00),  # cap
        # LOWER_BETTER: benchmark/value, capped at 1.0
        (50,  100, MetricDirection.LOWER_BETTER,  1.00),  # value < benchmark -> capped
        (100, 100, MetricDirection.LOWER_BETTER,  1.00),
        (200, 100, MetricDirection.LOWER_BETTER,  0.50),
        # LOWER_BETTER with value == 0 -> 1.0
        (0,   100, MetricDirection.LOWER_BETTER,  1.00),
        # NEUTRAL: always 1.0
        (999, 100, MetricDirection.NEUTRAL,        1.00),
    ])
    def test_with_benchmark(self, value, benchmark, direction, expected):
        result = score_quantitative(value, benchmark=benchmark, direction=direction)
        assert abs(result - expected) < 0.001


class TestScoreQualitative:
    def test_none_text_returns_zero(self):
        assert score_qualitative(None, []) == 0.0

    def test_no_criteria_full_text_returns_1(self):
        # No criteria -> only checks if text is non-empty
        assert score_qualitative("some text", []) == 1.0

    def test_no_criteria_none_text_returns_zero(self):
        assert score_qualitative(None, []) == 0.0

    def test_zero_matches(self):
        result = score_qualitative("nothing relevant here", ["emissions", "target", "policy"])
        assert result == 0.0

    def test_partial_match(self):
        result = score_qualitative(
            "We have an emissions reduction policy.",
            ["emissions", "target", "governance", "verification"],
        )
        # matches 2/4 = 0.5
        assert abs(result - 0.5) < 0.01

    def test_full_match(self):
        text = "emissions target governance verification"
        result = score_qualitative(text, ["emissions", "target", "governance", "verification"])
        assert result == 1.0

    def test_case_insensitive(self):
        result = score_qualitative("EMISSIONS TARGET", ["emissions", "target"])
        assert result == 1.0


class TestScoreQPlusQl:
    def test_default_blend(self):
        # default: q_weight=0.6, ql_weight=0.4
        q = score_quantitative(80, benchmark=100, direction=MetricDirection.HIGHER_BETTER)
        ql = score_qualitative("emissions target", ["emissions", "target"])
        expected = 0.6 * q + 0.4 * ql
        result = score_q_plus_ql(80, "emissions target", ["emissions", "target"],
                                 benchmark=100, direction=MetricDirection.HIGHER_BETTER)
        assert abs(result - expected) < 0.001

    def test_custom_weights(self):
        result = score_q_plus_ql(
            100, "policy governance", ["policy", "governance"],
            benchmark=100, direction=MetricDirection.HIGHER_BETTER,
            q_weight=0.3, ql_weight=0.7,
        )
        # q=1.0, ql=1.0 -> result=1.0 regardless of weights
        assert abs(result - 1.0) < 0.001

    def test_zero_quantitative_non_zero_qualitative(self):
        result = score_q_plus_ql(
            None, "policy governance target verification",
            ["policy", "governance", "target", "verification"],
        )
        # q=0.0, ql=1.0 -> 0.6*0 + 0.4*1 = 0.4
        assert abs(result - 0.4) < 0.001


# ===========================================================================
# 2. Weight registry validation
# ===========================================================================

class TestWeightRegistries:
    @pytest.mark.parametrize("registry", [FINANCIAL_WEIGHTS, MANUFACTURING_WEIGHTS])
    def test_pillar_weights_sum_to_one(self, registry):
        total = sum(registry.pillar_weights.values())
        assert abs(total - 1.0) < 0.001, (
            f"{registry.sector} pillar weights sum={total:.4f}"
        )

    @pytest.mark.parametrize("registry", [FINANCIAL_WEIGHTS, MANUFACTURING_WEIGHTS])
    def test_topic_weights_sum_to_one_per_pillar(self, registry):
        for pillar, tw in registry.topic_weights.items():
            total = sum(tw.values())
            assert abs(total - 1.0) < 0.001, (
                f"{registry.sector} {pillar} topic weights sum={total:.4f}"
            )

    @pytest.mark.parametrize("registry", [FINANCIAL_WEIGHTS, MANUFACTURING_WEIGHTS])
    def test_metric_weights_sum_to_one_per_topic(self, registry):
        for topic_id, mw in registry.metric_weights.items():
            total = sum(mw.values())
            assert abs(total - 1.0) < 0.002, (
                f"{registry.sector} {topic_id} metric weights sum={total:.4f}"
            )

    @pytest.mark.parametrize("registry", [FINANCIAL_WEIGHTS, MANUFACTURING_WEIGHTS])
    def test_validate_weights_returns_no_errors(self, registry):
        errors = validate_weights(registry)
        assert errors == [], f"Weight validation errors: {errors}"

    def test_financial_has_e_s_g_pillars(self):
        assert set(FINANCIAL_WEIGHTS.pillar_weights.keys()) == {"E", "S", "G"}

    def test_manufacturing_has_e_s_g_pillars(self):
        assert set(MANUFACTURING_WEIGHTS.pillar_weights.keys()) == {"E", "S", "G"}

    def test_financial_sector_label(self):
        assert FINANCIAL_WEIGHTS.sector.lower() == "financial"

    def test_manufacturing_sector_label(self):
        assert MANUFACTURING_WEIGHTS.sector.lower() == "manufacturing"


# ===========================================================================
# 3. FRA compliance gate
# ===========================================================================

class TestFRAGate:
    def test_gate_passes_all_kpis_present(self, full_fra_results):
        result = check_fra_gate(full_fra_results)
        assert result["gate_passed"] is True
        assert result["mandatory_pass"] is True
        assert result["coverage_ratio"] == pytest.approx(1.0, abs=0.001)
        assert result["missing_mandatory"] == []

    def test_gate_fails_missing_mandatory_g2(self):
        fra_results = {kpi: {"present": True, "score": 0.8} for kpi in FRA_KPI_REGISTRY}
        fra_results["G2"] = {"present": False, "score": 0.0}
        result = check_fra_gate(fra_results)
        assert result["gate_passed"] is False
        assert result["mandatory_pass"] is False
        assert "G2" in result["missing_mandatory"]

    def test_gate_fails_low_coverage(self, sparse_fra_results):
        # Only 4 mandatory KPIs present → 4/17 ≈ 24% < 50% threshold
        result = check_fra_gate(sparse_fra_results)
        assert result["gate_passed"] is False
        assert result["coverage_ratio"] < 0.50

    def test_gate_fails_both_conditions_missing(self):
        # G2 missing AND coverage low
        fra_results = {"E1": {"present": True, "score": 0.7}}
        result = check_fra_gate(fra_results)
        assert result["gate_passed"] is False
        assert result["mandatory_pass"] is False
        assert "G2" in result["missing_mandatory"]

    def test_mandatory_kpis_constant(self):
        assert set(MANDATORY_FRA_KPIS) == {"E1", "G2", "G3", "G4"}

    def test_fra_gate_score_cap_value(self):
        assert FRA_GATE_SCORE_CAP == 60.0

    def test_gate_coverage_ratio_correct(self):
        # 9 out of 17 KPIs present -> 9/17 ≈ 0.529 -> gate passes if mandatory ok
        fra_results = {
            kpi: {"present": True, "score": 0.8}
            for kpi in list(FRA_KPI_REGISTRY.keys())[:9]
        }
        result = check_fra_gate(fra_results)
        assert abs(result["coverage_ratio"] - 9 / 17) < 0.001
        assert result["total_disclosed"] == 9
        assert result["total_kpis"] == 17

    def test_extract_fra_results_from_scores(self):
        topic_scores = {"FIN-E1": 0.8, "FIN-G2": 0.0, "FIN-G3": 0.5, "FIN-G4": 0.6}
        fra_map = {"FIN-E1": "E1", "FIN-G2": "G2", "FIN-G3": "G3", "FIN-G4": "G4"}
        fra_results = extract_fra_results_from_scores(topic_scores, fra_map)
        assert fra_results["E1"]["present"] is True
        assert fra_results["G2"]["present"] is False  # score == 0.0
        assert fra_results["G3"]["score"] == pytest.approx(0.5)

    def test_fra_compliance_report_summary_failed(self):
        fra_results = {"E1": {"present": True, "score": 0.8}}  # G2/G3/G4 missing
        gate = check_fra_gate(fra_results)
        report = get_fra_compliance_report(fra_results, gate)
        assert report["gate_passed"] is False
        assert report["score_cap"] == FRA_GATE_SCORE_CAP
        assert "FAILED" in report["summary"]

    def test_fra_compliance_report_summary_passed(self, full_fra_results):
        gate = check_fra_gate(full_fra_results)
        report = get_fra_compliance_report(full_fra_results, gate)
        assert report["gate_passed"] is True
        assert report["score_cap"] is None
        assert "PASSED" in report["summary"]


# ===========================================================================
# 4. Composite score — ADCB-style worked example (spec §6)
# ===========================================================================

class TestCompositeScore:
    """
    Worked example from spec Section 6:
        E=0.65, S=0.55, G=0.80
        weights: E=0.25, S=0.40, G=0.35
        raw = 0.65*0.25 + 0.55*0.40 + 0.80*0.35 = 0.6625 -> 66.25 pts
        assurance bonus +5 pts -> final = 71.25, grade = 'B'
    """
    PILLAR_SCORES  = {"E": 0.65, "S": 0.55, "G": 0.80}
    PILLAR_WEIGHTS = {"E": 0.25, "S": 0.40, "G": 0.35}

    def test_raw_score(self):
        result = score_composite(self.PILLAR_SCORES, self.PILLAR_WEIGHTS)
        assert abs(result["raw_score"] - 66.25) < 0.5

    def test_final_score_with_assurance(self):
        result = score_composite(
            self.PILLAR_SCORES, self.PILLAR_WEIGHTS, external_assurance=True
        )
        assert abs(result["final_score"] - 71.25) < 0.5

    def test_grade_b(self):
        result = score_composite(
            self.PILLAR_SCORES, self.PILLAR_WEIGHTS, external_assurance=True
        )
        assert result["grade"] == "B"

    def test_assurance_bonus_applied_flag(self):
        result = score_composite(
            self.PILLAR_SCORES, self.PILLAR_WEIGHTS, external_assurance=True
        )
        assert result["assurance_bonus_applied"] is True

    def test_no_assurance_lower_score(self):
        with_assurance    = score_composite(self.PILLAR_SCORES, self.PILLAR_WEIGHTS, external_assurance=True)
        without_assurance = score_composite(self.PILLAR_SCORES, self.PILLAR_WEIGHTS, external_assurance=False)
        assert with_assurance["final_score"] > without_assurance["final_score"]

    def test_score_capped_at_100(self):
        result = score_composite({"E": 1.0, "S": 1.0, "G": 1.0},
                                 self.PILLAR_WEIGHTS, external_assurance=True)
        assert result["final_score"] <= 100.0

    @pytest.mark.parametrize("score, expected_grade", [
        (95, "A"),
        (80, "B"),
        (65, "C"),
        (50, "D"),
        (40, "D"),  # D boundary
        (35, "F"),  # no 'E' grade — drops directly to F
        (15, "F"),
    ])
    def test_grade_boundaries(self, score, expected_grade):
        assert score_to_grade(score) == expected_grade


# ===========================================================================
# 5. score_topic and score_pillar
# ===========================================================================

class TestTopicPillarAggregation:
    def _make_output(self, code: str, raw: float, weight: float) -> MetricScoreOutput:
        return MetricScoreOutput(
            metric_code=code,
            metric_type=MetricType.QUANTITATIVE,
            raw_score=raw,
            weight_in_topic=weight,
            weighted_contribution=raw * weight,
            fra_required=False,
            scoring_notes="test",
        )

    def test_score_topic_weighted_average(self):
        metrics = [
            self._make_output("M1", 1.0, 0.40),
            self._make_output("M2", 0.5, 0.60),
        ]
        result = score_topic(metrics)
        assert abs(result - (1.0 * 0.40 + 0.5 * 0.60)) < 0.001

    def test_score_topic_empty_list_returns_zero(self):
        assert score_topic([]) == 0.0

    def test_score_topic_normalises_when_weights_off(self):
        # Weights sum to 2.0 — should normalise
        metrics = [
            self._make_output("M1", 1.0, 1.0),
            self._make_output("M2", 0.0, 1.0),
        ]
        result = score_topic(metrics)
        assert abs(result - 0.5) < 0.001

    def test_score_pillar_weighted_average(self):
        topics = [
            {"id": "T1", "score": 0.8, "weight": 0.6},
            {"id": "T2", "score": 0.4, "weight": 0.4},
        ]
        result = score_pillar(topics)
        assert abs(result - (0.8 * 0.6 + 0.4 * 0.4)) < 0.001

    def test_score_pillar_empty_returns_zero(self):
        assert score_pillar([]) == 0.0


# ===========================================================================
# 6. Gap analysis and improvement roadmap
# ===========================================================================

class TestGapAnalysis:
    def test_high_priority_gap_identified(
        self, gap_topic_scores, gap_topic_weights, gap_pillar_weights, gap_topic_to_pillar
    ):
        results = generate_gap_analysis(
            gap_topic_scores, gap_topic_weights, gap_pillar_weights, gap_topic_to_pillar
        )
        assert len(results) > 0
        # Highest gain topic should be HIGH priority
        top = results[0]
        assert top["priority"] == "HIGH"
        assert top["potential_gain_points"] >= 3.0

    def test_sorted_descending_by_gain(
        self, gap_topic_scores, gap_topic_weights, gap_pillar_weights, gap_topic_to_pillar
    ):
        results = generate_gap_analysis(
            gap_topic_scores, gap_topic_weights, gap_pillar_weights, gap_topic_to_pillar
        )
        gains = [r["potential_gain_points"] for r in results]
        assert gains == sorted(gains, reverse=True)

    def test_zero_gap_for_perfect_score(
        self, gap_topic_weights, gap_pillar_weights, gap_topic_to_pillar
    ):
        perfect_scores = {tid: 1.0 for tid in gap_topic_weights}
        results = generate_gap_analysis(
            perfect_scores, gap_topic_weights, gap_pillar_weights, gap_topic_to_pillar
        )
        for r in results:
            assert r["potential_gain_points"] == pytest.approx(0.0, abs=0.001)

    def test_result_keys_present(
        self, gap_topic_scores, gap_topic_weights, gap_pillar_weights, gap_topic_to_pillar
    ):
        results = generate_gap_analysis(
            gap_topic_scores, gap_topic_weights, gap_pillar_weights, gap_topic_to_pillar
        )
        required = {"topic_id", "pillar", "current_score", "potential_gain_points", "priority"}
        for r in results:
            assert required.issubset(r.keys())

    def test_roadmap_separates_immediate_and_high(
        self, gap_topic_scores, gap_topic_weights, gap_pillar_weights, gap_topic_to_pillar
    ):
        fra_map = {
            "FIN-E1": "E1", "FIN-G2": "G2", "FIN-G3": "G3",
        }
        fra_results = extract_fra_results_from_scores(gap_topic_scores, fra_map)
        gate = check_fra_gate(fra_results)
        gaps = generate_gap_analysis(
            gap_topic_scores, gap_topic_weights, gap_pillar_weights, gap_topic_to_pillar
        )
        roadmap = generate_improvement_roadmap(gaps, gate, "FINANCIAL", fra_results)

        assert "immediate_actions" in roadmap
        assert "high_priority" in roadmap
        assert "medium_priority" in roadmap
        assert "stage2_preparation" in roadmap
        assert "summary" in roadmap

        # G2 is missing (score=0) and mandatory -> must appear in immediate actions
        immediate_kpis = [a["fra_kpi"] for a in roadmap["immediate_actions"]]
        assert "G2" in immediate_kpis

    def test_roadmap_summary_counts(
        self, gap_topic_scores, gap_topic_weights, gap_pillar_weights, gap_topic_to_pillar
    ):
        fra_map = {"FIN-E1": "E1", "FIN-G2": "G2", "FIN-G3": "G3"}
        fra_results = extract_fra_results_from_scores(gap_topic_scores, fra_map)
        gate = check_fra_gate(fra_results)
        gaps = generate_gap_analysis(
            gap_topic_scores, gap_topic_weights, gap_pillar_weights, gap_topic_to_pillar
        )
        roadmap = generate_improvement_roadmap(gaps, gate, "FINANCIAL", fra_results)
        summary = roadmap["summary"]

        assert summary["n_immediate"] == len(roadmap["immediate_actions"])
        assert summary["n_high"]      == len(roadmap["high_priority"])
        assert summary["n_medium"]    == len(roadmap["medium_priority"])
        assert summary["n_stage2"]    == len(roadmap["stage2_preparation"])

    def test_stage2_topics_in_roadmap_for_financial(
        self, gap_topic_scores, gap_topic_weights, gap_pillar_weights, gap_topic_to_pillar
    ):
        fra_results = {}
        gate = check_fra_gate(fra_results)
        gaps = generate_gap_analysis(
            gap_topic_scores, gap_topic_weights, gap_pillar_weights, gap_topic_to_pillar
        )
        roadmap = generate_improvement_roadmap(gaps, gate, "FINANCIAL")
        stage2_ids = {r["topic_id"] for r in roadmap["stage2_preparation"]}
        # FIN-S7 appears in our gap scores and is a Stage 2 topic
        assert "FIN-S7" in stage2_ids


# ===========================================================================
# 7. score_metric dispatcher (integration)
# ===========================================================================

class TestScoreMetricDispatcher:
    def _inp(self, mt, value=None, text=None, benchmark=None,
             direction=MetricDirection.NEUTRAL, criteria=None, w=0.5) -> MetricScoreInput:
        return MetricScoreInput(
            metric_code="TEST",
            metric_type=mt,
            extracted_value=value,
            extracted_text=text,
            benchmark=benchmark,
            direction=direction,
            completeness_criteria=criteria or [],
            weight_in_topic=w,
            fra_required=False,
        )

    def test_binary_dispatch(self):
        out = score_metric(self._inp(MetricType.BINARY, value="yes", w=0.4))
        assert out.raw_score == 1.0
        assert abs(out.weighted_contribution - 0.4) < 0.001

    def test_quantitative_dispatch(self):
        out = score_metric(self._inp(MetricType.QUANTITATIVE, value=80,
                                     benchmark=100, direction=MetricDirection.HIGHER_BETTER))
        assert abs(out.raw_score - 0.8) < 0.001

    def test_qualitative_dispatch(self):
        out = score_metric(self._inp(
            MetricType.QUALITATIVE,
            text="policy governance target",
            criteria=["policy", "governance", "target"],
        ))
        assert out.raw_score == 1.0

    def test_q_plus_ql_dispatch(self):
        out = score_metric(self._inp(
            MetricType.Q_PLUS_QL,
            value=50, benchmark=100, direction=MetricDirection.HIGHER_BETTER,
            text="policy governance",
            criteria=["policy", "governance"],
        ))
        # q=0.5, ql=1.0 -> 0.6*0.5+0.4*1.0 = 0.70
        assert abs(out.raw_score - 0.70) < 0.01

    def test_output_fields_populated(self):
        out = score_metric(self._inp(MetricType.BINARY, value="yes", w=0.3))
        assert out.metric_code == "TEST"
        assert out.metric_type == MetricType.BINARY
        assert isinstance(out.scoring_notes, str)
        assert out.weight_in_topic == pytest.approx(0.3)
        assert out.weighted_contribution == pytest.approx(0.3)
