"""OCR utilities — Tesseract Arabic+English for scanned PDFs and images.

Usage:
    from app.core.ingestion.ocr import ocr_pdf_page, parse_image, clean_text
"""

from __future__ import annotations

import re
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)


def clean_text(text: str) -> str:
    """Normalize whitespace, fix common OCR artifacts, strip control chars."""
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[^\S\n]+", " ", text)
    text = "\n".join(line.rstrip() for line in text.splitlines())
    return text.strip()


def ocr_pdf_page(page) -> str:  # page: fitz.Page
    """Render a PDF page to an image and run Tesseract OCR (Arabic + English).

    Returns empty string if Tesseract is not installed.

    Args:
        page: A ``fitz.Page`` object from PyMuPDF.

    Returns:
        Extracted text string, or empty string if OCR unavailable.
    """
    try:
        import pytesseract
    except ImportError:
        logger.warning("ocr.unavailable", reason="pytesseract not installed")
        return ""

    try:
        from PIL import Image
    except ImportError:
        logger.warning("ocr.unavailable", reason="Pillow not installed")
        return ""

    pix = page.get_pixmap(dpi=300)
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

    try:
        text = pytesseract.image_to_string(img, lang="ara+eng")
        return clean_text(text)
    except pytesseract.TesseractNotFoundError:
        logger.warning("ocr.unavailable", reason="tesseract binary not found")
        return ""


def parse_image(path: Path) -> tuple[str, str]:
    """Run Tesseract OCR on an image file (Arabic + English).

    Args:
        path: Path to the image file.

    Returns:
        Tuple of (extracted_text, file_type_str).

    Raises:
        RuntimeError: If Tesseract is not installed.
    """
    try:
        import pytesseract
    except ImportError:
        raise RuntimeError("pytesseract is required for image parsing") from None

    try:
        from PIL import Image
    except ImportError:
        raise RuntimeError("Pillow is required for image parsing") from None

    img = Image.open(path)

    try:
        text = pytesseract.image_to_string(img, lang="ara+eng")
    except pytesseract.TesseractNotFoundError:
        raise RuntimeError(
            "Tesseract binary not found. Install: https://github.com/UB-Mannheim/tesseract/wiki"
        ) from None

    return clean_text(text), path.suffix.lstrip(".").lower()
