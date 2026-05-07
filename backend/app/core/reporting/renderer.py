"""PDF renderer — HTML-to-PDF via WeasyPrint.

Input:  ordered list of ReportSection objects (from builder + narrative)
Output: PDF bytes or file path
"""

from __future__ import annotations

from pathlib import Path

from app.core.reporting.builder import ReportSection


def render_pdf(sections: list[ReportSection], output_path: Path) -> Path:
    """Render report sections to a PDF file.

    Args:
        sections: Sections with narratives populated.
        output_path: Destination path for the PDF file.

    Returns:
        Path to the generated PDF.

    Raises:
        NotImplementedError: M5 is not yet implemented (CLAUDE.md Step 6).
    """
    raise NotImplementedError("M5 PDF renderer not yet implemented — see CLAUDE.md Step 6")
