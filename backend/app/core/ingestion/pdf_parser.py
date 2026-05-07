"""PDF parsing — PyMuPDF for digital text, Tesseract OCR for scanned pages.

Usage:
    from app.core.ingestion.pdf_parser import parse_pdf
"""

from __future__ import annotations

from pathlib import Path

import fitz  # PyMuPDF
import structlog

from app.core.ingestion.ocr import clean_text, ocr_pdf_page

logger = structlog.get_logger(__name__)

# Minimum chars on a PDF page before we consider it "scanned"
_OCR_CHAR_THRESHOLD = 30


def parse_pdf(path: Path) -> list[tuple[int, str, str]]:
    """Extract text from a PDF, falling back to OCR for scanned pages.

    Args:
        path: Path to the PDF file.

    Returns:
        List of ``(page_number, text, method)`` tuples where method is
        ``"digital"`` or ``"ocr"``.
    """
    doc = fitz.open(str(path))
    pages: list[tuple[int, str, str]] = []

    for page_num in range(len(doc)):
        page = doc[page_num]
        text = page.get_text("text").strip()

        if len(text) >= _OCR_CHAR_THRESHOLD:
            text = clean_text(text)
            pages.append((page_num + 1, text, "digital"))
        else:
            ocr_text = ocr_pdf_page(page)
            if ocr_text:
                pages.append((page_num + 1, ocr_text, "ocr"))
            else:
                logger.warning(
                    "pdf_parser.empty_page",
                    file=path.name,
                    page=page_num + 1,
                    digital_chars=len(text),
                )
                if text:
                    pages.append((page_num + 1, text, "digital"))

    total_pages = len(doc)
    doc.close()

    logger.info("pdf_parser.done", file=path.name, total_pages=total_pages, extracted=len(pages))
    return pages
