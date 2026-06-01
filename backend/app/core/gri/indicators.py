"""GRI indicator definitions — loaded from data/gri_indicators.json.

Never hardcode indicator definitions in Python. This module is the single
access point for indicator metadata, extraction prompts, and validation rules.

Usage:
    from app.core.gri.indicators import get_indicator, get_all_indicators

    indicator = get_indicator("GRI 302-1")
    prompt = indicator["extraction_prompt"]
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# Resolve path relative to the project root (two levels up from this file).
_DATA_FILE: Path = Path(__file__).resolve().parents[4] / "data" / "gri_indicators.json"


@lru_cache(maxsize=1)
def _load_indicators() -> dict[str, Any]:
    """Load and cache the indicator JSON file.

    Raises:
        FileNotFoundError: If ``data/gri_indicators.json`` is missing.
        json.JSONDecodeError: If the file is malformed.
    """
    logger.info("gri.indicators.loading", path=str(_DATA_FILE))
    with open(_DATA_FILE) as f:
        data = json.load(f)
    logger.info("gri.indicators.loaded", count=len(data["indicators"]))
    return data


def get_all_indicators() -> list[dict[str, Any]]:
    """Return the full list of indicator definitions."""
    return _load_indicators()["indicators"]


def get_indicator(code: str) -> dict[str, Any]:
    """Look up a single indicator by its code (e.g. ``"GRI 302-1"``).

    Args:
        code: The indicator code, case-sensitive.

    Raises:
        KeyError: If no indicator matches *code*.
    """
    for ind in get_all_indicators():
        if ind["code"] == code:
            return ind
    raise KeyError(f"Indicator {code!r} not found in {_DATA_FILE.name}")


def get_indicators_by_pillar(pillar: str) -> list[dict[str, Any]]:
    """Return all indicators for a given ESG pillar (``"E"``, ``"S"``, ``"G"``)."""
    return [ind for ind in get_all_indicators() if ind["pillar"] == pillar]


def get_indicator_codes() -> list[str]:
    """Return a sorted list of all indicator codes."""
    return sorted(ind["code"] for ind in get_all_indicators())


def get_extraction_prompt(code: str) -> str:
    """Shorthand — return just the extraction prompt for an indicator code."""
    return get_indicator(code)["extraction_prompt"]


# ── Iteration 2 helpers — framework + sector aware lookups ────────────────
def get_indicators_by_framework(framework: str) -> list[dict[str, Any]]:
    """Return all indicators belonging to a given framework.

    Examples:
        ``"GRI"``, ``"SASB-FN-CF"``, ``"SASB-FN-MF"``, ``"SASB-FN-IN"``, ``"FRA"``.

    Pre-Iteration-2 indicators that lack the ``framework`` key are treated as GRI.
    """
    target = framework.strip()
    return [
        ind
        for ind in get_all_indicators()
        if ind.get("framework", "GRI") == target
    ]


def get_indicators_for_sector(sector: str) -> list[dict[str, Any]]:
    """Return indicators applicable to a finance sub-sector.

    Examples:
        ``"banking"``, ``"insurance"``, ``"consumer_finance"``,
        ``"mortgage_finance"``, ``"investment_banking"``, ``"asset_management"``.

    Indicators with no ``applicable_sectors`` field are assumed universal.
    """
    target = sector.strip()
    return [
        ind
        for ind in get_all_indicators()
        if not ind.get("applicable_sectors") or target in ind["applicable_sectors"]
    ]


def get_indicators_by_metric_type(metric_type: str) -> list[dict[str, Any]]:
    """Return indicators of a given metric type (``quantitative`` / ``monetary`` / ``rate`` / ``qualitative`` / ``activity``)."""
    target = metric_type.strip()
    return [
        ind
        for ind in get_all_indicators()
        if ind.get("metric_type", "quantitative") == target
    ]
