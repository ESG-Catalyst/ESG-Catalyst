"""Narrative generation — LLM drafts factual narrative per report section.

Uses ModelRouter("report") for all LLM calls.
Output is English only, references specific values, notes what is missing.
"""

from __future__ import annotations

from app.core.reporting.builder import ReportSection


async def generate_narratives(sections: list[ReportSection]) -> list[ReportSection]:
    """Draft LLM narratives for each section and return updated sections.

    Args:
        sections: Output of ``build_report_sections()``.

    Returns:
        Same sections with ``narrative`` field populated.

    Raises:
        NotImplementedError: M5 is not yet implemented (CLAUDE.md Step 6).
    """
    raise NotImplementedError("M5 narrative generation not yet implemented — see CLAUDE.md Step 6")
