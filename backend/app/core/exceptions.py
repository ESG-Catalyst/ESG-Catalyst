"""Shared exception hierarchy for ESG Catalyst.

All pipeline-level errors inherit from ``ESGCatalystError`` so callers can
catch the whole family with a single ``except ESGCatalystError`` clause, or
narrow to a specific stage with a subclass.

Design rules
------------
- Pure definitions only — no heavy imports (no torch / transformers / DB).
- Every class carries a short docstring that explains *when* it is raised.
- Adoption is incremental: ``router.py`` and ``tasks.py`` raise these now;
  other modules will adopt them in later iterations.

Hierarchy
---------
::

    ESGCatalystError (base)
    ├── IngestionError        – M1: file parsing / OCR failures
    ├── ExtractionError       – M3: LLM extraction failures
    │   └── LLMUnavailableError  – both primary AND fallback model failed
    ├── ScoringError          – M4: scorer / gap-analysis failures
    └── ReportError           – M5: builder / narrative / renderer failures
"""

from __future__ import annotations


class ESGCatalystError(Exception):
    """Base class for all ESG Catalyst pipeline errors.

    Catch this to handle any pipeline failure without caring which stage
    produced it. Carry the original cause in the ``__cause__`` chain
    (i.e. use ``raise ESGCatalystError(...) from original_exc``).
    """


class IngestionError(ESGCatalystError):
    """Raised by M1 (ingestion / chunking) when a file cannot be parsed.

    Examples
    --------
    - PyMuPDF / python-docx cannot open the file.
    - OCR returns empty text on an image-only PDF.
    - File is password-protected or corrupted.
    """


class ExtractionError(ESGCatalystError):
    """Raised by M3 (extraction) when metric extraction fails.

    Examples
    --------
    - LLM returns malformed JSON that cannot be repaired.
    - ChromaDB retrieval is unavailable and the fallback also fails.
    - A required indicator prompt cannot be built.
    """


class LLMUnavailableError(ExtractionError):
    """Raised when *all* configured LLM models (primary + fallback) fail.

    This is a subclass of ``ExtractionError`` so existing ``except
    ExtractionError`` clauses still catch it. Callers that need to
    distinguish "LLM completely down" from "extraction logic error" can
    narrow to this class.

    ``router.py`` raises this after the fallback model also returns a
    billing / quota / 5xx error, ensuring the failure is never silently
    swallowed.

    HTTP mapping (for FastAPI exception handlers)
    ---------------------------------------------
    - ``LLMUnavailableError`` → HTTP 503 Service Unavailable
    - Other ``ExtractionError`` → HTTP 422 Unprocessable Entity
    """


class ScoringError(ESGCatalystError):
    """Raised by M4 (scorer / gap-analysis) when scoring cannot complete.

    Examples
    --------
    - Unknown sector that cannot be resolved to a fallback.
    - ``gri_indicators.json`` is missing required fields.
    - Arithmetic error in weighted aggregation (e.g. zero denominator).
    """


class ReportError(ESGCatalystError):
    """Raised by M5 (builder / narrative / renderer) when report generation fails.

    Examples
    --------
    - PDF backend (WeasyPrint + PyMuPDF) both unavailable.
    - Narrative LLM call fails after the fallback is also exhausted.
    - Output directory cannot be created (permissions / disk full).
    """
