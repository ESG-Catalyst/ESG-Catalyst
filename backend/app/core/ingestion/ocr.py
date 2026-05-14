"""OCR utilities — Tesseract Arabic+English for scanned PDFs and images.

.. note::
    **Deferred to a later phase.**
    The Tesseract-based functions (``ocr_pdf_page``, ``parse_image``) are
    commented out and will be re-enabled when scanned-PDF support is
    prioritised.  ``clean_text`` is still active — it is used to normalise
    digitally-extracted text from PyMuPDF.

Usage:
    from app.core.ingestion.ocr import clean_text
"""

from __future__ import annotations

import re
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)


# ── Tesseract availability cache (deferred — OCR not active) ──────────────────
# TODO: un-comment the block below when Tesseract OCR phase is implemented.
#
# _TESSERACT_CHECKED = False
# _TESSERACT_AVAILABLE = False
# _TESSERACT_LANGS: set[str] = set()
#
#
# def _check_tesseract() -> bool:
#     """Check once whether Tesseract is installed and cache the result."""
#     global _TESSERACT_CHECKED, _TESSERACT_AVAILABLE, _TESSERACT_LANGS
#     if _TESSERACT_CHECKED:
#         return _TESSERACT_AVAILABLE
#     _TESSERACT_CHECKED = True
#     try:
#         import pytesseract
#     except ImportError:
#         logger.warning("ocr.check", available=False, reason="pytesseract not installed")
#         return False
#     try:
#         langs = pytesseract.get_languages()
#         _TESSERACT_LANGS = set(langs)
#         _TESSERACT_AVAILABLE = True
#         logger.info("ocr.check", available=True, languages=sorted(_TESSERACT_LANGS))
#     except Exception:
#         logger.warning("ocr.check", available=False, reason="tesseract binary not found")
#     return _TESSERACT_AVAILABLE
#
#
# def _best_lang() -> str:
#     """Return the best Tesseract lang string given installed packs."""
#     if "ara" in _TESSERACT_LANGS and "eng" in _TESSERACT_LANGS:
#         return "ara+eng"
#     if "eng" in _TESSERACT_LANGS:
#         return "eng"
#     if "ara" in _TESSERACT_LANGS:
#         return "ara"
#     return "eng"


# ── Text cleaning ─────────────────────────────────────────────────────────────

# Arabic-Indic digit map: U+0660–U+0669 -> ASCII 0-9
_ARABIC_INDIC_TABLE = str.maketrans(
    "\u0660\u0661\u0662\u0663\u0664\u0665\u0666\u0667\u0668\u0669",
    "0123456789",
)


def clean_text(text: str) -> str:
    """Normalize whitespace, fix Arabic artifacts, strip control chars.

    Applied to all digitally-extracted text (Arabic and English alike).
    Safe to call on already-clean text — idempotent for most inputs.

    Steps applied in order:

    1. Strip C0 control characters (keep ``\\t``, ``\\n``, ``\\r``).
    2. Strip Unicode BiDi directional controls that confuse LLM tokenizers
       (U+200B–U+200F, U+202A–U+202E, U+FEFF BOM, U+00AD soft hyphen).
    3. Remove kashida / tatweel (U+0640) — decorative Arabic elongation glyph.
    4. Normalize Arabic-Indic digits (U+0660–U+0669) to ASCII 0–9.
    5. Collapse runs of 3+ newlines to two newlines.
    6. Collapse horizontal whitespace runs to a single space.
    7. Strip trailing whitespace from each line.
    """
    # 1. C0 control characters (keep \t \n \r)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
    # 2. BiDi control characters
    text = re.sub(r"[\u200b-\u200f\u202a-\u202e\ufeff\u00ad]", "", text)
    # 3. Kashida / tatweel — purely decorative, never carries meaning
    text = text.replace("\u0640", "")
    # 4. Arabic-Indic digits -> ASCII
    text = text.translate(_ARABIC_INDIC_TABLE)
    # 5. Collapse excessive newlines
    text = re.sub(r"\n{3,}", "\n\n", text)
    # 6. Collapse horizontal whitespace
    text = re.sub(r"[^\S\n]+", " ", text)
    # 7. Strip trailing whitespace per line
    text = "\n".join(line.rstrip() for line in text.splitlines())
    return text.strip()


# ── OCR for PDF pages (deferred — not active) ────────────────────────────────
# TODO: un-comment when Tesseract OCR phase is implemented.
#
# def ocr_pdf_page(page) -> str:  # page: fitz.Page
#     """Render a PDF page to an image and run Tesseract OCR.
#
#     Returns empty string if Tesseract is not installed or fails.
#     """
#     if not _check_tesseract():
#         return ""
#     try:
#         import pytesseract
#         from PIL import Image, ImageFilter
#     except ImportError:
#         return ""
#     # Render at 300 DPI for good OCR quality
#     pix = page.get_pixmap(dpi=300)
#     img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
#     # Preprocessing: convert to grayscale and sharpen for better OCR
#     img = img.convert("L")
#     img = img.filter(ImageFilter.SHARPEN)
#     try:
#         lang = _best_lang()
#         text = pytesseract.image_to_string(img, lang=lang)
#         return clean_text(text)
#     except Exception as exc:
#         logger.warning("ocr.pdf_page_failed", error=str(exc))
#         return ""


# ── OCR for standalone images (deferred — not active) ────────────────────────
# TODO: un-comment when Tesseract OCR phase is implemented.
#
# def parse_image(path: Path) -> tuple[str, str]:
#     """Run Tesseract OCR on an image file.
#
#     Gracefully returns empty text if Tesseract is not installed.
#     """
#     file_type = path.suffix.lstrip(".").lower()
#     if not _check_tesseract():
#         logger.warning(
#             "ocr.image_skipped",
#             file=path.name,
#             reason="Tesseract not available — image will have no text",
#         )
#         return "", file_type
#     try:
#         import pytesseract
#         from PIL import Image, ImageFilter
#     except ImportError:
#         return "", file_type
#     img = Image.open(path)
#     if img.mode != "L":
#         img = img.convert("L")
#     img = img.filter(ImageFilter.SHARPEN)
#     try:
#         lang = _best_lang()
#         text = pytesseract.image_to_string(img, lang=lang)
#     except Exception as exc:
#         logger.warning("ocr.image_failed", file=path.name, error=str(exc))
#         return "", file_type
#     return clean_text(text), file_type
