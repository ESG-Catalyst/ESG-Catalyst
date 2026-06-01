"""Unit tests for core/extraction/validator.py.

Coverage:
  1. parse_monetary — standard Western strings, magnitude words, sign, currency placement
  2. parse_monetary — Arabic-Indic digits, Arabic decimal (U+066B) / thousands (U+066C)
  3. parse_monetary — edge cases (None, empty, unrecognized)
  4. normalize_currency — ISO-4217 pass-through, Arabic/English aliases, substring match
  5. normalize_energy / normalize_water — spot-check unit conversion helpers
  6. safe_float / safe_int — None, valid, invalid
  7. clamp
"""
from __future__ import annotations

import sys
import os

# Mirror the import pattern from tests/test_scoring.py
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import pytest

from app.core.extraction.validator import (
    clamp,
    normalize_currency,
    normalize_energy,
    normalize_water,
    parse_monetary,
    safe_float,
    safe_int,
)


# ===========================================================================
# 1. normalize_currency
# ===========================================================================

class TestNormalizeCurrency:
    @pytest.mark.parametrize("raw, expected", [
        # Direct ISO-4217 pass-through (3 uppercase letters)
        ("USD", "USD"),
        ("EGP", "EGP"),
        ("EUR", "EUR"),
        ("GBP", "GBP"),
        # Arabic/English aliases
        ("egp", "EGP"),
        ("le", "EGP"),
        ("l.e.", "EGP"),
        ("egyptian pound", "EGP"),
        ("جنيه", "EGP"),
        ("usd", "USD"),
        ("us$", "USD"),
        ("$", "USD"),
        ("dollar", "USD"),
        ("eur", "EUR"),
        ("€", "EUR"),
        ("euro", "EUR"),
        ("gbp", "GBP"),
        ("£", "GBP"),
        ("pound sterling", "GBP"),
        # MENA currencies
        ("aed", "AED"),
        ("sar", "SAR"),
        ("kwd", "KWD"),
        ("qar", "QAR"),
        # Substring matching (e.g., "EGP million" → "EGP" found in key "egp")
        ("EGP million", "EGP"),
        ("USD millions", "USD"),
    ])
    def test_known_aliases(self, raw, expected):
        assert normalize_currency(raw) == expected

    @pytest.mark.parametrize("raw", [None, "", "   "])
    def test_none_and_empty(self, raw):
        assert normalize_currency(raw) is None

    def test_unrecognized_returns_none(self):
        assert normalize_currency("XYZ_UNKNOWN_CURR") is None


# ===========================================================================
# 2. parse_monetary — Western / standard cases
# ===========================================================================

class TestParseMonetaryStandard:
    @pytest.mark.parametrize("raw, expected_value, expected_currency", [
        ("EGP 1.2 billion",  1_200_000_000.0, "EGP"),
        ("USD 540 mn",       540_000_000.0,   "USD"),
        ("$2500",            2_500.0,          "USD"),
        ("$2,500",           2_500.0,          "USD"),
        # Magnitude variants
        ("EUR 5 million",    5_000_000.0,      "EUR"),
        ("GBP 1.5 billion",  1_500_000_000.0,  "GBP"),
        ("USD 10 thousand",  10_000.0,         "USD"),
        ("USD 10k",          10_000.0,         "USD"),
        ("USD 1 trillion",   1_000_000_000_000.0, "USD"),
        # No currency prefix/suffix → value parseable, currency None
        ("1,200,000",        1_200_000.0,      None),
        # Negative
        ("-USD 500 mn",      -500_000_000.0,   "USD"),
        # Simple plain number
        ("42",               42.0,             None),
    ])
    def test_standard_monetary(self, raw, expected_value, expected_currency):
        val, cur = parse_monetary(raw)
        assert val == pytest.approx(expected_value, rel=1e-6), f"value mismatch for {raw!r}"
        assert cur == expected_currency, f"currency mismatch for {raw!r}"

    def test_none_input(self):
        val, cur = parse_monetary(None)
        assert val is None
        assert cur is None

    def test_empty_string(self):
        val, cur = parse_monetary("")
        assert val is None
        assert cur is None

    def test_non_string_returns_none_none(self):
        val, cur = parse_monetary(12345)  # type: ignore[arg-type]
        assert val is None
        assert cur is None


