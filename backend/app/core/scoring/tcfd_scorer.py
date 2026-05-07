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


def compute_tcfd_score(metrics: list, full_text: str = "") -> dict[str, float]:
    """Score TCFD pillar coverage from extracted metrics and document text.

    Args:
        metrics: Extracted metrics with ``tcfd_pillar`` field.
        full_text: Optional raw document text for keyword-based pillar detection.

    Returns:
        Dict mapping pillar name → 0–100 score, plus ``"overall"`` key.
    """
    metric_pillars = {m.tcfd_pillar for m in metrics if getattr(m, "tcfd_pillar", None)}

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
