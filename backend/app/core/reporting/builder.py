"""Report builder — group metrics by GRI topic into ordered ReportSection list.

Input:  approved/extracted ExtractedMetrics + ScoringResult + company profile
Output: ordered list of ReportSection objects (consumed by narrative.py)

Section order follows CLAUDE.md M5 spec:
    Cover, Executive Summary, Company Profile, Materiality Assessment,
    Environmental, Social, Governance, GRI Content Index, Gap Analysis
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

import structlog

from app.core.gri.indicators import get_all_indicators

logger = structlog.get_logger(__name__)


# ── GRI topic → human label (for section headings) ──────────────────────
_GRI_TOPIC_NAMES: dict[str, str] = {
    "GRI 2": "General Disclosures",
    "GRI 3": "Material Topics",
    "GRI 302": "Energy",
    "GRI 303": "Water",
    "GRI 305": "Emissions",
    "GRI 306": "Waste",
    "GRI 401": "Employment",
    "GRI 403": "Occupational Health & Safety",
    "GRI 404": "Training & Education",
    "GRI 405": "Diversity & Equal Opportunity",
    "GRI 406": "Non-discrimination",
    "GRI 418": "Customer Privacy",
    # Economic / governance topics
    "GRI 201": "Economic Performance",
    "GRI 205": "Anti-corruption",
    "GRI 207": "Tax",
    "GRI 415": "Public Policy",
    # Financial-sector standards (GRI Financial Services + SASB)
    "GRI FS": "Financial Services Sector Disclosures",
    "SASB FN-CF": "SASB — Consumer Finance",
    "SASB FN-MF": "SASB — Mortgage Finance",
    "SASB FN-IN": "SASB — Insurance",
    "FRA": "Egyptian FRA Disclosures",
}

_PILLAR_OF_TOPIC: dict[str, str] = {
    "GRI 2": "G",
    "GRI 3": "G",
    "GRI 302": "E",
    "GRI 303": "E",
    "GRI 305": "E",
    "GRI 306": "E",
    "GRI 401": "S",
    "GRI 403": "S",
    "GRI 404": "S",
    "GRI 405": "S",
    "GRI 406": "S",
    "GRI 418": "S",
    "GRI 201": "G",
    "GRI 205": "G",
    "GRI 207": "G",
    "GRI 415": "G",
    # Sector standards span pillars — these are only fallbacks; the real
    # section pillar is derived from the metrics present (see _pillar_of_section).
    "GRI FS": "G",
    "SASB FN-CF": "G",
    "SASB FN-MF": "S",
    "SASB FN-IN": "E",
    "FRA": "G",
}

# Canonical section order
_TOPIC_ORDER = [
    "GRI 2", "GRI 3",
    "GRI 201", "GRI 205", "GRI 207", "GRI 415",
    "GRI 302", "GRI 303", "GRI 305", "GRI 306",
    "GRI 401", "GRI 403", "GRI 404", "GRI 405", "GRI 406", "GRI 418",
    "GRI FS",
    "SASB FN-CF", "SASB FN-MF", "SASB FN-IN",
    "FRA",
]


def _topic_of(gri_code: str) -> str:
    """Extract the section topic from a full indicator code.

    Handles every code shape in the 46-indicator catalog:
    classic GRI (``GRI 305-1`` → ``GRI 305``), GRI Financial Services
    (``GRI-FS-XX.0.1-LENDING`` → ``GRI FS``), SASB industry standards
    (``SASB-FN-CF-230a.1`` / ``FN-IN-410c.1`` → ``SASB FN-CF`` / ``SASB FN-IN``),
    and FRA (``FRA-36`` → ``FRA``).

    Args:
        gri_code: Full indicator code.

    Returns:
        A topic label, or ``"Other"`` for unrecognised codes (which the
        builder still renders via the trailing-topics safety net).
    """
    code = (gri_code or "").strip()
    # SASB industry standards — group by standard (FN-CF / FN-MF / FN-IN).
    m = re.match(r"(?:SASB-)?(FN-[A-Z]{2})\b", code)
    if m:
        return f"SASB {m.group(1)}"
    # GRI Financial Services sector codes (hyphenated, not "GRI <num>").
    if code.startswith("GRI-FS"):
        return "GRI FS"
    # Classic GRI topic (e.g. "GRI 305-1" → "GRI 305").
    m = re.match(r"(GRI \d+)", code)
    if m:
        return m.group(1)
    if code.startswith("FRA"):
        return "FRA"
    return "Other"


def _pillar_of_section(topic: str, topic_metrics: list) -> str:
    """Pick a section's E/S/G pillar from the metrics it contains.

    SASB standards span pillars, so a single hard-coded topic→pillar map is
    lossy. Use the majority pillar of the metrics actually present; fall back
    to ``_PILLAR_OF_TOPIC`` (then ``"G"``) when metrics carry no pillar.
    """
    counts: Counter = Counter()
    for m in topic_metrics:
        p = getattr(m, "pillar", None)
        p = getattr(p, "value", p)  # PillarType enum → "E"/"S"/"G"
        if p:
            counts[str(p)] += 1
    if counts:
        return counts.most_common(1)[0][0]
    return _PILLAR_OF_TOPIC.get(topic, "G")


@dataclass
class CompanyProfile:
    name: str
    sector: str = "default"
    reporting_period: str = ""
    headquarters: str = ""


@dataclass
class ReportSection:
    """One section of the final ESG report."""
    title: str
    gri_topic: str
    pillar: str
    metrics: list = field(default_factory=list)
    narrative: str = ""


@dataclass
class ReportBundle:
    company: CompanyProfile
    score: object
    sections: list[ReportSection]


def build_report_sections(
    metrics: list,
    score,
    company: CompanyProfile,
) -> ReportBundle:
    """Group metrics into ordered report sections.

    Args:
        metrics: List of ExtractedMetric schema objects.
        score: ScoringResult from the scorer.
        company: CompanyProfile with name, sector, etc.

    Returns:
        ReportBundle containing company, score, and ordered sections.
    """
    # Group metrics by topic
    by_topic: dict[str, list] = {}
    for m in metrics:
        topic = _topic_of(m.gri_code)
        by_topic.setdefault(topic, []).append(m)

    # Also add missing indicators as placeholder metrics so gaps appear
    all_indicators = get_all_indicators()
    present_codes = {m.gri_code for m in metrics}
    for ind in all_indicators:
        if ind["code"] not in present_codes:
            topic = _topic_of(ind["code"])
            by_topic.setdefault(topic, [])

    sections: list[ReportSection] = []
    # Canonical order first, then any topics not in the canonical list (new
    # code shapes, "Other") so no indicator is ever silently dropped.
    ordered_topics = _TOPIC_ORDER + [t for t in by_topic if t not in _TOPIC_ORDER]
    for topic in ordered_topics:
        topic_metrics = by_topic.get(topic)
        if not topic_metrics:  # absent topic, or a missing-only placeholder
            continue
        title = _GRI_TOPIC_NAMES.get(topic, topic)
        pillar = _pillar_of_section(topic, topic_metrics)
        sections.append(ReportSection(title=title, gri_topic=topic, pillar=pillar, metrics=topic_metrics))

    logger.info("builder.sections_built", count=len(sections), metrics=len(metrics))
    return ReportBundle(company=company, score=score, sections=sections)


def gri_content_index(metrics: list) -> list[dict]:
    """Build GRI Content Index rows for all known indicators.

    Args:
        metrics: All ExtractedMetric objects in the report.

    Returns:
        List of dicts: code, name, page, status for each indicator.
    """
    by_code = {m.gri_code: m for m in metrics}
    all_indicators = get_all_indicators()
    rows = []
    for ind in all_indicators:
        code = ind["code"]
        m = by_code.get(code)
        if m:
            status = m.status.value if hasattr(m.status, "value") else str(m.status)
            page = m.source_page
        else:
            status = "not reported"
            page = None
        rows.append({"code": code, "name": ind["name"], "page": page, "status": status})
    return rows
