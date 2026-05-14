"""Document ingestion — parse uploaded files into structured text.

Supported formats:
    - PDF (digital text via PyMuPDF, scanned/Arabic via Tesseract OCR)
    - DOCX (via python-docx — paragraphs + tables)
    - XLSX / XLS (via openpyxl + pandas)
    - CSV
    - Images: PNG, JPG, TIFF (via Tesseract OCR)

Usage:
    from app.core.ingestion.parser import ingest_document

    result = ingest_document("/path/to/file.pdf")
    for page in result.pages:
        print(page.page_number, page.text[:80])
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)

# ── Supported file extensions ────────────────────────────────────────────
_PDF_EXTS = {".pdf"}
_DOCX_EXTS = {".docx"}
_SPREADSHEET_EXTS = {".xlsx", ".xls"}
_CSV_EXTS = {".csv"}
_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp"}

_ALL_SUPPORTED = _PDF_EXTS | _DOCX_EXTS | _SPREADSHEET_EXTS | _CSV_EXTS | _IMAGE_EXTS


# ── Data classes ─────────────────────────────────────────────────────────
@dataclass
class PageContent:
    """One logical page / sheet of extracted text."""

    page_number: int
    text: str
    method: str  # "digital", "ocr", "table", "docx"


@dataclass
class IngestedDocument:
    """Full result of parsing a single uploaded file."""

    source_file: str
    file_type: str
    page_count: int
    language: str | None
    pages: list[PageContent] = field(default_factory=list)

    @property
    def full_text(self) -> str:
        """Concatenate all pages into a single string."""
        return "\n\n".join(p.text for p in self.pages if p.text)


# ── Public entry point ───────────────────────────────────────────────────
def ingest_document(file_path: str | Path) -> IngestedDocument:
    """Parse a document and return structured text content.

    Args:
        file_path: Absolute or relative path to the file.

    Returns:
        An ``IngestedDocument`` with per-page text and metadata.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the file type is not supported.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    ext = path.suffix.lower()
    if ext not in _ALL_SUPPORTED:
        raise ValueError(
            f"Unsupported file type {ext!r}. "
            f"Supported: {sorted(_ALL_SUPPORTED)}"
        )

    logger.info("ingestion.start", file=path.name, ext=ext)

    if ext in _PDF_EXTS:
        result = _parse_pdf(path)
    elif ext in _DOCX_EXTS:
        result = _parse_docx(path)
    elif ext in _SPREADSHEET_EXTS:
        result = _parse_spreadsheet(path)
    elif ext in _CSV_EXTS:
        result = _parse_csv(path)
    elif ext in _IMAGE_EXTS:
        result = _parse_image(path)
    else:
        raise ValueError(f"Unhandled extension: {ext}")

    result.language = _detect_language(result.full_text)

    logger.info(
        "ingestion.done",
        file=path.name,
        pages=result.page_count,
        chars=len(result.full_text),
        language=result.language,
    )
    return result


# ── Sub-parser adapters ──────────────────────────────────────────────────
def _parse_pdf(path: Path) -> IngestedDocument:
    from app.core.ingestion.pdf_parser import parse_pdf

    raw_pages = parse_pdf(path)
    pages = [PageContent(page_number=n, text=t, method=m) for n, t, m in raw_pages]
    return IngestedDocument(
        source_file=path.name,
        file_type="pdf",
        page_count=len(pages),
        language=None,
        pages=pages,
    )


def _parse_docx(path: Path) -> IngestedDocument:
    """Parse a DOCX file extracting paragraphs and tables.

    Tables are rendered as pipe-delimited text (same format as
    spreadsheet parsing) so downstream chunking treats them uniformly.
    """
    from app.core.ingestion.docx_parser import parse_docx

    raw_pages = parse_docx(path)
    pages = [PageContent(page_number=n, text=t, method=m) for n, t, m in raw_pages]
    return IngestedDocument(
        source_file=path.name,
        file_type="docx",
        page_count=len(pages),
        language=None,
        pages=pages,
    )


def _parse_spreadsheet(path: Path) -> IngestedDocument:
    from app.core.ingestion.table_extractor import parse_spreadsheet

    raw_pages = parse_spreadsheet(path)
    pages = [PageContent(page_number=n, text=t, method="table") for n, t in raw_pages]
    return IngestedDocument(
        source_file=path.name,
        file_type="xlsx",
        page_count=len(pages),
        language=None,
        pages=pages,
    )


def _parse_csv(path: Path) -> IngestedDocument:
    from app.core.ingestion.table_extractor import parse_csv

    text = parse_csv(path)
    return IngestedDocument(
        source_file=path.name,
        file_type="csv",
        page_count=1,
        language=None,
        pages=[PageContent(page_number=1, text=text, method="table")],
    )


def _parse_image(path: Path) -> IngestedDocument:
    from app.core.ingestion.ocr import parse_image

    text, file_type = parse_image(path)

    if not text:
        logger.warning(
            "ingestion.image_empty",
            file=path.name,
            reason="OCR returned no text (Tesseract may not be installed)",
        )

    return IngestedDocument(
        source_file=path.name,
        file_type=file_type,
        page_count=1,
        language=None,
        pages=[PageContent(page_number=1, text=text, method="ocr")],
    )


# ── Language detection ───────────────────────────────────────────────────
def _detect_language(text: str) -> str | None:
    """Simple heuristic language detection based on character ranges.

    Returns:
        ``"ar"`` if predominantly Arabic, ``"en"`` if Latin, ``"ar+en"`` if
        mixed, or ``None`` if the text is too short to tell.
    """
    if len(text) < 20:
        return None

    arabic_chars = len(re.findall(r"[؀-ۿݐ-ݿࢠ-ࣿ٠-٩]", text))
    latin_chars = len(re.findall(r"[a-zA-Z]", text))
    total = arabic_chars + latin_chars

    if total == 0:
        return None

    arabic_ratio = arabic_chars / total
    if arabic_ratio > 0.6:
        return "ar"
    elif arabic_ratio > 0.15:
        return "ar+en"
    else:
        return "en"
