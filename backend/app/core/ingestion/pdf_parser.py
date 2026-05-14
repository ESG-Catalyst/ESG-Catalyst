"""PDF parsing — PyMuPDF for digital text.

Enhanced with:
    - Arabic/RTL support: ``arabic-reshaper`` reconstructs ligatures split by
      PyMuPDF's glyph extraction; ``python-bidi`` restores RTL reading order
      via the Unicode BiDi algorithm. Applied automatically on Arabic pages.
    - Table detection via ``page.find_tables()`` — tables are extracted
      as pipe-delimited text and appended after the page's narrative text.
    - Scanned-page OCR: deferred to a later phase (see ocr.py).

Usage:
    from app.core.ingestion.pdf_parser import parse_pdf
"""

from __future__ import annotations

import re
from pathlib import Path

import fitz  # PyMuPDF
import structlog

from app.core.ingestion.ocr import clean_text
# ocr_pdf_page import deferred — Tesseract OCR for scanned pages is a later-phase feature

logger = structlog.get_logger(__name__)

# Minimum chars on a PDF page before we consider it "scanned"
_OCR_CHAR_THRESHOLD = 30

# Minimum cells with content for a table to be worth extracting
_MIN_TABLE_CELLS = 4

# Arabic char ratio above which we apply BiDi + reshaping on a page
_ARABIC_RATIO_THRESHOLD = 0.15

# Pre-compiled regex for Arabic Unicode ranges (same as parser._detect_language)
_RE_ARABIC = re.compile(r"[\u0600-\u06ff\u0750-\u077f\u08a0-\u08ff\u0660-\u0669]")
_RE_LATIN = re.compile(r"[a-zA-Z]")

# Logical Arabic (U+0600–U+06FF): already in correct Unicode reading order.
# Presentation forms (U+FB50–U+FEFF): visual/isolated glyphs needing BiDi fix.
_RE_ARABIC_LOGICAL = re.compile(r"[\u0600-\u06ff\u0750-\u077f]")
_RE_ARABIC_PRESENTATION = re.compile(r"[\ufb50-\ufdff\ufe70-\ufeff]")


def _extract_tables(page: fitz.Page) -> list[str]:
    """Extract tables from a PDF page as pipe-delimited text.

    Only returns tables that have enough populated cells to be useful.
    Skips tables where most cells are empty (likely decorative borders).

    Args:
        page: A PyMuPDF Page object.

    Returns:
        List of pipe-delimited table strings.
    """
    try:
        tab_finder = page.find_tables()
    except Exception as exc:
        logger.debug("pdf_parser.table_detection_failed", error=str(exc))
        return []

    tables: list[str] = []
    for tab in tab_finder.tables:
        try:
            # Extract as list of lists (header + rows)
            data = tab.extract()
            if not data:
                continue

            # Count non-empty cells to filter out noise
            non_empty = sum(
                1 for row in data for cell in row
                if cell is not None and str(cell).strip()
            )
            if non_empty < _MIN_TABLE_CELLS:
                continue

            lines: list[str] = []
            for row_idx, row in enumerate(data):
                # Clean each cell value
                cells = [
                    str(cell).strip().replace("\n", " ") if cell else ""
                    for cell in row
                ]
                line = " | ".join(cells)
                if line.strip(" |"):
                    lines.append(line)
                # Separator after first row (header)
                if row_idx == 0 and lines:
                    lines.append("-" * 40)

            if lines:
                tables.append("\n".join(lines))

        except Exception as exc:
            logger.debug("pdf_parser.table_extract_failed", error=str(exc))
            continue

    return tables


def _arabic_char_ratio(text: str) -> float:
    """Return the fraction of script characters that are Arabic.

    Args:
        text: Raw extracted text from a PDF page.

    Returns:
        Float in [0, 1]; 0.0 if no script chars found.
    """
    arabic = len(_RE_ARABIC.findall(text))
    latin = len(_RE_LATIN.findall(text))
    total = arabic + latin
    return arabic / total if total else 0.0


