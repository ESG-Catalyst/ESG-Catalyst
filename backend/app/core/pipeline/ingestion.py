"""Document ingestion — parse uploaded files into structured text.

Supported formats:
    - PDF (digital text via PyMuPDF, scanned/Arabic via Tesseract OCR)
    - XLSX / XLS (via openpyxl + pandas)
    - CSV
    - Images: PNG, JPG, TIFF (via Tesseract OCR)

Usage:
    from app.core.pipeline.ingestion import ingest_document

    result = ingest_document("/path/to/file.pdf")
    for page in result.pages:
        print(page.page_number, page.text[:80])
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from pathlib import Path

import fitz  # PyMuPDF
import pandas as pd
import structlog
from PIL import Image

logger = structlog.get_logger(__name__)

# ── Minimum chars on a PDF page before we consider it "scanned" ──────────
_OCR_CHAR_THRESHOLD = 30

# ── Supported file extensions ────────────────────────────────────────────
_PDF_EXTS = {".pdf"}
_SPREADSHEET_EXTS = {".xlsx", ".xls"}
_CSV_EXTS = {".csv"}
_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp"}

_ALL_SUPPORTED = _PDF_EXTS | _SPREADSHEET_EXTS | _CSV_EXTS | _IMAGE_EXTS


# ── Data classes ─────────────────────────────────────────────────────────
@dataclass
class PageContent:
    """One logical page / sheet of extracted text."""

    page_number: int
    text: str
    method: str  # "digital", "ocr", "table"


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
    elif ext in _SPREADSHEET_EXTS:
        result = _parse_spreadsheet(path)
    elif ext in _CSV_EXTS:
        result = _parse_csv(path)
    elif ext in _IMAGE_EXTS:
        result = _parse_image(path)
    else:
        raise ValueError(f"Unhandled extension: {ext}")

    # Detect dominant language from extracted text
    result.language = _detect_language(result.full_text)

    logger.info(
        "ingestion.done",
        file=path.name,
        pages=result.page_count,
        chars=len(result.full_text),
        language=result.language,
    )
    return result


# ── PDF parsing ──────────────────────────────────────────────────────────
def _parse_pdf(path: Path) -> IngestedDocument:
    """Extract text from a PDF, falling back to OCR for scanned pages."""
    doc = fitz.open(str(path))
    pages: list[PageContent] = []

    for page_num in range(len(doc)):
        page = doc[page_num]
        text = page.get_text("text").strip()

        if len(text) >= _OCR_CHAR_THRESHOLD:
            # Digital text extracted successfully
            text = _clean_text(text)
            pages.append(PageContent(page_number=page_num + 1, text=text, method="digital"))
        else:
            # Page is likely scanned — try OCR
            ocr_text = _ocr_pdf_page(page)
            if ocr_text:
                pages.append(PageContent(page_number=page_num + 1, text=ocr_text, method="ocr"))
            else:
                # Truly empty page or OCR unavailable
                logger.warning(
                    "ingestion.empty_page",
                    file=path.name,
                    page=page_num + 1,
                    digital_chars=len(text),
                )
                if text:
                    pages.append(
                        PageContent(page_number=page_num + 1, text=text, method="digital")
                    )

    total_pages = len(doc)
    doc.close()

    return IngestedDocument(
        source_file=path.name,
        file_type="pdf",
        page_count=total_pages,
        language=None,
        pages=pages,
    )


def _ocr_pdf_page(page: fitz.Page) -> str:
    """Render a PDF page to an image and run Tesseract OCR (Arabic + English).

    Returns empty string if Tesseract is not installed.
    """
    try:
        import pytesseract
    except ImportError:
        logger.warning("ingestion.ocr_unavailable", reason="pytesseract not installed")
        return ""

    # Render page at 300 DPI for good OCR accuracy
    pix = page.get_pixmap(dpi=300)
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

    try:
        # ara+eng: Arabic first (RTL), English second
        text = pytesseract.image_to_string(img, lang="ara+eng")
        return _clean_text(text)
    except pytesseract.TesseractNotFoundError:
        logger.warning("ingestion.ocr_unavailable", reason="tesseract binary not found")
        return ""


# ── Spreadsheet parsing ──────────────────────────────────────────────────
def _parse_spreadsheet(path: Path) -> IngestedDocument:
    """Parse XLSX/XLS into text, one page per sheet."""
    sheets = pd.read_excel(path, sheet_name=None, dtype=str)
    pages: list[PageContent] = []

    for idx, (sheet_name, df) in enumerate(sheets.items(), start=1):
        df = df.fillna("")
        lines: list[str] = []

        # Sheet header
        lines.append(f"=== Sheet: {sheet_name} ===")
        lines.append("")

        # Column headers
        if len(df.columns) > 0:
            lines.append(" | ".join(str(c) for c in df.columns))
            lines.append("-" * 40)

        # Data rows
        for _, row in df.iterrows():
            row_text = " | ".join(str(v) for v in row.values if str(v).strip())
            if row_text.strip():
                lines.append(row_text)

        text = "\n".join(lines)
        pages.append(PageContent(page_number=idx, text=text, method="table"))

    return IngestedDocument(
        source_file=path.name,
        file_type="xlsx",
        page_count=len(pages),
        language=None,
        pages=pages,
    )


# ── CSV parsing ──────────────────────────────────────────────────────────
def _parse_csv(path: Path) -> IngestedDocument:
    """Parse a CSV file into a single page of text."""
    # Detect encoding — try UTF-8, fall back to latin-1
    for encoding in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            df = pd.read_csv(path, dtype=str, encoding=encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ValueError(f"Cannot decode CSV file: {path.name}")

    df = df.fillna("")
    lines: list[str] = []

    if len(df.columns) > 0:
        lines.append(" | ".join(str(c) for c in df.columns))
        lines.append("-" * 40)

    for _, row in df.iterrows():
        row_text = " | ".join(str(v) for v in row.values if str(v).strip())
        if row_text.strip():
            lines.append(row_text)

    text = "\n".join(lines)

    return IngestedDocument(
        source_file=path.name,
        file_type="csv",
        page_count=1,
        language=None,
        pages=[PageContent(page_number=1, text=text, method="table")],
    )


# ── Image parsing (OCR) ─────────────────────────────────────────────────
def _parse_image(path: Path) -> IngestedDocument:
    """Run Tesseract OCR on an image file (Arabic + English).

    Raises:
        RuntimeError: If Tesseract is not installed.
    """
    try:
        import pytesseract
    except ImportError:
        raise RuntimeError("pytesseract is required for image parsing") from None

    img = Image.open(path)

    try:
        text = pytesseract.image_to_string(img, lang="ara+eng")
    except pytesseract.TesseractNotFoundError:
        raise RuntimeError(
            "Tesseract binary not found. Install with: brew install tesseract tesseract-lang"
        ) from None

    text = _clean_text(text)

    return IngestedDocument(
        source_file=path.name,
        file_type=path.suffix.lstrip(".").lower(),
        page_count=1,
        language=None,
        pages=[PageContent(page_number=1, text=text, method="ocr")],
    )


# ── Text utilities ───────────────────────────────────────────────────────
def _clean_text(text: str) -> str:
    """Normalize whitespace, fix common OCR artifacts, strip control chars."""
    # Remove null bytes and control characters (keep newlines and tabs)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
    # Collapse runs of 3+ newlines into 2
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Collapse runs of spaces/tabs on a single line
    text = re.sub(r"[^\S\n]+", " ", text)
    # Strip trailing whitespace per line
    text = "\n".join(line.rstrip() for line in text.splitlines())
    return text.strip()


def _detect_language(text: str) -> str | None:
    """Simple heuristic language detection based on character ranges.

    Returns:
        ``"ar"`` if predominantly Arabic, ``"en"`` if Latin, ``"ar+en"`` if
        mixed, or ``None`` if the text is too short to tell.
    """
    if len(text) < 20:
        return None

    # Count Arabic-script characters (including Arabic-Indic digits)
    arabic_chars = len(re.findall(r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\u0660-\u0669]", text))
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
