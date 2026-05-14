# Ingestion Module: Arabic Support Improvements

## Overview
This session focused on improving the document ingestion pipeline (`backend/app/core/ingestion/`) to robustly handle Arabic ESG and financial reports. A gap analysis was performed against 7 real-world Arabic test files, identifying issues with PyMuPDF's RTL text extraction, OCR preprocessing, and text cleaning.

As part of this effort, Tesseract OCR for scanned pages and images was **deferred to a later phase** to focus on accurately extracting digitally embedded Arabic text, which is the most common format.

## Changes Implemented

### 1. `backend/app/core/ingestion/pdf_parser.py`
- **Arabic BiDi & Reshaping**: Added an `_arabic_char_ratio()` heuristic to detect pages with significant Arabic content (>= 15%). For these pages, applied `arabic-reshaper` (to reconstruct split ligatures) and `python-bidi` (to restore RTL reading order) via a new `_fix_arabic_text()` helper. This fixes the critical issue of PyMuPDF extracting Arabic text backwards or with broken ligatures.
- **OCR Deferral**: Commented out the `ocr_pdf_page` import and the fallback logic for scanned pages. Pages below the digital text threshold are now skipped with a warning log rather than triggering OCR.

### 2. `backend/app/core/ingestion/ocr.py`
- **Enhanced `clean_text()`**: Upgraded the text normalization function to handle Arabic-specific artifacts safely:
  - Strips Unicode BiDi directional control characters (e.g., LRM, RLM, ZWNJ) that confuse LLM tokenizers.
  - Removes Kashida/Tatweel (U+0640) - purely decorative Arabic elongation glyphs.
  - Normalizes Arabic-Indic digits (٠-٩) to ASCII numerals (0-9) using a translation table.
- **OCR Deferral**: Commented out `_check_tesseract()`, `_best_lang()`, `ocr_pdf_page()`, and `parse_image()` with clear `TODO` notes for a later phase.

### 3. `backend/app/core/ingestion/parser.py`
- **Language Detection Threshold**: Lowered the Arabic character ratio threshold for the "ar" classification from 0.60 to 0.45. This correctly accounts for MENA ESG reports that heavily embed Latin script for GRI codes, units (e.g., tCO2e), and brand names.
- **Image Parsing Deferral**: Updated `_parse_image()` to return an empty `IngestedDocument` and log a warning instead of calling the deferred `parse_image` function from `ocr.py`.

### 4. Dependencies
- **`requirements-base.txt`**: Added `arabic-reshaper>=3.0.0` and `python-bidi>=0.4.2` to support the RTL extraction fixes in the API and Celery worker.
- **`requirements.txt`**: Updated the Tesseract note to clearly indicate that system OCR installation is currently DEFERRED.

## Test Results
Running `data/ingestion_test_files/test_ingestion.py` after the changes yielded an 11/14 pass rate. 
- All 7 Arabic PDF reports successfully parsed, with Arabic pages correctly tagged as `digital+arabic` or `digital+arabic+tables`.
- English documents (`.pdf`, `.xlsx`, `.csv`) continued to parse correctly without being affected.
- The 3 "failures" were expected: `.json` (unsupported format), `.png` (OCR deferred), and `.docx` (missing `python-docx` dependency in the venv, which the user subsequently installed).

## Next Steps / Instructions
- **Iteration 2 MLflow Validation**: The pipeline is now ready to process Arabic documents through to the LLM extractor. The next step is to run a full pipeline extraction on an Arabic report and compare the MLflow confidence metrics to ensure the BiDi text is yielding high-quality extractions.
- **Later Phase - Scanned Documents**: When prioritizing scanned PDFs and images, uncomment the Tesseract functions in `ocr.py` and `pdf_parser.py`, and implement the recommended OCR enhancements (e.g., OpenCV Otsu binarization, `--oem 1 --psm 6` Tesseract configs).