def _fix_arabic_text(text: str) -> str:
    """Reconstruct Arabic ligatures and restore RTL reading order when needed.

    PyMuPDF can extract Arabic in two modes depending on how the PDF was
    authored:

    1. **Logical order** (codepoints U+0600–U+06FF): the text is already in
       correct Unicode reading order — the same order an LLM tokenizer
       expects.  Applying reshape+get_display here would *reverse* the text
       and produce garbage.  We detect this case and return as-is.

    2. **Visual/presentation order** (codepoints U+FB50–U+FEFF): PyMuPDF
       emitted isolated glyph forms in left-to-right visual sequence, which
       is backwards and fragmented.  We apply arabic_reshaper to reconnect
       ligatures and get_display to restore reading order.

    Detection: count logical vs presentation-form Arabic codepoints.  If
    logical chars dominate (≥ presentation chars), the text is already good.

    Args:
        text: Raw text extracted by PyMuPDF from an Arabic page.

    Returns:
        Text in correct logical Unicode reading order.
    """
    logical_count = len(_RE_ARABIC_LOGICAL.findall(text))
    presentation_count = len(_RE_ARABIC_PRESENTATION.findall(text))

    if logical_count >= presentation_count:
        # Text is already in correct logical order — do not touch it.
        logger.debug(
            "pdf_parser.arabic_already_logical",
            logical=logical_count,
            presentation=presentation_count,
        )
        return text

    # Text is in visual presentation form — apply reshape + BiDi reorder.
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
    except ImportError:
        logger.warning(
            "pdf_parser.arabic_fix_skipped",
            reason="arabic-reshaper or python-bidi not installed",
        )
        return text

    try:
        reshaped = arabic_reshaper.reshape(text)
        return get_display(reshaped)
    except Exception as exc:
        logger.warning("pdf_parser.arabic_fix_failed", error=str(exc))
        return text


def parse_pdf(path: Path) -> list[tuple[int, str, str]]:
    """Extract text from a PDF, falling back to OCR for scanned pages.

    For each page:
    1. Try digital text extraction via PyMuPDF.
    2. Detect and extract any tables on the page.
    3. If digital text is too short, fall back to OCR (Tesseract).

    Tables are appended to the page text in pipe-delimited format,
    separated by a ``[TABLE]`` marker so the chunker can handle them.

    Args:
        path: Path to the PDF file.

    Returns:
        List of ``(page_number, text, method)`` tuples where method is
        ``"digital"``, ``"digital+tables"``, or ``"ocr"``.
    """
    doc = fitz.open(str(path))
    pages: list[tuple[int, str, str]] = []
    tables_found = 0

    for page_num in range(len(doc)):
        page = doc[page_num]
        text = page.get_text("text").strip()

        if len(text) >= _OCR_CHAR_THRESHOLD:
            # Apply Arabic BiDi fix before general cleaning when the page
            # has significant Arabic content.  clean_text() runs after so
            # that any BiDi control chars inserted by the reshaper are
            # stripped in the next step.
            if _arabic_char_ratio(text) >= _ARABIC_RATIO_THRESHOLD:
                text = _fix_arabic_text(text)
                method = "digital+arabic"
            else:
                method = "digital"

            text = clean_text(text)

            # Try to extract tables from this page
            table_texts = _extract_tables(page)
            if table_texts:
                tables_found += len(table_texts)
                table_section = "\n\n".join(
                    f"[TABLE]\n{t}" for t in table_texts
                )
                text = f"{text}\n\n{table_section}"
                # Preserve arabic tag if already set
                method = method.replace("digital", "digital") + "+tables"

            pages.append((page_num + 1, text, method))
        else:
            # Scanned page — OCR via Tesseract is deferred to a later phase.
            # Log and skip; the page will be absent from the output.
            # TODO: re-enable ocr_pdf_page() when Tesseract OCR phase is implemented.
            logger.warning(
                "pdf_parser.empty_page",
                file=path.name,
                page=page_num + 1,
                digital_chars=len(text),
                reason="scanned page skipped — OCR deferred",
            )
            # Keep even minimal text rather than losing the page entirely
            if text:
                pages.append((page_num + 1, text, "digital"))

    total_pages = len(doc)
    doc.close()

    logger.info(
        "pdf_parser.done",
        file=path.name,
        total_pages=total_pages,
        extracted=len(pages),
        tables_found=tables_found,
    )
    return pages
