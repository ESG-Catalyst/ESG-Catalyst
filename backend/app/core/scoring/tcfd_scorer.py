"""TCFD pillar scoring — percentage of TCFD disclosure elements present.

TCFD Pillars:
- Governance: board oversight, management role
- Strategy: risks/opportunities, business impact, scenario resilience
- Risk Management: identification, management process, integration
- Metrics & Targets: metrics used, Scope 1/2/3 emissions, targets
"""

from __future__ import annotations

# ── TCFD keyword signals per pillar ─────────────────────────────────────
_TCFD_PILLAR_KEYWORDS: dict[str, list[str]] = {
    "governance": [
        "board oversight", "board of directors", "climate governance",
        "management role", "executive responsibility",
    ],
    "strategy": [
        "climate risk", "climate opportunity", "scenario analysis",
        "2°c scenario", "business impact", "resilience",
    ],
    "risk_management": [
        "risk identification", "risk management process",
        "climate risk integration", "enterprise risk",
    ],
    "metrics_targets": [
        "scope 1", "scope 2", "scope 3", "ghg emissions",
        "carbon target", "net zero", "emissions intensity",
    ],
}


def _tcfd_pillar_for_metric(metric: object) -> str | None:
    """Infer a TCFD pillar from an extracted metric's GRI/FRA code + topic.

    ``ExtractedMetric`` has no dedicated ``tcfd_pillar`` field (the data
    contract is frozen), so derive it: GHG / energy / Scope disclosures map to
    "Metrics & Targets"; board / governance disclosures to "Governance".
    Strategy and Risk-Management are left to keyword detection on the text.
    Returns None when no confident mapping exists.
    """
    code = str(getattr(metric, "gri_code", "") or "")
    topic = str(getattr(metric, "topic", "") or "")
    hay = f"{code} {topic}".upper()
    if any(k in hay for k in ("305", "302", "FRA", "GHG", "EMISSION", "SCOPE")):
        return "metrics_targets"
    if any(k in hay for k in ("GRI 2-", "GRI 2 ", "405", "GOVERNANCE", "BOARD")):
        return "governance"
    return None


def compute_tcfd_score(metrics: list, full_text: str = "") -> dict[str, float]:
    """Score TCFD pillar coverage from extracted metrics and document text.

    Args:
        metrics: Extracted metrics (TCFD pillar inferred per metric via
            ``_tcfd_pillar_for_metric`` — the schema has no ``tcfd_pillar``).
        full_text: Optional raw document text for keyword-based pillar detection.

    Returns:
        Dict mapping pillar name → 0–100 score, plus ``"overall"`` key.
    """
    metric_pillars = {p for m in metrics if (p := _tcfd_pillar_for_metric(m))}

    pillar_scores: dict[str, float] = {}
    lower_text = full_text.lower()

    for pillar, keywords in _TCFD_PILLAR_KEYWORDS.items():
        # Check via metric pillars first
        if pillar in metric_pillars or pillar.replace("_", " ") in metric_pillars:
            pillar_scores[pillar] = 100.0
            continue

        # Fall back to keyword presence in document text
        hits = sum(1 for kw in keywords if kw in lower_text)
        pillar_scores[pillar] = min(100.0, hits / len(keywords) * 100)

    overall = sum(pillar_scores.values()) / len(pillar_scores) if pillar_scores else 0.0
    pillar_scores["overall"] = round(overall, 1)

    return {k: round(v, 1) for k, v in pillar_scores.items()}
