"""Weight Brain — single source of truth for all ESG scoring weights.

Spec references:
  Pillar weights     → Sections 3.1 (Financial), 4.1 (Manufacturing)
  Topic weights      → Sections 3.2-3.4, 4.2-4.4
  Metric weights     → metric tables within each topic section
  Derivation engine  → Section 9
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Optional

import structlog

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _N(d: dict[str, float]) -> dict[str, float]:
    """Normalise a weight dict so values sum to 1.0."""
    total = sum(d.values())
    if total == 0:
        raise ValueError("Cannot normalise: all weights are zero.")
    return {k: round(v / total, 6) for k, v in d.items()}


# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------

@dataclass
class SectorWeightRegistry:
    """Complete weight registry for one sector."""

    sector: str
    pillar_weights: dict[str, float]
    topic_weights: dict[str, dict[str, float]]   # pillar → {topic_id: weight}
    metric_weights: dict[str, dict[str, float]]  # topic_id → {metric_code: weight}
    fra_topic_map: dict[str, str]                # topic_id → FRA KPI code
    fra_mandatory_kpis: list[str]
    stage2_topics: list[str]                     # topics with no FRA Stage 1 KPI


# ---------------------------------------------------------------------------
# FINANCIAL SECTOR WEIGHT REGISTRY  (Spec §3.1 – §3.4)
# ---------------------------------------------------------------------------

_FIN_PILLAR: dict[str, float] = {"E": 0.25, "S": 0.40, "G": 0.35}

_FIN_TOPIC: dict[str, dict[str, float]] = {
    "E": {"FIN-E1": 0.30, "FIN-E2": 0.25, "FIN-E3": 0.20,
          "FIN-E4": 0.15, "FIN-E5": 0.10},
    "S": {"FIN-S1": 0.12, "FIN-S2": 0.08, "FIN-S3": 0.08,
          "FIN-S4": 0.08, "FIN-S5": 0.06, "FIN-S6": 0.06,
          "FIN-S7": 0.22, "FIN-S8": 0.18, "FIN-S9": 0.12},
    "G": {"FIN-G1": 0.15, "FIN-G2": 0.20, "FIN-G3": 0.12,
          "FIN-G4": 0.18, "FIN-G5": 0.20, "FIN-G6": 0.15},
}

# Metric weights — raw spec values normalised where sum ≠ 1.0
# FIN-E1 raw sum = 1.30 → normalised
_FIN_METRIC: dict[str, dict[str, float]] = {
    "FIN-E1": _N({"FRA-E1.1": 0.35, "FRA-E1.2": 0.30, "FRA-E1.3": 0.30,
                  "FRA-E1.4": 0.20, "FRA-E1.5": 0.10, "FRA-E1.6": 0.05}),
    "FIN-E2": {"FRA-E2":         0.35, "FN-IN-410c.1": 0.35,
               "FN-IN-410c.2":   0.20, "FN-IN-410c.4": 0.10},
    "FIN-E3": {"FRA-E3-energy":  0.50, "FRA-E3-renew":  0.30,
               "FRA-E3-saved":   0.20},
    "FIN-E4": {"FRA-E4-consumed": 0.60, "FRA-E4-reclaimed": 0.40},
    "FIN-E5": {"FRA-E5-waste":   1.00},
    # S1 raw sum = 135 → normalised
    "FIN-S1": _N({"FRA-S1-headcount": 0.30, "FRA-S1-entry":   0.35,
                  "FRA-S1-senior":    0.35, "FRA-S1-payratio": 0.35}),
    "FIN-S2": {"FRA-S2-fulltime":  0.40, "FRA-S2-parttime": 0.30,
               "FRA-S2-contract":  0.30},
    "FIN-S3": {"FRA-S3-policy":   0.50, "GRI-406-1":       0.30,
               "GRI-405-1-gov":   0.20},
    "FIN-S4": {"FRA-S4-ohs":      0.25, "FRA-S4-injury":   0.35,
               "FRA-S4-training": 0.25, "GRI-403-8":       0.15},
    "FIN-S5": {"FRA-S5-policy":   0.50, "FRA-S5-supplier": 0.50},
    "FIN-S6": {"FRA-S6-ilo":      0.60, "GRI-414-1":       0.40},
    "FIN-S7": {"GRI-XX-5.2":  0.18, "GRI-XX-5.3":  0.18,
               "GRI-XX-5.7":  0.16, "FN-CF-270a.4": 0.14,
               "GRI-XX-5.5":  0.12, "GRI-XX-5.8":   0.12,
               "FN-CF-270a.2": 0.10},
    "FIN-S8": {"FN-CF-230a.1": 0.32, "GRI-418-1":    0.28,
               "FN-CF-230a.2": 0.18, "FN-CF-220a.1": 0.14,
               "FN-CF-220a.2": 0.08},
    "FIN-S9": {"FN-IN-270a.1": 0.35, "GRI-417-2":    0.25,
               "FN-IN-270a.2": 0.20, "GRI-417-3":    0.20},
    "FIN-G1": {"FRA-G1-board":    0.40, "FRA-G1-committee": 0.30,
               "GRI-405-1-qual":  0.30},
    "FIN-G2": {"FRA-G2-code":     0.25, "GRI-205-3":  0.35,
               "GRI-XX-19.5":    0.25, "GRI-205-1":   0.15},
    "FIN-G3": {"FRA-G3-ethics":   0.60, "GRI-102-17": 0.40},
    "FIN-G4": {"FRA-G4-pdpl":     0.45, "GRI-XX-6.1": 0.35,
               "FN-CF-230a.3":   0.20},
    "FIN-G5": {"FRA-G5-report":   0.25, "FRA-G5-sdg":  0.20,
               "FRA-G5-csr":     0.20, "FRA-G5-ppp":   0.15,
               "GRI-415-1":      0.20},
    "FIN-G6": {"FRA-G6-assurance": 0.60, "GRI-102-56": 0.40},
}

_FIN_FRA_MAP: dict[str, str] = {
    "FIN-E1": "E1", "FIN-E2": "E2", "FIN-E3": "E3",
    "FIN-E4": "E4", "FIN-E5": "E5",
    "FIN-S1": "S1", "FIN-S2": "S2", "FIN-S3": "S3",
    "FIN-S4": "S4", "FIN-S5": "S5", "FIN-S6": "S6",
    "FIN-G1": "G1", "FIN-G2": "G2", "FIN-G3": "G3",
    "FIN-G4": "G4", "FIN-G5": "G5", "FIN-G6": "G6",
}

FINANCIAL_WEIGHTS = SectorWeightRegistry(
    sector="financial",
    pillar_weights=_FIN_PILLAR,
    topic_weights=_FIN_TOPIC,
    metric_weights=_FIN_METRIC,
    fra_topic_map=_FIN_FRA_MAP,
    fra_mandatory_kpis=["E1", "G2", "G3", "G4"],
    stage2_topics=["FIN-S7", "FIN-S8", "FIN-S9"],
)


# ---------------------------------------------------------------------------
# MANUFACTURING SECTOR WEIGHT REGISTRY  (Spec §4.1 – §4.4)
# ---------------------------------------------------------------------------

_MFG_PILLAR: dict[str, float] = {"E": 0.45, "S": 0.30, "G": 0.25}

_MFG_TOPIC: dict[str, dict[str, float]] = {
    "E": {"MFG-E1": 0.15, "MFG-E2": 0.25, "MFG-E3": 0.20,
          "MFG-E4": 0.18, "MFG-E5": 0.15, "MFG-E6": 0.07},
    "S": {"MFG-S1": 0.10, "MFG-S2": 0.07, "MFG-S3": 0.07,
          "MFG-S4": 0.28, "MFG-S5": 0.10, "MFG-S6": 0.15,
          "MFG-S7": 0.13, "MFG-S8": 0.10},
    "G": {"MFG-G1": 0.15, "MFG-G2": 0.25, "MFG-G3": 0.12,
          "MFG-G4": 0.18, "MFG-G5": 0.18, "MFG-G6": 0.12},
}

_MFG_METRIC: dict[str, dict[str, float]] = {
    # MFG-E1 omits FRA-E1.2 (policy origin) — 5 metrics, sum=1.00
    "MFG-E1": {"FRA-E1.1": 0.30, "FRA-E1.3": 0.30, "FRA-E1.4": 0.25,
               "FRA-E1.5": 0.10, "FRA-E1.6": 0.05},
    "MFG-E2": {"GRI-305-1": 0.35, "GRI-305-2": 0.20, "GRI-305-3": 0.20,
               "GRI-305-4": 0.15, "GRI-305-5": 0.10},
    "MFG-E3": {"GRI-302-1":    0.35, "GRI-302-1b":  0.25,
               "GRI-302-3":    0.25, "GRI-302-4":   0.15},
    "MFG-E4": {"GRI-303-3": 0.30, "GRI-303-5": 0.25,
               "GRI-303-4": 0.25, "GRI-303-2": 0.20},
    "MFG-E5": {"GRI-306-3":  0.35, "GRI-306-3h": 0.30,
               "GRI-306-4":  0.20, "GRI-306-3s": 0.15},
    "MFG-E6": {"GRI-304-1": 0.50, "GRI-304-2": 0.30, "GRI-304-4": 0.20},
    # S1-S3 mirror Financial structure
    "MFG-S1": _N({"MFG-S1-headcount": 0.30, "MFG-S1-entry":    0.35,
                  "MFG-S1-senior":    0.35, "MFG-S1-payratio": 0.35}),
    "MFG-S2": {"MFG-S2-fulltime":  0.40, "MFG-S2-parttime": 0.30,
               "MFG-S2-contract":  0.30},
    "MFG-S3": {"MFG-S3-policy":   0.50, "GRI-406-1-mfg":   0.30,
               "GRI-405-1-mfg":   0.20},
    "MFG-S4": {"GRI-403-9f": 0.25, "GRI-403-9t": 0.20, "GRI-403-10": 0.15,
               "FRA-S4-ohs": 0.15, "GRI-403-5":  0.10, "GRI-403-8":  0.08,
               "GRI-403-4":  0.07},
    "MFG-S5": {"MFG-S5-policy":   0.50, "MFG-S5-supplier": 0.50},
    "MFG-S6": {"FRA-S6-ilo-mfg":  0.35, "GRI-412-1":       0.25,
               "GRI-414-1-mfg":  0.25, "FRA-S5-ext":       0.15},
    "MFG-S7": {"GRI-413-1": 0.40, "GRI-201-1": 0.35, "GRI-413-2": 0.25},
    "MFG-S8": {"GRI-404-1": 0.50, "GRI-404-3": 0.30, "GRI-404-2": 0.20},
    "MFG-G1": {"MFG-G1-board":    0.40, "MFG-G1-committee": 0.30,
               "GRI-405-1-mfg2": 0.30},
    "MFG-G2": {"FRA-G2-code-mfg": 0.25, "GRI-205-3-mfg":   0.35,
               "GRI-XX-19.5-mfg": 0.25, "GRI-205-1-mfg":   0.15},
    "MFG-G3": {"FRA-G3-ethics-mfg": 0.60, "GRI-102-17-mfg": 0.40},
    "MFG-G4": {"GRI-308-1": 0.30, "GRI-308-2": 0.25,
               "GRI-414-1s": 0.25, "GRI-414-2": 0.20},
    "MFG-G5": {"FRA-G5-report-mfg": 0.25, "FRA-G5-sdg-mfg":  0.20,
               "FRA-G5-csr-mfg":   0.20, "FRA-G5-ppp-mfg":   0.15,
               "GRI-415-1-mfg":    0.20},
    "MFG-G6": {"FRA-G6-assurance-mfg": 0.60, "GRI-102-56-mfg": 0.40},
}

_MFG_FRA_MAP: dict[str, str] = {
    "MFG-E1": "E1", "MFG-E2": "E2", "MFG-E3": "E3",
    "MFG-E4": "E4", "MFG-E5": "E5",
    "MFG-S1": "S1", "MFG-S2": "S2", "MFG-S3": "S3",
    "MFG-S4": "S4", "MFG-S5": "S5", "MFG-S6": "S6",
    "MFG-G1": "G1", "MFG-G2": "G2", "MFG-G3": "G3",
    "MFG-G5": "G5", "MFG-G6": "G6",
    # MFG-E6, MFG-S7, MFG-S8, MFG-G4 have no FRA Stage 1 KPI
}

MANUFACTURING_WEIGHTS = SectorWeightRegistry(
    sector="manufacturing",
    pillar_weights=_MFG_PILLAR,
    topic_weights=_MFG_TOPIC,
    metric_weights=_MFG_METRIC,
    fra_topic_map=_MFG_FRA_MAP,
    fra_mandatory_kpis=["E1", "G2", "G3", "G4"],
    stage2_topics=["MFG-E6", "MFG-S7", "MFG-S8", "MFG-G4"],
)

_REGISTRY: dict[str, SectorWeightRegistry] = {
    "financial":     FINANCIAL_WEIGHTS,
    "manufacturing": MANUFACTURING_WEIGHTS,
}


# ---------------------------------------------------------------------------
# Part B — Three-Factor Weight Derivation Engine  (Spec §9)
# ---------------------------------------------------------------------------

def compute_derived_weights(
    fra_sub_kpi_counts: dict[str, int],
    gri_disclosure_counts: dict[str, int],
    sasb_metric_counts: dict[str, int],
    data_availability_scores: dict[str, float],
    alpha: float = 0.40,
    beta: float = 0.40,
    gamma: float = 0.20,
    fra_covered_topics: Optional[list[str]] = None,
    min_fra_weight: float = 0.05,
    min_sasb_weight: float = 0.08,
) -> dict[str, float]:
    """Derive topic/metric weights using the three-factor model.

    Spec: Section 9.1
    Weight_i = α × Regulatory_Factor_i + β × Materiality_Factor_i + γ × Data_Factor_i

    Args:
        fra_sub_kpi_counts:     topic/metric → number of FRA sub-KPIs.
        gri_disclosure_counts:  topic/metric → GRI disclosure count.
        sasb_metric_counts:     topic/metric → SASB metric count.
        data_availability_scores: topic/metric → 0.0–1.0 NLP extractability.
        alpha: Regulatory factor weight (default 0.40).
        beta:  Materiality factor weight (default 0.40).
        gamma: Data availability factor weight (default 0.20).
        fra_covered_topics: Topics with FRA Stage 1 coverage — floor applied.
        min_fra_weight: Floor for FRA-covered items (Spec §9.5 Check 1).
        min_sasb_weight: Floor for SASB-coded items (Spec §9.5 Check 2).

    Returns:
        Normalised weight dict (values sum to 1.0).
    """
    topics = list(fra_sub_kpi_counts.keys())

    # ── Step 1: Regulatory Factor  (Spec §9.2) ──────────────────────────────
    total_fra = sum(fra_sub_kpi_counts.values()) or 1
    R = {t: fra_sub_kpi_counts[t] / total_fra for t in topics}

    # ── Step 2: Materiality Factor  (Spec §9.3) ─────────────────────────────
    mat_raw = {
        t: gri_disclosure_counts.get(t, 0) + sasb_metric_counts.get(t, 0) * 1.5
        for t in topics
    }
    total_mat = sum(mat_raw.values()) or 1
    M = {t: mat_raw[t] / total_mat for t in topics}

    # ── Step 3: Data Factor  (Spec §9.4) ────────────────────────────────────
    total_da = sum(data_availability_scores.values()) or 1
    D = {t: data_availability_scores.get(t, 0.0) / total_da for t in topics}

    # ── Step 4: Blended raw weight ───────────────────────────────────────────
    raw = {t: alpha * R[t] + beta * M[t] + gamma * D[t] for t in topics}

    # ── Step 5: Normalise ────────────────────────────────────────────────────
    weights = _N(raw)

    # ── Step 6: Sensitivity Check 1 — FRA floor  (Spec §9.5) ────────────────
    if fra_covered_topics:
        floored = False
        for t in fra_covered_topics:
            if t in weights and weights[t] < min_fra_weight:
                weights[t] = min_fra_weight
                floored = True
        if floored:
            weights = _N(weights)

    # ── Step 7: Sensitivity Check 2 — SASB floor  (Spec §9.5) ──────────────
    sasb_topics = [t for t in topics if sasb_metric_counts.get(t, 0) > 0]
    floored = False
    for t in sasb_topics:
        if weights.get(t, 0.0) < min_sasb_weight:
            weights[t] = min_sasb_weight
            floored = True
    if floored:
        weights = _N(weights)

    return weights


# ---------------------------------------------------------------------------
# Part C — Weight Registry Access API
# ---------------------------------------------------------------------------

def get_weight_registry(sector: str) -> SectorWeightRegistry:
    """Return FINANCIAL_WEIGHTS or MANUFACTURING_WEIGHTS for the given sector."""
    key = sector.lower()
    if key not in _REGISTRY:
        raise KeyError(
            f"Unknown sector '{sector}'. Valid: {list(_REGISTRY.keys())}"
        )
    return _REGISTRY[key]


def get_pillar_weights(sector: str) -> dict[str, float]:
    """Return {'E': float, 'S': float, 'G': float} for the sector."""
    return get_weight_registry(sector).pillar_weights


def get_topic_weights(sector: str, pillar: str) -> dict[str, float]:
    """Return topic weights within a pillar for the sector."""
    registry = get_weight_registry(sector)
    pillar_key = pillar.upper()
    if pillar_key not in registry.topic_weights:
        raise KeyError(f"Pillar '{pillar}' not found for sector '{sector}'.")
    return registry.topic_weights[pillar_key]


def get_metric_weights(sector: str, topic_id: str) -> dict[str, float]:
    """Return metric weights within a topic for the sector."""
    registry = get_weight_registry(sector)
    if topic_id not in registry.metric_weights:
        raise KeyError(f"Topic '{topic_id}' not found for sector '{sector}'.")
    return registry.metric_weights[topic_id]


def get_fra_topic_map(sector: str) -> dict[str, str]:
    """Return topic_id → FRA KPI code mapping for the sector."""
    return get_weight_registry(sector).fra_topic_map


def validate_weights(registry: SectorWeightRegistry) -> list[str]:
    """Validate that all weight groups sum to 1.0 ± 0.001.

    Returns:
        List of violation messages.  Empty list means all weights are valid.
    """
    violations: list[str] = []
    tol = 0.001

    # Pillar weights
    s = sum(registry.pillar_weights.values())
    if abs(s - 1.0) >= tol:
        violations.append(f"[{registry.sector}] pillar_weights sum={s:.6f}")

    # Topic weights per pillar
    for pillar, tw in registry.topic_weights.items():
        s = sum(tw.values())
        if abs(s - 1.0) >= tol:
            violations.append(
                f"[{registry.sector}] topic_weights[{pillar}] sum={s:.6f}"
            )

    # Metric weights per topic
    for topic, mw in registry.metric_weights.items():
        s = sum(mw.values())
        if abs(s - 1.0) >= tol:
            violations.append(
                f"[{registry.sector}] metric_weights[{topic}] sum={s:.6f}"
            )

    return violations


# ---------------------------------------------------------------------------
# Legacy shim — kept for backward-compat with old sasb_scorer/materiality callers
# ---------------------------------------------------------------------------

_DATA_FILE = Path(__file__).resolve().parents[4] / "data" / "sasb_standards.json"


@lru_cache(maxsize=1)
def _load_sasb() -> dict:
    with open(_DATA_FILE, encoding="utf-8") as f:
        return json.load(f)


def get_material_topics(sector: str) -> dict[str, float]:
    """Legacy: load SASB materiality map from sasb_standards.json.

    Deprecated — use get_metric_weights() from the built-in registry instead.
    """
    try:
        data = _load_sasb()
    except FileNotFoundError:
        logger.warning("materiality.file_missing", path=str(_DATA_FILE))
        return {}
    sectors = data.get("sectors", {})
    sector_data = sectors.get(sector) or sectors.get("default", {})
    return sector_data.get("material_topics", {})


def get_industry_average(sector: str) -> float | None:
    """Legacy: return industry-average ESG score from sasb_standards.json."""
    try:
        data = _load_sasb()
    except FileNotFoundError:
        return None
    sectors = data.get("sectors", {})
    sector_data = sectors.get(sector) or sectors.get("default", {})
    return sector_data.get("industry_average_score")


# ---------------------------------------------------------------------------
# __main__ — self-validation
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    for reg in (FINANCIAL_WEIGHTS, MANUFACTURING_WEIGHTS):
        issues = validate_weights(reg)
        if issues:
            print(f"\n[FAIL] {reg.sector.upper()} weight violations:")
            for v in issues:
                print(f"  {v}")
        else:
            print(f"[OK]   {reg.sector.upper()} — all weights valid.")
