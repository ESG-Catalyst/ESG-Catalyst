"""DOCX parsing — extract paragraphs and tables from Word documents.

Tables are rendered as pipe-delimited text (same format as spreadsheets)
so the downstream chunker treats all tabular data uniformly.

Usage:
    from app.core.ingestion.docx_parser import parse_docx
"""

from __future__ import annotations

from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)


def parse_docx(path: Path) -> list[tuple[int, str, str]]:
    """Extract text from a DOCX file, preserving paragraphs and tables.

    The document body is walked in order. Consecutive paragraphs are
    grouped together, and each table is emitted as its own "page" in
    pipe-delimited format.  This keeps table structure visible to the
    chunker and extractor without mixing it into narrative text.

    Args:
        path: Path to the ``.docx`` file.

    Returns:
        List of ``(page_number, text, method)`` tuples where method is
        ``"docx"`` for paragraph text or ``"table"`` for table content.
    """
    try:
        from docx import Document
    except ImportError:
        raise RuntimeError(
            "python-docx is required for DOCX parsing. "
            "Install: pip install python-docx"
        ) from None

    doc = Document(str(path))
    pages: list[tuple[int, str, str]] = []
    page_idx = 1

    # Walk the document body in order — paragraphs and tables are
    # interleaved in doc.element.body.  We accumulate paragraph text
    # until we hit a table, flush it, emit the table, then resume.
    current_paragraphs: list[str] = []

    def _flush_paragraphs():
        nonlocal page_idx
        if not current_paragraphs:
            return
        text = "\n".join(current_paragraphs).strip()
        if text:
            pages.append((page_idx, text, "docx"))
            page_idx += 1
        current_paragraphs.clear()

    def _render_table(table) -> str:
        """Render a docx Table as pipe-delimited text."""
        lines: list[str] = []
        for row_idx, row in enumerate(table.rows):
            cells = [cell.text.strip().replace("\n", " ") for cell in row.cells]
            line = " | ".join(cells)
            if line.strip(" |"):
                lines.append(line)
            # Add separator after header row
            if row_idx == 0 and lines:
                lines.append("-" * 40)
        return "\n".join(lines)

    # Iterate over the raw XML body children to preserve order
    from docx.oxml.ns import qn

    for child in doc.element.body:
        tag = child.tag

        if tag == qn("w:p"):
            # Paragraph
            para_text = child.text or ""
            # python-docx paragraph text needs to be extracted properly
            # child.text only gets direct text; use itertext for all runs
            para_text = "".join(child.itertext()).strip()
            if para_text:
                current_paragraphs.append(para_text)

        elif tag == qn("w:tbl"):
            # Table — flush accumulated paragraphs first
            _flush_paragraphs()
            # Find the matching Table object
            for table in doc.tables:
                if table._element is child:
                    table_text = _render_table(table)
                    if table_text.strip():
                        pages.append((page_idx, table_text, "table"))
                        page_idx += 1
                    break

    # Flush any remaining paragraphs
    _flush_paragraphs()

    if not pages:
        logger.warning("docx_parser.empty", file=path.name)

    logger.info(
        "docx_parser.done",
        file=path.name,
        total_pages=len(pages),
        tables=sum(1 for _, _, m in pages if m == "table"),
        text_sections=sum(1 for _, _, m in pages if m == "docx"),
    )
    return pages
