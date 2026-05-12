"""OCR utilities — Tesseract Arabic+English for scanned PDFs and images.

Gracefully degrades when Tesseract is not installed: logs a warning and
returns empty text instead of crashing the pipeline.

Usage:
    from app.core.ingestion.ocr import ocr_pdf_page, parse_image, clean_text
"""

from __future__ import annotations

import re
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)


# ── Tesseract availability cache ─────────────────────────────────────────
_TESSERACT_CHECKED = False
_TESSERACT_AVAILABLE = False
_TESSERACT_LANGS: set[str] = set()


def _check_tesseract() -> bool:
    """Check once whether Tesseract is installed and cache the result.

    Also discovers which language packs are available so we can pick
    the best ``lang`` parameter (e.g. ``ara+eng`` vs ``eng`` only).
    """
    global _TESSERACT_CHECKED, _TESSERACT_AVAILABLE, _TESSERACT_LANGS

    if _TESSERACT_CHECKED:
        return _TESSERACT_AVAILABLE

    _TESSERACT_CHECKED = True

    try:
        import pytesseract
    except ImportError:
        logger.warning("ocr.check", available=False, reason="pytesseract not installed")
        return False

    try:
        langs = pytesseract.get_languages()
        _TESSERACT_LANGS = set(langs)
        _TESSERACT_AVAILABLE = True
        logger.info("ocr.check", available=True, languages=sorted(_TESSERACT_LANGS))
    except Exception:
        logger.warning("ocr.check", available=False, reason="tesseract binary not found")

    return _TESSERACT_AVAILABLE


def _best_lang() -> str:
    """Return the best Tesseract ``lang`` string given installed packs.

    Prefers ``ara+eng`` for bilingual Egyptian documents.
    Falls back to ``eng`` if Arabic pack is missing, or ``osd`` as last resort.
    """
    if "ara" in _TESSERACT_LANGS and "eng" in _TESSERACT_LANGS:
        return "ara+eng"
    if "eng" in _TESSERACT_LANGS:
        return "eng"
    if "ara" in _TESSERACT_LANGS:
        return "ara"
    # Tesseract always has 'osd' (orientation/script detection)
    return "eng"


# ── Text cleaning ────────────────────────────────────────────────────────
def clean_text(text: str) -> str:
    """Normalize whitespace, fix common OCR artifacts, strip control chars."""
    # Remove control characters (keep tabs, newlines, carriage returns)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
    # Collapse 3+ newlines into 2
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Collapse horizontal whitespace (not newlines) into single space
    text = re.sub(r"[^\S\n]+", " ", text)
    # Strip trailing whitespace per line
    text = "\n".join(line.rstrip() for line in text.splitlines())
    return text.strip()


# ── OCR for PDF pages ────────────────────────────────────────────────────
def ocr_pdf_page(page) -> str:  # page: fitz.Page
    """Render a PDF page to an image and run Tesseract OCR.

    Returns empty string if Tesseract is not installed or fails.

    Args:
        page: A ``fitz.Page`` object from PyMuPDF.

    Returns:
        Extracted text string, or empty string if OCR unavailable.
    """
    if not _check_tesseract():
        return ""

    try:
        import pytesseract
        from PIL import Image, ImageFilter
    except ImportError:
        return ""

    # Render at 300 DPI for good OCR quality
    pix = page.get_pixmap(dpi=300)
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

    # Preprocessing: convert to grayscale and sharpen for better OCR
    img = img.convert("L")
    img = img.filter(ImageFilter.SHARPEN)

    try:
        lang = _best_lang()
        text = pytesseract.image_to_string(img, lang=lang)
        return clean_text(text)
    except Exception as exc:
        logger.warning("ocr.pdf_page_failed", error=str(exc))
        return ""


# ── OCR for standalone images ────────────────────────────────────────────
def parse_image(path: Path) -> tuple[str, str]:
    """Run Tesseract OCR on an image file.

    Gracefully returns empty text if Tesseract is not installed.

    Args:
        path: Path to the image file.

    Returns:
        Tuple of ``(extracted_text, file_type_str)``.
        If OCR is unavailable, ``extracted_text`` will be empty.
    """
    file_type = path.suffix.lstrip(".").lower()

    if not _check_tesseract():
        logger.warning(
            "ocr.image_skipped",
            file=path.name,
            reason="Tesseract not available — image will have no text",
        )
        return "", file_type

    try:
        import pytesseract
        from PIL import Image, ImageFilter
    except ImportError:
        return "", file_type

    img = Image.open(path)

    # Preprocessing: convert to grayscale and sharpen
    if img.mode != "L":
        img = img.convert("L")
    img = img.filter(ImageFilter.SHARPEN)

    try:
        lang = _best_lang()
        text = pytesseract.image_to_string(img, lang=lang)
    except Exception as exc:
        logger.warning("ocr.image_failed", file=path.name, error=str(exc))
        return "", file_type

    return clean_text(text), file_type
