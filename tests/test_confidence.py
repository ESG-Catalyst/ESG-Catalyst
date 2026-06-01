"""Unit tests for core/extraction/confidence.py.

Coverage:
  1. adjust_confidence — no flags (identity)
  2. adjust_confidence — each penalty flag individually
  3. adjust_confidence — combined flags (multiplicative)
  4. adjust_confidence — clamping at 0.0 and 1.0
  5. has_approximate_language — positive and negative cases
"""
from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import pytest

from app.core.extraction.confidence import adjust_confidence, has_approximate_language


# ===========================================================================
# 1. adjust_confidence — baseline
# ===========================================================================

class TestAdjustConfidenceBaseline:
    def test_no_flags_returns_base(self):
        assert adjust_confidence(0.9) == pytest.approx(0.9)

    def test_base_1_no_flags(self):
        assert adjust_confidence(1.0) == pytest.approx(1.0)

    def test_base_0_no_flags(self):
        assert adjust_confidence(0.0) == pytest.approx(0.0)


# ===========================================================================
# 2. Each penalty flag individually
# ===========================================================================

class TestAdjustConfidenceIndividualFlags:
    BASE = 1.0

    def test_indirect_language_penalty(self):
        # indirect_language -> * 0.7
        result = adjust_confidence(self.BASE, indirect_language=True)
        assert result == pytest.approx(0.7)

    def test_is_approximate_penalty(self):
        # is_approximate -> * 0.85
        result = adjust_confidence(self.BASE, is_approximate=True)
        assert result == pytest.approx(0.85)

    def test_unit_ambiguous_penalty(self):
        # unit_ambiguous -> * 0.85
        result = adjust_confidence(self.BASE, unit_ambiguous=True)
        assert result == pytest.approx(0.85)

    def test_is_ocr_penalty(self):
        # is_ocr -> * 0.9
        result = adjust_confidence(self.BASE, is_ocr=True)
        assert result == pytest.approx(0.9)

    def test_single_source_penalty(self):
        # single_source -> * 0.95
        result = adjust_confidence(self.BASE, single_source=True)
        assert result == pytest.approx(0.95)


# ===========================================================================
# 3. Combined flags (multiplicative order matches source code)
# ===========================================================================

class TestAdjustConfidenceCombined:
    def test_ocr_plus_approximate(self):
        # 0.9 * 0.85 * 0.9 (base=0.9, is_ocr, is_approximate)
        # applied in order: indirect_language first (off), then is_approximate (* 0.85),
        # unit_ambiguous (off), is_ocr (* 0.9), single_source (off)
        base = 0.9
        result = adjust_confidence(base, is_approximate=True, is_ocr=True)
        expected = base * 0.85 * 0.9
        assert result == pytest.approx(expected, rel=1e-6)

    def test_all_flags(self):
        base = 1.0
        result = adjust_confidence(
            base,
            is_ocr=True,
            is_approximate=True,
            unit_ambiguous=True,
            single_source=True,
            indirect_language=True,
        )
        expected = 1.0 * 0.7 * 0.85 * 0.85 * 0.9 * 0.95
        assert result == pytest.approx(expected, rel=1e-6)

    def test_combined_does_not_exceed_base(self):
        result = adjust_confidence(0.8, is_ocr=True, single_source=True)
        assert result <= 0.8


# ===========================================================================
# 4. Clamping
# ===========================================================================

class TestAdjustConfidenceClamping:
    def test_never_below_zero(self):
        # Extremely low base with all penalties
        result = adjust_confidence(
            0.01,
            indirect_language=True,
            is_approximate=True,
            unit_ambiguous=True,
            is_ocr=True,
            single_source=True,
        )
        assert result >= 0.0

    def test_base_above_one_clamped(self):
        # Passing a value > 1.0 is not valid usage but should not crash
        result = adjust_confidence(1.5)
        # No flags → value unchanged at 1.5, then clamped to 1.0
        assert result <= 1.0


# ===========================================================================
# 5. has_approximate_language
# ===========================================================================

class TestHasApproximateLanguage:
    @pytest.mark.parametrize("text", [
        "The value is approximately 500 tCO2e.",
        "Energy consumption was around 1,200 GJ.",
        "Roughly 40% of waste was recycled.",
        "About 200 employees attended training.",
        "Estimated emissions include Scope 1 and 2.",
        "~ 300 kWh were consumed.",
        "≈ 50 metric tons of waste.",
        "Nearly all emissions are Scope 2.",
        "Almost 100% renewable energy.",
        "Water usage: approx 5000 m3.",
        "Circa 2 million USD invested.",
    ])
    def test_detects_approximate_terms(self, text):
        assert has_approximate_language(text) is True

    @pytest.mark.parametrize("text", [
        "Total energy consumption: 1,234 GJ.",
        "The board consists of 12 directors.",
        "Scope 1 emissions: 960 tCO2e.",
        "Water withdrawn from municipal supplies: 5000 m3.",
    ])
    def test_no_false_positives(self, text):
        assert has_approximate_language(text) is False

    def test_empty_string(self):
        assert has_approximate_language("") is False

    def test_case_insensitive(self):
        assert has_approximate_language("APPROXIMATELY 500 MWh") is True