# ===========================================================================
# 3. parse_monetary — Arabic-Indic digits and Arabic decimal / thousands
# ===========================================================================

class TestParseMonetaryArabic:
    def test_arabic_indic_digits_plain(self):
        # ١٢٣٤ = 1234
        val, cur = parse_monetary("١٢٣٤")
        assert val == pytest.approx(1234.0, rel=1e-6)
        assert cur is None

    def test_arabic_decimal_separator(self):
        # Arabic decimal separator U+066B: ١٫٢ = 1.2
        val, cur = parse_monetary("١٫٢")
        assert val == pytest.approx(1.2, rel=1e-6)
        assert cur is None

    def test_arabic_thousands_separator(self):
        # Arabic thousands separator U+066C: ١٬٢٠٠ = 1200
        val, cur = parse_monetary("١٬٢٠٠")
        assert val == pytest.approx(1200.0, rel=1e-6)
        assert cur is None

    def test_arabic_indic_with_magnitude(self):
        # ١٠ billion = 10,000,000,000
        val, cur = parse_monetary("١٠ billion")
        assert val == pytest.approx(10_000_000_000.0, rel=1e-6)

    def test_arabic_indic_with_egp_prefix(self):
        # EGP ٥٠٠ = 500 EGP
        val, cur = parse_monetary("EGP ٥٠٠")
        assert val == pytest.approx(500.0, rel=1e-6)
        assert cur == "EGP"


# ===========================================================================
# 4. normalize_energy / normalize_water
# ===========================================================================

class TestNormalizeEnergy:
    @pytest.mark.parametrize("value, unit, expected_gj", [
        (1.0, "GJ",    1.0),
        (1.0, "gj",    1.0),       # case-insensitive
        (1.0, "MWh",   3.6),
        (1.0, "kWh",   0.0036),
        (1.0, "TJ",    1000.0),
        (1.0, "GWh",   3600.0),
        (1.0, "toe",   41.868),
        (1.0, "mmbtu", 1.05505),
    ])
    def test_known_units(self, value, unit, expected_gj):
        result = normalize_energy(value, unit)
        assert result is not None
        norm_val, norm_unit = result
        assert norm_unit == "GJ"
        assert norm_val == pytest.approx(expected_gj, rel=1e-4)

    def test_unknown_unit_returns_none(self):
        assert normalize_energy(1.0, "stones") is None


class TestNormalizeWater:
    @pytest.mark.parametrize("value, unit, expected_m3", [
        (1.0, "m3",       1.0),
        (1.0, "m³",       1.0),
        (1000.0, "liter", 1.0),
        (1000.0, "l",     1.0),
        (1.0, "megaliter", 1000.0),
        (1.0, "gallon",   0.003785),
    ])
    def test_known_units(self, value, unit, expected_m3):
        result = normalize_water(value, unit)
        assert result is not None
        norm_val, norm_unit = result
        assert norm_unit == "m3"
        assert norm_val == pytest.approx(expected_m3, rel=1e-4)

    def test_unknown_unit_returns_none(self):
        assert normalize_water(1.0, "buckets") is None


# ===========================================================================
# 5. safe_float / safe_int / clamp
# ===========================================================================

class TestSafeFloat:
    def test_none_returns_none(self):
        assert safe_float(None) is None

    def test_int_to_float(self):
        assert safe_float(42) == pytest.approx(42.0)

    def test_string_number(self):
        assert safe_float("3.14") == pytest.approx(3.14)

    def test_invalid_string_returns_none(self):
        assert safe_float("not_a_number") is None


class TestSafeInt:
    def test_none_returns_none(self):
        assert safe_int(None) is None

    def test_float_to_int(self):
        assert safe_int(3.9) == 3

    def test_string_number(self):
        assert safe_int("7") == 7

    def test_invalid_string_returns_none(self):
        assert safe_int("abc") is None


class TestClamp:
    def test_below_lo(self):
        assert clamp(-5.0, 0.0, 1.0) == 0.0

    def test_above_hi(self):
        assert clamp(2.0, 0.0, 1.0) == 1.0

    def test_within_range(self):
        assert clamp(0.5, 0.0, 1.0) == pytest.approx(0.5)

    def test_at_boundary(self):
        assert clamp(0.0, 0.0, 1.0) == 0.0
        assert clamp(1.0, 0.0, 1.0) == 1.0
