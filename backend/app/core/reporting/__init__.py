"""M5 Report Generation — structure metrics into PDF report."""

from app.core.reporting.builder import (
    CompanyProfile,
    ReportBundle,
    ReportSection,
    build_report_sections,
    gri_content_index,
)
from app.core.reporting.narrative import generate_narratives
from app.core.reporting.renderer import render_pdf, render_report_html

__all__ = [
    "CompanyProfile",
    "ReportBundle",
    "ReportSection",
    "build_report_sections",
    "generate_narratives",
    "gri_content_index",
    "render_pdf",
    "render_report_html",
]
