"""SASB sector-specific scoring — registry + dispatcher.

Covers FN-CF, FN-IN (Financial) and EM-MM, RT-CH, FB-AG (Manufacturing)
codes from esg_scoring_framework.md Sections 3 and 4.
Merges additional codes from data/sasb_standards.json at import time.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import structlog

from app.core.scoring.scorer import score_metric
from app.models.enums import MetricDirection, MetricType
from app.schemas.metric import MetricScoreInput, MetricScoreOutput

logger = structlog.get_logger(__name__)

_DATA_FILE = Path(__file__).resolve().parents[4] / "data" / "sasb_standards.json"


# ---------------------------------------------------------------------------
# Config dataclass
# ---------------------------------------------------------------------------

@dataclass
class SASBMetricConfig:
    code: str
    name: str
    metric_type: MetricType
    pillar: str
    topics: list[str] = field(default_factory=list)
    sector_codes: list[str] = field(default_factory=list)   # SICS codes / sector keys
    direction: MetricDirection = MetricDirection.NEUTRAL
    completeness_criteria: list[str] = field(default_factory=list)
    extraction_keywords: list[str] = field(default_factory=list)
    data_availability: float = 0.5


# ---------------------------------------------------------------------------
# Builder helpers
# ---------------------------------------------------------------------------

def _q(code, name, pillar, topics, sectors, dir=MetricDirection.NEUTRAL, da=0.6, kw=None):
    return SASBMetricConfig(code=code, name=name, metric_type=MetricType.QUANTITATIVE,
                            pillar=pillar, topics=topics, sector_codes=sectors,
                            direction=dir, data_availability=da,
                            extraction_keywords=kw or [])


def _ql(code, name, pillar, topics, sectors, criteria, da=0.5, kw=None):
    return SASBMetricConfig(code=code, name=name, metric_type=MetricType.QUALITATIVE,
                            pillar=pillar, topics=topics, sector_codes=sectors,
                            completeness_criteria=criteria, data_availability=da,
                            extraction_keywords=kw or [])


def _b(code, name, pillar, topics, sectors, da=0.7, kw=None):
    return SASBMetricConfig(code=code, name=name, metric_type=MetricType.BINARY,
                            pillar=pillar, topics=topics, sector_codes=sectors,
                            data_availability=da, extraction_keywords=kw or [])


# ---------------------------------------------------------------------------
# Static registry
# ---------------------------------------------------------------------------

SASB_METRIC_REGISTRY: dict[str, SASBMetricConfig] = {

    # ── FN-CF (Consumer Finance) ─────────────────────────────────────────────
    "FN-CF-230a.1": _q("FN-CF-230a.1", "Data breaches — count and account holders affected",
                       "G", ["FIN-S8"], ["consumer_finance", "financial"],
                       dir=MetricDirection.LOWER_BETTER, da=0.7,
                       kw=["data breach", "account holders affected", "personal data"]),

    "FN-CF-230a.2": _q("FN-CF-230a.2", "Card-related fraud losses",
                       "G", ["FIN-S8"], ["consumer_finance", "financial"],
                       dir=MetricDirection.LOWER_BETTER, da=0.65,
                       kw=["card fraud", "card-not-present", "fraud losses"]),

    "FN-CF-230a.3": _ql("FN-CF-230a.3", "Approach to identifying and managing data security risks",
                        "G", ["FIN-G4"], ["consumer_finance", "financial"],
                        criteria=["risk assessment", "cybersecurity", "encryption",
                                  "third-party", "incident response"], da=0.5,
                        kw=["data security", "cybersecurity approach", "risk management"]),

    "FN-CF-220a.1": _q("FN-CF-220a.1", "Account holders whose data used for secondary purposes",
                       "G", ["FIN-S8"], ["consumer_finance", "financial"],
                       dir=MetricDirection.LOWER_BETTER, da=0.5,
                       kw=["secondary purposes", "account holders", "data sharing"]),

    "FN-CF-220a.2": _q("FN-CF-220a.2", "Monetary losses from customer privacy legal proceedings",
                       "G", ["FIN-S8"], ["consumer_finance", "financial"],
                       dir=MetricDirection.LOWER_BETTER, da=0.55,
                       kw=["privacy losses", "legal proceedings", "regulatory penalty"]),

    "FN-CF-270a.2": _q("FN-CF-270a.2", "Approval rates for credit and pre-paid products",
                       "S", ["FIN-S7"], ["consumer_finance", "financial"],
                       da=0.5, kw=["approval rate", "credit approval", "pre-paid"]),

    "FN-CF-270a.4": _q("FN-CF-270a.4", "Customer complaints filed and % resolved with relief",
                       "S", ["FIN-S7"], ["consumer_finance", "financial"],
                       dir=MetricDirection.LOWER_BETTER, da=0.6,
                       kw=["complaints filed", "monetary relief", "resolution rate"]),

    # ── FN-IN (Insurance) ───────────────────────────────────────────────────
    "FN-IN-410c.1": _q("FN-IN-410c.1", "Financed emissions — absolute (insurance portfolio)",
                       "E", ["FIN-E2"], ["insurance", "financial"],
                       dir=MetricDirection.LOWER_BETTER, da=0.35,
                       kw=["financed emissions", "portfolio emissions", "tCO2e", "PCAF"]),

    "FN-IN-410c.2": _q("FN-IN-410c.2", "Financed emissions — weighted average carbon intensity",
                       "E", ["FIN-E2"], ["insurance", "financial"],
                       dir=MetricDirection.LOWER_BETTER, da=0.3,
                       kw=["carbon intensity", "WACI", "tCO2e per million"]),

    "FN-IN-270a.1": _q("FN-IN-270a.1", "Monetary losses from marketing/communications legal proceedings",
                       "S", ["FIN-S9"], ["insurance", "financial"],
                       dir=MetricDirection.LOWER_BETTER, da=0.5,
                       kw=["marketing losses", "mis-selling", "legal proceedings"]),

    "FN-IN-270a.2": _q("FN-IN-270a.2", "Complaints-to-claims ratio",
                       "S", ["FIN-S9"], ["insurance", "financial"],
                       dir=MetricDirection.LOWER_BETTER, da=0.55,
                       kw=["complaints to claims", "claims ratio", "complaint rate"]),

    # ── EM-MM (Metals & Mining — Manufacturing) ──────────────────────────────
    "EM-MM-110a.1": _q("EM-MM-110a.1", "GHG emissions Scope 1 — mining",
                       "E", ["MFG-E2"], ["manufacturing", "metals_mining"],
                       dir=MetricDirection.LOWER_BETTER, da=0.75,
                       kw=["scope 1", "GHG", "tCO2e", "direct emissions"]),

    "EM-MM-110a.2": _ql("EM-MM-110a.2", "GHG emissions reduction strategy — mining",
                        "E", ["MFG-E2"], ["manufacturing", "metals_mining"],
                        criteria=["reduction target", "initiative", "timeline", "baseline"], da=0.4,
                        kw=["GHG reduction", "climate target", "decarbonisation"]),

    "EM-MM-140a.1": _q("EM-MM-140a.1", "Water withdrawn and recycled — mining",
                       "E", ["MFG-E4"], ["manufacturing", "metals_mining"],
                       dir=MetricDirection.LOWER_BETTER, da=0.6,
                       kw=["water withdrawn", "water recycled", "m3", "water intensity"]),

    "EM-MM-150a.1": _q("EM-MM-150a.1", "Waste generated — tailings and waste rock",
                       "E", ["MFG-E5"], ["manufacturing", "metals_mining"],
                       dir=MetricDirection.LOWER_BETTER, da=0.65,
                       kw=["tailings", "waste rock", "metric tons", "hazardous"]),

    "EM-MM-210a.1": _q("EM-MM-210a.1", "Reportable safety incidents — TRIR",
                       "S", ["MFG-S4"], ["manufacturing", "metals_mining"],
                       dir=MetricDirection.LOWER_BETTER, da=0.8,
                       kw=["TRIR", "recordable incidents", "fatalities", "injury rate"]),

    "EM-MM-210b.1": _q("EM-MM-210b.1", "Fatalities — employees and contractors",
                       "S", ["MFG-S4"], ["manufacturing", "metals_mining"],
                       dir=MetricDirection.LOWER_BETTER, da=0.85,
                       kw=["fatalities", "deaths", "work-related"]),

    "EM-MM-310a.1": _q("EM-MM-310a.1", "Payments to local communities",
                       "S", ["MFG-S7"], ["manufacturing", "metals_mining"],
                       da=0.4, kw=["community payments", "royalties", "local content"]),

    "EM-MM-310a.2": _ql("EM-MM-310a.2", "Community development and relations approach",
                        "S", ["MFG-S7"], ["manufacturing", "metals_mining"],
                        criteria=["community engagement", "grievance mechanism",
                                  "free prior informed consent", "FPIC"], da=0.35),

    # ── RT-CH (Chemicals — Manufacturing) ────────────────────────────────────
    "RT-CH-110a.1": _q("RT-CH-110a.1", "Scope 1 GHG emissions — chemicals",
                       "E", ["MFG-E2"], ["manufacturing", "chemicals"],
                       dir=MetricDirection.LOWER_BETTER, da=0.75,
                       kw=["scope 1", "GHG", "tCO2e", "chemical process"]),

    "RT-CH-150a.1": _q("RT-CH-150a.1", "Hazardous waste — generated and disposed",
                       "E", ["MFG-E5"], ["manufacturing", "chemicals"],
                       dir=MetricDirection.LOWER_BETTER, da=0.7,
                       kw=["hazardous waste", "metric tons", "disposal"]),

    "RT-CH-150a.2": _q("RT-CH-150a.2", "Accidental releases to the environment",
                       "E", ["MFG-E5"], ["manufacturing", "chemicals"],
                       dir=MetricDirection.LOWER_BETTER, da=0.6,
                       kw=["spills", "releases", "reportable", "accidental"]),

    "RT-CH-320a.1": _q("RT-CH-320a.1", "Total recordable incident rate — chemicals",
                       "S", ["MFG-S4"], ["manufacturing", "chemicals"],
                       dir=MetricDirection.LOWER_BETTER, da=0.8,
                       kw=["TRIR", "recordable incidents", "process safety"]),

    # ── FB-AG (Food and Beverage / Agribusiness — Manufacturing) ────────────
    "FB-AG-160a.1": _q("FB-AG-160a.1", "Freshwater withdrawn in water-stressed areas",
                       "E", ["MFG-E4"], ["manufacturing", "food_beverage"],
                       dir=MetricDirection.LOWER_BETTER, da=0.55,
                       kw=["freshwater", "water-stressed", "withdrawal", "m3"]),

    "FB-AG-430a.1": _q("FB-AG-430a.1", "Work-related fatalities and injury rate",
                       "S", ["MFG-S4"], ["manufacturing", "food_beverage"],
                       dir=MetricDirection.LOWER_BETTER, da=0.75,
                       kw=["fatalities", "injury rate", "TRIR", "work-related"]),
}

# Sector → list of applicable SASB codes
_SECTOR_CODE_MAP: dict[str, list[str]] = {
    "financial": [
        "FN-CF-230a.1", "FN-CF-230a.2", "FN-CF-230a.3",
        "FN-CF-220a.1", "FN-CF-220a.2",
        "FN-CF-270a.2", "FN-CF-270a.4",
        "FN-IN-410c.1", "FN-IN-410c.2",
        "FN-IN-270a.1", "FN-IN-270a.2",
    ],
    "manufacturing": [
        "EM-MM-110a.1", "EM-MM-110a.2", "EM-MM-140a.1",
        "EM-MM-150a.1", "EM-MM-210a.1", "EM-MM-210b.1",
        "EM-MM-310a.1", "EM-MM-310a.2",
        "RT-CH-110a.1", "RT-CH-150a.1", "RT-CH-150a.2", "RT-CH-320a.1",
        "FB-AG-160a.1", "FB-AG-430a.1",
    ],
}


# ---------------------------------------------------------------------------
# JSON merge — add entries from sasb_standards.json not already in registry
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _load_sasb_standards() -> dict:
    try:
        with open(_DATA_FILE) as f:
            return json.load(f)
    except FileNotFoundError:
        logger.warning("sasb_scorer.file_missing", path=str(_DATA_FILE))
        return {}


def _merge_json() -> None:
    standards = _load_sasb_standards()
    # Mirrors extractor._METRIC_TYPE_MAP and gri_scorer._merge_json_into_registry._MT_MAP.
    # monetary/rate/activity all score as QUANTITATIVE; keep all three maps in sync.
    _MT_MAP = {
        "quantitative": MetricType.QUANTITATIVE,
        "monetary":     MetricType.QUANTITATIVE,
        "rate":         MetricType.QUANTITATIVE,
        "qualitative":  MetricType.QUALITATIVE,
        "activity":     MetricType.QUANTITATIVE,
        "binary":       MetricType.BINARY,
    }
    for sector_key, sector_data in standards.get("sectors", {}).items():
        for code, weight in sector_data.get("material_topics", {}).items():
            if code not in SASB_METRIC_REGISTRY:
                SASB_METRIC_REGISTRY[code] = SASBMetricConfig(
                    code=code,
                    name=code,
                    metric_type=MetricType.QUANTITATIVE,
                    pillar="G",
                    sector_codes=[sector_key],
                    data_availability=weight if isinstance(weight, float) else 0.5,
                )


_merge_json()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_sasb_codes_for_sector(sector: str) -> list[str]:
    """Return relevant SASB metric codes for a sector.

    Falls back to scanning the registry by sector_codes if the sector is not
    in the pre-built map.
    """
    key = sector.lower()
    if key in _SECTOR_CODE_MAP:
        return list(_SECTOR_CODE_MAP[key])
    return [
        code for code, cfg in SASB_METRIC_REGISTRY.items()
        if key in cfg.sector_codes
    ]


def score_sasb_metric(
    sasb_code: str,
    extracted_data: dict,
    sector: str = "financial",
    weight_in_topic: float = 1.0,
) -> MetricScoreOutput:
    """Score one SASB metric given its extracted data.

    Args:
        sasb_code:      e.g. 'FN-CF-230a.1'
        extracted_data: Keys: 'value', 'text', 'benchmark', 'confidence'
        sector:         'financial' | 'manufacturing'
        weight_in_topic: passed through to MetricScoreOutput

    Returns:
        MetricScoreOutput
    """
    cfg = SASB_METRIC_REGISTRY.get(sasb_code)
    if cfg is None:
        logger.warning("score_sasb_metric.unknown_code", code=sasb_code)
        return MetricScoreOutput(
            metric_code=sasb_code,
            metric_type=MetricType.QUANTITATIVE,
            raw_score=0.0,
            weight_in_topic=weight_in_topic,
            weighted_contribution=0.0,
            fra_required=False,
            scoring_notes=f"Unknown SASB code '{sasb_code}' -- scored 0.0",
        )

    inp = MetricScoreInput(
        metric_code=cfg.code,
        metric_type=cfg.metric_type,
        extracted_value=extracted_data.get("value"),
        extracted_text=extracted_data.get("text"),
        benchmark=extracted_data.get("benchmark"),
        direction=cfg.direction,
        completeness_criteria=cfg.completeness_criteria,
        weight_in_topic=weight_in_topic,
        fra_required=False,
    )
    return score_metric(inp)


def score_all_sasb_for_document(
    extracted_metrics: list[dict],
    sector: str = "financial",
) -> dict[str, MetricScoreOutput]:
    """Score every extracted metric that carries a SASB code.

    Args:
        extracted_metrics: List of dicts each with at minimum 'sasb_code'.
                           Optional keys: 'value', 'text', 'benchmark',
                           'weight_in_topic'.
        sector:            'financial' | 'manufacturing'

    Returns:
        Dict mapping sasb_code -> MetricScoreOutput.
    """
    results: dict[str, MetricScoreOutput] = {}
    for m in extracted_metrics:
        code = m.get("sasb_code") or m.get("code")
        if not code:
            continue
        results[code] = score_sasb_metric(
            sasb_code=code,
            extracted_data=m,
            sector=sector,
            weight_in_topic=m.get("weight_in_topic", 1.0),
        )
    logger.info("score_all_sasb_for_document.done", sector=sector, n_scored=len(results))
    return results


# ---------------------------------------------------------------------------
# Legacy shim — preserved for backward-compat with scorer.py:score_report()
# ---------------------------------------------------------------------------

def compute_sasb_score(metrics: list, sector: str) -> float:
    """Legacy: 0-100 SASB coverage weighted by materiality scores from JSON.

    Deprecated — use score_all_sasb_for_document() for weight-aware scoring.
    """
    try:
        standards = _load_sasb_standards()
    except FileNotFoundError:
        logger.warning("sasb_scorer.file_missing", path=str(_DATA_FILE))
        return 0.0

    sector_data = (
        standards.get("sectors", {}).get(sector)
        or standards.get("sectors", {}).get("default", {})
    )
    material_codes: dict[str, float] = sector_data.get("material_topics", {})
    if not material_codes:
        return 0.0

    metric_map = {m.sasb_code: m for m in metrics if m.sasb_code}
    total_weight = sum(material_codes.values())
    if total_weight == 0:
        return 0.0

    weighted_score = 0.0
    for code, weight in material_codes.items():
        metric = metric_map.get(code)
        if metric is not None and metric.confidence > 0:
            weighted_score += weight * metric.confidence

    return round(weighted_score / total_weight * 100, 1)
