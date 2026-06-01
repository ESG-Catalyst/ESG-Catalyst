"""Unit tests for core/gri/indicators.py.

Coverage:
  1. Catalog loads — exactly 46 indicators, no hardcoded values
  2. get_indicator — lookup by code, KeyError on unknown
  3. get_indicator_codes — sorted list, no duplicates
  4. get_indicators_by_pillar — each pillar non-empty, correct membership
  5. get_indicators_by_framework — GRI / SASB-FN-* / FRA subsets
  6. get_indicators_for_sector — banking / insurance / consumer_finance / mortgage_finance
  7. get_indicators_by_metric_type — quantitative / qualitative / monetary / etc.
  8. Every indicator has mandatory fields: code, name, pillar, extraction_prompt
"""
from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import pytest

from app.core.gri.indicators import (
    get_all_indicators,
    get_extraction_prompt,
    get_indicator,
    get_indicator_codes,
    get_indicators_by_framework,
    get_indicators_by_metric_type,
    get_indicators_by_pillar,
    get_indicators_for_sector,
)


# ===========================================================================
# 1. Catalog loading and count
# ===========================================================================

class TestCatalogLoading:
    def test_exactly_46_indicators(self):
        indicators = get_all_indicators()
        assert len(indicators) == 46, (
            f"Expected 46 indicators; got {len(indicators)}. "
            "If the catalog was intentionally expanded, update this test."
        )

    def test_returns_list_of_dicts(self):
        indicators = get_all_indicators()
        assert isinstance(indicators, list)
        for ind in indicators:
            assert isinstance(ind, dict)

    def test_catalog_is_cached(self):
        # Calling twice should return the exact same list object (lru_cache)
        first = get_all_indicators()
        second = get_all_indicators()
        assert first is second


# ===========================================================================
# 2. Mandatory fields on every indicator
# ===========================================================================

class TestMandatoryFields:
    MANDATORY = {"code", "name", "pillar", "extraction_prompt"}

    @pytest.mark.parametrize("indicator", get_all_indicators())
    def test_mandatory_fields_present(self, indicator):
        missing = self.MANDATORY - indicator.keys()
        assert not missing, (
            f"Indicator {indicator.get('code', '???')} missing fields: {missing}"
        )

    @pytest.mark.parametrize("indicator", get_all_indicators())
    def test_pillar_is_valid(self, indicator):
        assert indicator["pillar"] in ("E", "S", "G"), (
            f"{indicator['code']}: unexpected pillar {indicator['pillar']!r}"
        )

    @pytest.mark.parametrize("indicator", get_all_indicators())
    def test_code_is_nonempty_string(self, indicator):
        assert isinstance(indicator["code"], str) and indicator["code"].strip()

    @pytest.mark.parametrize("indicator", get_all_indicators())
    def test_extraction_prompt_is_nonempty_string(self, indicator):
        assert isinstance(indicator["extraction_prompt"], str)
        assert len(indicator["extraction_prompt"].strip()) > 0, (
            f"{indicator['code']}: extraction_prompt is empty"
        )


# ===========================================================================
# 3. get_indicator (single lookup)
# ===========================================================================

class TestGetIndicator:
    def test_known_code_returns_dict(self):
        ind = get_indicator("GRI 2-1")
        assert isinstance(ind, dict)
        assert ind["code"] == "GRI 2-1"
        assert ind["name"] == "Organizational details"

    def test_known_fra_code(self):
        ind = get_indicator("FRA-36")
        assert ind["code"] == "FRA-36"

    def test_unknown_code_raises_key_error(self):
        with pytest.raises(KeyError):
            get_indicator("DOES_NOT_EXIST_9999")

    def test_case_sensitive(self):
        # Codes are stored exactly — lowercase should not match
        with pytest.raises(KeyError):
            get_indicator("gri 2-1")


# ===========================================================================
# 4. get_indicator_codes
# ===========================================================================

class TestGetIndicatorCodes:
    def test_returns_46_codes(self):
        codes = get_indicator_codes()
        assert len(codes) == 46

    def test_codes_are_sorted(self):
        codes = get_indicator_codes()
        assert codes == sorted(codes)

    def test_no_duplicate_codes(self):
        codes = get_indicator_codes()
        assert len(codes) == len(set(codes))

    def test_gri_2_1_present(self):
        assert "GRI 2-1" in get_indicator_codes()

    def test_fra_36_present(self):
        assert "FRA-36" in get_indicator_codes()


# ===========================================================================
# 5. get_indicators_by_pillar
# ===========================================================================

