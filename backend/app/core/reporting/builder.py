"""Report builder — group metrics by GRI topic into ordered ReportSection list.

Input:  approved ExtractedMetrics + ESGScore + company profile
Output: ordered list of ReportSection objects (consumed by narrative.py)
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ReportSection:
    """One section of the final ESG report."""

    title: str
    gri_topic: str           # e.g. "GRI 302: Energy"
    pillar: str              # "E", "S", or "G"
    metrics: list = field(default_factory=list)
    narrative: str = ""      # filled in by narrative.py


def build_report_sections(metrics: list, score) -> list[ReportSection]:
    """Group approved metrics into ordered report sections.

    Args:
        metrics: List of approved ``ExtractedMetric`` ORM objects.
        score: ``ScoringResult`` from the scorer.

    Returns:
        Ordered list of ``ReportSection`` objects.

    Raises:
        NotImplementedError: M5 is not yet implemented (CLAUDE.md Step 6).
    """
    raise NotImplementedError("M5 report builder not yet implemented — see CLAUDE.md Step 6")
