"""DOCX parsing — extract paragraphs and tables from Word documents.

Tables are rendered as pipe-delimited text (same format as spreadsheets)
so the downstream chunker treats all tabular data uniformly.

Arabic support: paragraphs with significant Arabic content are passed through
``_fix_arabic_text()`` (arabic-reshaper + python-bidi) before being emitted,
matching the same treatment applied to PDF pages.

Usage:
    from app.core.ingestion.docx_parser import parse_docx
"""

from __future__ import annotations

import re
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)

# Minimum Arabic character ratio to trigger BiDi fix on a DOCX paragraph
_ARABIC_RATIO_THRESHOLD = 0.15

_RE_ARABIC = re.compile(r"[\u0600-\u06ff\u0750-\u077f\u08a0-\u08ff\u0660-\u0669]")
_RE_LATIN = re.compile(r"[a-zA-Z]")
_RE_ARABIC_LOGICAL = re.compile(r"[\u0600-\u06ff\u0750-\u077f]")
_RE_ARABIC_PRESENTATION = re.compile(r"[\ufb50-\ufdff\ufe70-\ufeff]")


def _arabic_char_ratio(text: str) -> float:
    """Return fraction of script characters that are Arabic (0.0–1.0)."""
    arabic = len(_RE_ARABIC.findall(text))
    latin = len(_RE_LATIN.findall(text))
    total = arabic + latin
    return arabic / total if total else 0.0


def _fix_arabic_text(text: str) -> str:
    """Reconstruct Arabic ligatures and restore RTL reading order when needed.

    Only applies reshape+BiDi when the text is in visual presentation form
    (U+FB50–U+FEFF). If the text is already in logical Unicode order
    (U+0600–U+06FF), it is returned unchanged.
    """
    logical_count = len(_RE_ARABIC_LOGICAL.findall(text))
    presentation_count = len(_RE_ARABIC_PRESENTATION.findall(text))

    if logical_count >= presentation_count:
        return text

    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
    except ImportError:
        logger.warning(
            "docx_parser.arabic_fix_skipped",
            reason="arabic-reshaper or python-bidi not installed",
        )
        return text

    try:
        reshaped = arabic_reshaper.reshape(text)
        return get_display(reshaped)
    except Exception as exc:
        logger.warning("docx_parser.arabic_fix_failed", error=str(exc))
        return text


def parse_docx(path: Path) -> list[tuple[int, str, str]]:
    """Extract text from a DOCX file, preserving paragraphs and tables.

    The document body is walked in order. Consecutive paragraphs are
    grouped together, and each table is emitted as its own "page" in
    pipe-delimited format.  This keeps table structure visible to the
    chunker and extractor without mixing it into narrative text.

    Arabic paragraphs are automatically reshaped and BiDi-reordered so
    that RTL text arrives at the chunker in correct logical order.

    Args:
        path: Path to the ``.docx`` file.

    Returns:
        List of ``(page_number, text, method)`` tuples where method is
        ``\"docx\"``, ``\"docx+arabic\"``, or ``\"table\"`` for table content.
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
    current_is_arabic: bool = False

    def _flush_paragraphs():
        nonlocal page_idx, current_is_arabic
        if not current_paragraphs:
            return
        text = "\n".join(current_paragraphs).strip()
        if text:
            method = "docx+arabic" if current_is_arabic else "docx"
            pages.append((page_idx, text, method))
            page_idx += 1
        current_paragraphs.clear()
        current_is_arabic = False

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
            para_text = "".join(child.itertext()).strip()
            if para_text:
                # Apply BiDi fix if paragraph is predominantly Arabic
                if _arabic_char_ratio(para_text) >= _ARABIC_RATIO_THRESHOLD:
                    para_text = _fix_arabic_text(para_text)
                    current_is_arabic = True
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

    arabic_sections = sum(1 for _, _, m in pages if "arabic" in m)
    logger.info(
        "docx_parser.done",
        file=path.name,
        total_pages=len(pages),
        tables=sum(1 for _, _, m in pages if m == "table"),
        text_sections=sum(1 for _, _, m in pages if "docx" in m),
        arabic_sections=arabic_sections,
    )
    return pages