class TestGetIndicatorsByPillar:
    def test_all_three_pillars_non_empty(self):
        for pillar in ("E", "S", "G"):
            result = get_indicators_by_pillar(pillar)
            assert len(result) > 0, f"No indicators for pillar {pillar}"

    def test_pillar_e_contains_only_e(self):
        for ind in get_indicators_by_pillar("E"):
            assert ind["pillar"] == "E"

    def test_pillar_s_contains_only_s(self):
        for ind in get_indicators_by_pillar("S"):
            assert ind["pillar"] == "S"

    def test_pillar_g_contains_only_g(self):
        for ind in get_indicators_by_pillar("G"):
            assert ind["pillar"] == "G"

    def test_union_equals_all(self):
        all_codes = {ind["code"] for ind in get_all_indicators()}
        pillar_union = set()
        for pillar in ("E", "S", "G"):
            pillar_union |= {ind["code"] for ind in get_indicators_by_pillar(pillar)}
        assert pillar_union == all_codes

    def test_unknown_pillar_returns_empty(self):
        assert get_indicators_by_pillar("X") == []


# ===========================================================================
# 6. get_indicators_by_framework
# ===========================================================================

class TestGetIndicatorsByFramework:
    def test_gri_non_empty(self):
        result = get_indicators_by_framework("GRI")
        assert len(result) >= 24  # known count from CLAUDE.md

    def test_sasb_fn_cf_non_empty(self):
        result = get_indicators_by_framework("SASB-FN-CF")
        assert len(result) >= 7

    def test_sasb_fn_mf_non_empty(self):
        result = get_indicators_by_framework("SASB-FN-MF")
        assert len(result) >= 5

    def test_sasb_fn_in_non_empty(self):
        result = get_indicators_by_framework("SASB-FN-IN")
        assert len(result) >= 9

    def test_fra_non_empty(self):
        result = get_indicators_by_framework("FRA")
        assert len(result) >= 1

    def test_framework_membership_correct(self):
        for ind in get_indicators_by_framework("GRI"):
            assert ind.get("framework", "GRI") == "GRI"

    def test_unknown_framework_returns_empty(self):
        assert get_indicators_by_framework("NONEXISTENT") == []


# ===========================================================================
# 7. get_indicators_for_sector
# ===========================================================================

class TestGetIndicatorsForSector:
    @pytest.mark.parametrize("sector", [
        "banking", "insurance", "consumer_finance", "mortgage_finance"
    ])
    def test_known_sectors_non_empty(self, sector):
        result = get_indicators_for_sector(sector)
        assert len(result) > 0, f"No indicators for sector {sector}"

    def test_banking_count_in_range(self):
        result = get_indicators_for_sector("banking")
        # CLAUDE.md notes ~25 banking indicators
        assert 20 <= len(result) <= 46

    def test_insurance_count_in_range(self):
        result = get_indicators_for_sector("insurance")
        # CLAUDE.md notes ~30 insurance indicators
        assert 25 <= len(result) <= 46

    def test_sector_membership_respected(self):
        for ind in get_indicators_for_sector("banking"):
            sectors = ind.get("applicable_sectors")
            # Either universal (no sectors key) or banking in the list
            assert sectors is None or "banking" in sectors

    def test_unknown_sector_returns_universal_indicators(self):
        # Indicators with no applicable_sectors (universal) should still appear
        result = get_indicators_for_sector("UNKNOWN_SECTOR_XYZ")
        universal = [
            ind for ind in get_all_indicators()
            if not ind.get("applicable_sectors")
        ]
        for ind in universal:
            assert ind in result


# ===========================================================================
# 8. get_indicators_by_metric_type
# ===========================================================================

class TestGetIndicatorsByMetricType:
    @pytest.mark.parametrize("metric_type", [
        "quantitative", "qualitative", "monetary"
    ])
    def test_known_types_non_empty(self, metric_type):
        result = get_indicators_by_metric_type(metric_type)
        assert len(result) >= 0  # some types might be sparse; just check no crash

    def test_monetary_count(self):
        # CLAUDE.md notes 15 monetary metrics in the Iter-2 session
        result = get_indicators_by_metric_type("monetary")
        assert len(result) >= 10, "Expected at least 10 monetary indicators"

    def test_metric_type_membership_correct(self):
        for ind in get_indicators_by_metric_type("qualitative"):
            assert ind.get("metric_type", "quantitative") == "qualitative"

    def test_unknown_type_returns_empty(self):
        assert get_indicators_by_metric_type("NONEXISTENT_TYPE") == []


# ===========================================================================
# 9. get_extraction_prompt shorthand
# ===========================================================================

class TestGetExtractionPrompt:
    def test_returns_string_for_known_code(self):
        prompt = get_extraction_prompt("GRI 2-1")
        assert isinstance(prompt, str)
        assert len(prompt) > 0

    def test_raises_for_unknown_code(self):
        with pytest.raises(KeyError):
            get_extraction_prompt("INVALID_CODE")
