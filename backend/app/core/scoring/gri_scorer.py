"""GRI indicator scoring — registry + per-indicator dispatcher.

Defines GRIIndicatorConfig, builds GRI_INDICATOR_REGISTRY from spec
Sections 3 & 4, merges additional data from data/gri_indicators.json,
and exposes score_gri_indicator() + score_all_gri_for_document().
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import structlog

from app.core.scoring.scorer import (
    score_binary,
    score_metric,
    score_qualitative,
    score_quantitative,
    score_q_plus_ql,
)
from app.models.enums import MetricDirection, MetricType
from app.schemas.metric import MetricScoreInput, MetricScoreOutput

logger = structlog.get_logger(__name__)

_JSON_PATH = Path(__file__).resolve().parents[4] / "data" / "gri_indicators.json"


# ---------------------------------------------------------------------------
# Config dataclass
# ---------------------------------------------------------------------------

@dataclass
class GRIIndicatorConfig:
    code: str
    name: str
    metric_type: MetricType
    pillar: str                          # "E" | "S" | "G"
    direction: MetricDirection = MetricDirection.NEUTRAL
    topics: list[str] = field(default_factory=list)
    completeness_criteria: list[str] = field(default_factory=list)
    extraction_keywords: list[str] = field(default_factory=list)
    fra_kpi_codes: list[str] = field(default_factory=list)
    data_availability: float = 0.5
    sectors: list[str] = field(default_factory=lambda: ["financial", "manufacturing"])


# ---------------------------------------------------------------------------
# Static registry  (spec §3 and §4)
# ---------------------------------------------------------------------------

def _q(code, name, pillar, topics, fra=None, dir=MetricDirection.NEUTRAL,
       da=0.7, kw=None, sectors=None):
    return GRIIndicatorConfig(
        code=code, name=name, metric_type=MetricType.QUANTITATIVE,
        pillar=pillar, direction=dir, topics=topics or [],
        fra_kpi_codes=[fra] if fra else [],
        data_availability=da,
        extraction_keywords=kw or [],
        sectors=sectors or ["financial", "manufacturing"],
    )


def _ql(code, name, pillar, topics, criteria, fra=None, da=0.5, kw=None, sectors=None):
    return GRIIndicatorConfig(
        code=code, name=name, metric_type=MetricType.QUALITATIVE,
        pillar=pillar, topics=topics or [],
        completeness_criteria=criteria,
        fra_kpi_codes=[fra] if fra else [],
        data_availability=da,
        extraction_keywords=kw or [],
        sectors=sectors or ["financial", "manufacturing"],
    )


def _b(code, name, pillar, topics, fra=None, da=0.8, kw=None, sectors=None):
    return GRIIndicatorConfig(
        code=code, name=name, metric_type=MetricType.BINARY,
        pillar=pillar, topics=topics or [],
        fra_kpi_codes=[fra] if fra else [],
        data_availability=da,
        extraction_keywords=kw or [],
        sectors=sectors or ["financial", "manufacturing"],
    )


GRI_INDICATOR_REGISTRY: dict[str, GRIIndicatorConfig] = {

    # ── Energy (GRI 302) ────────────────────────────────────────────────────
    "GRI 302-1": _q("GRI 302-1", "Energy consumption within the organization",
                    "E", ["FIN-E3", "MFG-E3"], fra="E3", da=0.9,
                    kw=["energy consumption", "GJ", "MWh", "electricity", "fuel"]),
    "GRI 302-3": _q("GRI 302-3", "Energy intensity",
                    "E", ["FIN-E3", "MFG-E3"], dir=MetricDirection.LOWER_BETTER, da=0.6,
                    kw=["energy intensity", "GJ per", "energy ratio"]),
    "GRI 302-4": _ql("GRI 302-4", "Reduction of energy consumption",
                     "E", ["MFG-E3"],
                     ["reduction", "energy efficiency", "target", "initiative"], da=0.5,
                     sectors=["manufacturing"]),

    # ── Water (GRI 303) ─────────────────────────────────────────────────────
    "GRI 303-1": _ql("GRI 303-1", "Water withdrawal by source",
                     "E", ["FIN-E4", "MFG-E4"], fra="E4",
                     criteria=["withdrawal", "source", "municipal", "groundwater"], da=0.5),
    "GRI 303-3": _q("GRI 303-3", "Water withdrawal",
                    "E", ["MFG-E4"], fra="E4", da=0.6,
                    kw=["water withdrawal", "m3", "cubic metres"],
                    sectors=["manufacturing"]),
    "GRI 303-4": _q("GRI 303-4", "Water discharge",
                    "E", ["MFG-E4"], da=0.5,
                    kw=["water discharge", "effluent", "m3"],
                    sectors=["manufacturing"]),
    "GRI 303-5": _q("GRI 303-5", "Water consumption",
                    "E", ["FIN-E4", "MFG-E4"], fra="E4", da=0.6,
                    kw=["water consumption", "water consumed", "m3"]),

    # ── Biodiversity (GRI 304) — Manufacturing only ─────────────────────────
    "GRI 304-1": _ql("GRI 304-1", "Sites in or near protected areas",
                     "E", ["MFG-E6"],
                     ["protected area", "biodiversity", "IUCN", "habitat"], da=0.3,
                     sectors=["manufacturing"]),
    "GRI 304-2": _ql("GRI 304-2", "Significant impacts on biodiversity",
                     "E", ["MFG-E6"],
                     ["species impacted", "habitat change", "mitigation"], da=0.3,
                     sectors=["manufacturing"]),

    # ── Emissions (GRI 305) ─────────────────────────────────────────────────
    "GRI 305-1": _q("GRI 305-1", "Direct (Scope 1) GHG emissions",
                    "E", ["FIN-E2", "MFG-E2"], fra="E2",
                    dir=MetricDirection.LOWER_BETTER, da=0.9,
                    kw=["scope 1", "direct emissions", "GHG", "CO2e", "tCO2e"]),
    "GRI 305-2": _q("GRI 305-2", "Energy indirect (Scope 2) GHG emissions",
                    "E", ["FIN-E2", "MFG-E2"], fra="E2",
                    dir=MetricDirection.LOWER_BETTER, da=0.85,
                    kw=["scope 2", "indirect emissions", "electricity", "tCO2e"]),
    "GRI 305-3": _q("GRI 305-3", "Other indirect (Scope 3) GHG emissions",
                    "E", ["FIN-E2", "MFG-E2"],
                    dir=MetricDirection.LOWER_BETTER, da=0.3,
                    kw=["scope 3", "financed emissions", "value chain", "tCO2e"]),
    "GRI 305-4": _q("GRI 305-4", "GHG emissions intensity",
                    "E", ["FIN-E2", "MFG-E2"],
                    dir=MetricDirection.LOWER_BETTER, da=0.6,
                    kw=["GHG intensity", "emissions intensity", "tCO2e per"]),
    "GRI 305-5": _ql("GRI 305-5", "Reduction of GHG emissions",
                     "E", ["MFG-E2"],
                     ["reduction target", "initiative", "timeline", "baseline year"],
                     da=0.5, sectors=["manufacturing"]),

    # ── Waste (GRI 306) ─────────────────────────────────────────────────────
    "GRI 306-1": _ql("GRI 306-1", "Waste generation and significant waste-related impacts",
                     "E", ["FIN-E5", "MFG-E5"], fra="E5",
                     criteria=["waste", "impact", "hazardous", "disposal"], da=0.5),
    "GRI 306-2": _ql("GRI 306-2", "Management of significant waste-related impacts",
                     "E", ["FIN-E5", "MFG-E5"],
                     criteria=["waste management", "circular economy", "reuse", "reduction"], da=0.4),
    "GRI 306-3": _q("GRI 306-3", "Waste generated",
                    "E", ["FIN-E5", "MFG-E5"], fra="E5", da=0.7,
                    kw=["waste generated", "metric tons", "tonnes", "hazardous waste"]),

    # ── Employment (GRI 401) ─────────────────────────────────────────────────
    "GRI 401-1": _q("GRI 401-1", "New employee hires and turnover",
                    "S", ["FIN-S2", "MFG-S2"], fra="S2", da=0.85,
                    kw=["new hires", "turnover", "headcount", "employees"]),
    "GRI 401-3": _q("GRI 401-3", "Parental leave",
                    "S", ["FIN-S2", "MFG-S2"], da=0.5,
                    kw=["parental leave", "maternity", "paternity"]),

    # ── OHS (GRI 403) ────────────────────────────────────────────────────────
    "GRI 403-1": _b("GRI 403-1", "OHS management system",
                    "S", ["FIN-S4", "MFG-S4"], fra="S4", da=0.7,
                    kw=["OHS", "health and safety", "management system", "ISO 45001"]),
    "GRI 403-4": _ql("GRI 403-4", "Worker participation in OHS",
                     "S", ["MFG-S4"],
                     ["worker committee", "consultation", "joint OHS committee"], da=0.4,
                     sectors=["manufacturing"]),
    "GRI 403-5": _q("GRI 403-5", "Worker training on OHS",
                    "S", ["FIN-S4", "MFG-S4"], fra="S4", da=0.6,
                    kw=["safety training", "OHS training", "health training", "hours"]),
    "GRI 403-6": _q("GRI 403-6", "Promotion of worker health",
                    "S", ["FIN-S4"], da=0.4,
                    kw=["health promotion", "wellness", "employee health"]),
    "GRI 403-8": _q("GRI 403-8", "Workers covered by OHS management system",
                    "S", ["FIN-S4", "MFG-S4"], da=0.5,
                    kw=["OHS coverage", "workers covered", "percentage"]),
    "GRI 403-9": _q("GRI 403-9", "Work-related injuries",
                    "S", ["FIN-S4", "MFG-S4"], fra="S4", da=0.75,
                    dir=MetricDirection.LOWER_BETTER,
                    kw=["fatalities", "injuries", "TRIR", "incident rate", "recordable"]),
    "GRI 403-10": _q("GRI 403-10", "Work-related ill health",
                     "S", ["MFG-S4"], dir=MetricDirection.LOWER_BETTER, da=0.5,
                     kw=["ill health", "occupational disease", "work-related illness"],
                     sectors=["manufacturing"]),

    # ── Training (GRI 404) ────────────────────────────────────────────────────
    "GRI 404-1": _q("GRI 404-1", "Average training hours per employee",
                    "S", ["MFG-S8"], da=0.7,
                    kw=["training hours", "average hours", "per employee"],
                    sectors=["manufacturing"]),
    "GRI 404-2": _ql("GRI 404-2", "Programs for upgrading employee skills",
                     "S", ["MFG-S8"],
                     ["upskilling", "training program", "career development", "learning"],
                     da=0.5, sectors=["manufacturing"]),
    "GRI 404-3": _q("GRI 404-3", "Employees receiving performance reviews",
                    "S", ["MFG-S8"], da=0.6,
                    kw=["performance review", "appraisal", "percentage employees"],
                    sectors=["manufacturing"]),

    # ── Diversity (GRI 405) ──────────────────────────────────────────────────
    "GRI 405-1": _q("GRI 405-1", "Diversity of governance bodies and employees",
                    "S", ["FIN-S1", "FIN-G1", "MFG-S1", "MFG-G1"], fra="S1", da=0.9,
                    kw=["board diversity", "gender", "female", "male", "board seats"]),
    "GRI 405-2": _q("GRI 405-2", "Ratio of basic salary by gender",
                    "S", ["FIN-S1", "MFG-S1"], fra="S1", da=0.6,
                    kw=["pay ratio", "salary ratio", "gender pay", "compensation"]),

    # ── Non-discrimination (GRI 406) ─────────────────────────────────────────
    "GRI 406-1": _q("GRI 406-1", "Incidents of discrimination",
                    "S", ["FIN-S3", "MFG-S3"], fra="S3", da=0.7,
                    kw=["discrimination", "incidents", "complaints", "corrective"]),

    # ── Freedom of association (GRI 407) ────────────────────────────────────
    "GRI 407-1": _b("GRI 407-1", "Operations with freedom of association risk",
                    "S", ["FIN-S6", "MFG-S6"], fra="S6", da=0.4,
                    kw=["freedom of association", "collective bargaining", "ILO"]),

    # ── Child / forced labor (GRI 408 / 409) ────────────────────────────────
    "GRI 408-1": _b("GRI 408-1", "Operations with child labor risk",
                    "S", ["FIN-S5", "MFG-S5"], fra="S5", da=0.6,
                    kw=["child labor", "child labour", "minimum age"]),
    "GRI 409-1": _b("GRI 409-1", "Operations with forced labor risk",
                    "S", ["FIN-S5", "MFG-S5"], fra="S5", da=0.5,
                    kw=["forced labor", "forced labour", "modern slavery"]),

    # ── Local communities (GRI 413) — Manufacturing ──────────────────────────
    "GRI 413-1": _ql("GRI 413-1", "Operations with community engagement",
                     "S", ["MFG-S7"],
                     ["community engagement", "stakeholder", "grievance mechanism",
                      "impact assessment"], da=0.4, sectors=["manufacturing"]),
    "GRI 413-2": _q("GRI 413-2", "Operations with negative community impacts",
                    "S", ["MFG-S7"], da=0.4,
                    kw=["negative impact", "community", "resettlement"],
                    sectors=["manufacturing"]),

    # ── Supplier social (GRI 414) ────────────────────────────────────────────
    "GRI 414-1": _q("GRI 414-1", "Supplier screening for social criteria",
                    "S", ["FIN-S6", "MFG-S6", "MFG-G4"], da=0.4,
                    kw=["supplier screening", "social audit", "labor rights"]),

    # ── Political contributions (GRI 415) ────────────────────────────────────
    "GRI 415-1": _q("GRI 415-1", "Political contributions",
                    "G", ["FIN-G5", "MFG-G5"], da=0.5,
                    kw=["political contributions", "lobbying", "public policy"]),

    # ── Customer privacy (GRI 418) ───────────────────────────────────────────
    "GRI 418-1": _q("GRI 418-1", "Substantiated privacy complaints",
                    "G", ["FIN-S8"], da=0.7,
                    kw=["data breach", "privacy complaints", "customer data",
                        "leaks", "PDPL"],
                    sectors=["financial"]),

    # ── Anti-corruption (GRI 205) ─────────────────────────────────────────────
    "GRI 205-1": _q("GRI 205-1", "Operations assessed for corruption risks",
                    "G", ["FIN-G2", "MFG-G2"], fra="G2", da=0.5,
                    kw=["corruption risk", "operations assessed", "anti-corruption"]),
    "GRI 205-2": _b("GRI 205-2", "Anti-corruption training",
                    "G", ["FIN-G2", "MFG-G2"], fra="G2", da=0.6,
                    kw=["anti-corruption training", "compliance training"]),
    "GRI 205-3": _q("GRI 205-3", "Confirmed incidents of corruption",
                    "G", ["FIN-G2", "MFG-G2"], fra="G2", da=0.65,
                    kw=["confirmed incidents", "corruption", "financial crime"]),

    # ── Ethics / assurance (GRI 102) ────────────────────────────────────────
    "GRI 102-17": _ql("GRI 102-17", "Mechanisms for advice and ethical concerns",
                      "G", ["FIN-G3", "MFG-G3"], fra="G3",
                      criteria=["whistleblower", "ethics hotline", "reporting mechanism",
                                "anonymity"], da=0.6,
                      kw=["whistleblower", "ethics hotline", "code of conduct"]),
    "GRI 102-56": _ql("GRI 102-56", "External assurance",
                      "G", ["FIN-G6", "MFG-G6"], fra="G6",
                      criteria=["assurance standard", "independent assurer",
                                "ISAE 3000", "scope"], da=0.7,
                      kw=["external assurance", "third-party assurance", "ISAE"]),

    # ── GRI Banking Sector codes ─────────────────────────────────────────────
    "GRI-XX-5.2": _ql("GRI-XX-5.2", "Identified underserved customer groups",
                      "S", ["FIN-S7"],
                      ["customer groups", "underserved", "selection process", "methodology"],
                      da=0.4, sectors=["financial"]),
    "GRI-XX-5.3": GRIIndicatorConfig(
        code="GRI-XX-5.3", name="Products for underserved groups",
        metric_type=MetricType.Q_PLUS_QL, pillar="S",
        topics=["FIN-S7"],
        completeness_criteria=["underserved", "product", "financial education"],
        data_availability=0.4, sectors=["financial"],
    ),
    "GRI-XX-5.7": _q("GRI-XX-5.7", "Complaints on financial health & inclusion",
                     "S", ["FIN-S7"], da=0.5,
                     kw=["financial inclusion complaints", "inclusion"],
                     sectors=["financial"]),
    "GRI-XX-5.8": _q("GRI-XX-5.8", "Banking access points in disadvantaged areas",
                     "S", ["FIN-S7"], da=0.5,
                     kw=["access points", "branch", "ATM", "disadvantaged", "rural"],
                     sectors=["financial"]),
    "GRI-XX-6.1": _ql("GRI-XX-6.1", "Cybersecurity approach",
                      "G", ["FIN-G4"],
                      ["cybersecurity", "encryption", "third-party", "data governance",
                       "PDPL"], da=0.5, sectors=["financial"]),
    "GRI-XX-6.2": _q("GRI-XX-6.2", "Customer data leaks / complaints",
                     "G", ["FIN-S8"], da=0.6,
                     kw=["data leaks", "privacy complaints", "customers affected"],
                     sectors=["financial"]),
    "GRI-XX-7.2": _q("GRI-XX-7.2", "Non-compliance — product information",
                     "S", ["FIN-S9"], da=0.5,
                     kw=["non-compliance", "product labeling", "marketing"],
                     sectors=["financial"]),
    "GRI-XX-7.3": _q("GRI-XX-7.3", "Non-compliance — marketing communications",
                     "S", ["FIN-S9"], da=0.5,
                     kw=["marketing non-compliance", "advertising"],
                     sectors=["financial"]),
    "GRI-XX-19.5": _q("GRI-XX-19.5", "Customer funds lost to financial crime",
                      "G", ["FIN-G2"], da=0.5,
                      kw=["funds lost", "financial crime", "fraud losses"],
                      sectors=["financial"]),

    # ── FRA composite ────────────────────────────────────────────────────────
    "FRA-36": _q("FRA-36", "Total GHG emissions (Scope 1+2) — FRA",
                 "E", ["FIN-E2"], fra="E2", da=0.9,
                 dir=MetricDirection.LOWER_BETTER,
                 kw=["scope 1", "scope 2", "total GHG", "tCO2e", "FRA-36"]),

    # ── Economic (GRI 201) ───────────────────────────────────────────────────
    "GRI 201-1": _q("GRI 201-1", "Direct economic value generated and distributed",
                    "G", ["MFG-S7"], da=0.7,
                    kw=["economic value", "wages", "taxes", "community investment"]),
}


# ---------------------------------------------------------------------------
# JSON merge — adds any indicator from gri_indicators.json not already
# present in the static registry (preserves static definitions as authoritative)
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _load_json_indicators() -> list[dict]:
    try:
        with open(_JSON_PATH) as f:
            return json.load(f).get("indicators", [])
    except FileNotFoundError:
        logger.warning("gri_scorer.json_missing", path=str(_JSON_PATH))
        return []


def _merge_json_into_registry() -> None:
    # gri_indicators.json metric_type shapes → scoring MetricType selector.
    # Mirrors extractor._METRIC_TYPE_MAP (monetary/rate/activity all score as
    # QUANTITATIVE). Keep both maps in sync when adding new extraction shapes.
    _MT_MAP = {
        "quantitative": MetricType.QUANTITATIVE,
        "monetary":     MetricType.QUANTITATIVE,
        "rate":         MetricType.QUANTITATIVE,
        "qualitative":  MetricType.QUALITATIVE,
        "activity":     MetricType.QUANTITATIVE,
        "binary":       MetricType.BINARY,
    }
    for ind in _load_json_indicators():
        code = ind.get("code", "")
        if not code or code in GRI_INDICATOR_REGISTRY:
            continue
        mt = _MT_MAP.get(ind.get("metric_type", "quantitative"), MetricType.QUANTITATIVE)
        GRI_INDICATOR_REGISTRY[code] = GRIIndicatorConfig(
            code=code,
            name=str(ind.get("name") or code),
            metric_type=mt,
            pillar=str(ind.get("pillar") or "G"),
            topics=[],
            fra_kpi_codes=[ind["fra_code"]] if ind.get("fra_code") else [],
            data_availability=0.5,
            extraction_keywords=str(ind.get("extraction_prompt") or "").split()[:8],
        )


_merge_json_into_registry()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def score_gri_indicator(
    indicator_code: str,
    extracted_data: dict,
    sector: str = "financial",
    weight_in_topic: float = 1.0,
) -> MetricScoreOutput:
    """Score one GRI indicator given its extracted data dict.

    Args:
        indicator_code:  e.g. 'GRI 305-1'
        extracted_data:  Keys used:
                           'value'      – numeric/bool/str for BINARY/QUANTITATIVE
                           'text'       – narrative string for QUALITATIVE/Q_PLUS_QL
                           'benchmark'  – optional float for Stage 2 scoring
                           'confidence' – optional float, merged into scoring_notes
        sector:          'financial' | 'manufacturing'
        weight_in_topic: fractional weight (passed through to MetricScoreOutput)

    Returns:
        MetricScoreOutput
    """
    cfg = GRI_INDICATOR_REGISTRY.get(indicator_code)
    if cfg is None:
        logger.warning("score_gri_indicator.unknown_code", code=indicator_code)
        return MetricScoreOutput(
            metric_code=indicator_code,
            metric_type=MetricType.QUANTITATIVE,
            raw_score=0.0,
            weight_in_topic=weight_in_topic,
            weighted_contribution=0.0,
            fra_required=False,
            scoring_notes=f"Unknown indicator '{indicator_code}' — scored 0.0",
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
        fra_required=bool(cfg.fra_kpi_codes),
    )
    return score_metric(inp)


def score_all_gri_for_document(
    extracted_metrics: list[dict],
    sector: str = "financial",
) -> dict[str, MetricScoreOutput]:
    """Score every extracted metric that carries a GRI code.

    Args:
        extracted_metrics: List of dicts each with at minimum 'gri_code'.
                           Other optional keys: 'value', 'text', 'benchmark',
                           'confidence', 'weight_in_topic'.
        sector:            'financial' | 'manufacturing'

    Returns:
        Dict mapping gri_code → MetricScoreOutput.
        Codes not in GRI_INDICATOR_REGISTRY are scored 0.0 with a warning note.
    """
    results: dict[str, MetricScoreOutput] = {}
    for m in extracted_metrics:
        code = m.get("gri_code") or m.get("code")
        if not code:
            continue
        results[code] = score_gri_indicator(
            indicator_code=code,
            extracted_data=m,
            sector=sector,
            weight_in_topic=m.get("weight_in_topic", 1.0),
        )
    logger.info(
        "score_all_gri_for_document.done",
        sector=sector,
        n_scored=len(results),
    )
    return results


# ---------------------------------------------------------------------------
# Legacy shim — preserved for backward-compat with existing pipeline
# ---------------------------------------------------------------------------

def compute_gri_score(metrics: list, indicator_codes: list[str] | None = None) -> float:
    """Legacy: GRI completeness as 0-100 (approved/extracted count / total).

    Deprecated — use score_all_gri_for_document() for weight-aware scoring.
    """
    from app.core.gri.indicators import get_all_indicators
    from app.models.enums import MetricStatus

    all_indicators = get_all_indicators()
    if indicator_codes is not None:
        all_indicators = [i for i in all_indicators if i["code"] in set(indicator_codes)]
    if not all_indicators:
        return 0.0

    approved_or_extracted = {MetricStatus.approved, MetricStatus.extracted}
    metric_map = {m.gri_code: m for m in metrics}

    covered = sum(
        1 for ind in all_indicators
        if ind["code"].startswith("GRI")
        and metric_map.get(ind["code"]) is not None
        and metric_map[ind["code"]].status in approved_or_extracted
    )
    gri_total = sum(1 for ind in all_indicators if ind["code"].startswith("GRI"))
    return round(covered / gri_total * 100, 1) if gri_total else 0.0
