"""Report builder — group metrics by GRI topic into ordered ReportSection list.

Input:  approved/extracted ExtractedMetrics + ScoringResult + company profile
Output: ordered list of ReportSection objects (consumed by narrative.py)

Section order follows CLAUDE.md M5 spec:
    Cover, Executive Summary, Company Profile, Materiality Assessment,
    Environmental, Social, Governance, GRI Content Index, Gap Analysis
"""

from __future__ import annotations

import re
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
    "FRA": "G",
}

# Canonical section order
_TOPIC_ORDER = [
    "GRI 2", "GRI 3",
    "GRI 302", "GRI 303", "GRI 305", "GRI 306",
    "GRI 401", "GRI 403", "GRI 404", "GRI 405", "GRI 406", "GRI 418",
    "FRA",
]


def _topic_of(gri_code: str) -> str:
    """Extract GRI topic prefix from a full indicator code.

    Args:
        gri_code: Full GRI code, e.g. ``"GRI 302-1"`` or ``"FRA-36"``.

    Returns:
        Topic prefix such as ``"GRI 302"`` or ``"FRA"``, or ``"Other"``
        for unrecognised codes.
    """
    m = re.match(r"(GRI \d+|FRA)", gri_code)
    return m.group(1) if m else "Other"


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
    for topic in _TOPIC_ORDER:
        if topic not in by_topic:
            continue
        topic_metrics = by_topic[topic]
        if not topic_metrics:
            continue
        title = _GRI_TOPIC_NAMES.get(topic, topic)
        pillar = _PILLAR_OF_TOPIC.get(topic, "G")
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
