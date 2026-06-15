"""Table and spreadsheet extraction — XLSX, XLS, CSV.

Preserves row-column relationships as pipe-delimited text.
Adds summary statistics (row/column counts, numeric totals) at the end
of each sheet so the downstream extractor has pre-computed aggregates.

Usage:
    from app.core.ingestion.table_extractor import parse_spreadsheet, parse_csv
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd
import structlog

logger = structlog.get_logger(__name__)

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
    """Reconstruct Arabic ligatures when text is in visual presentation form.

    Returns the text unchanged if it is already in logical Unicode order
    (U+0600–U+06FF). Only applies reshape+BiDi for presentation-form glyphs
    (U+FB50–U+FEFF).

    Args:
        text: Raw cell text from a spreadsheet.

    Returns:
        Text in correct logical Unicode reading order.
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
            "table_extractor.arabic_fix_skipped",
            reason="arabic-reshaper or python-bidi not installed",
        )
        return text
    try:
        reshaped = arabic_reshaper.reshape(text)
        return get_display(reshaped)
    except Exception as exc:
        # arabic_reshaper / python-bidi can raise varied exception types; this
        # is a best-effort cosmetic fixup, so stay fail-safe and return the
        # original text on ANY failure (logged for diagnosis).
        logger.warning("table_extractor.arabic_fix_failed", error=str(exc))
        return text


def _render_dataframe(df: pd.DataFrame, sheet_label: str | None = None) -> str:
    """Render a DataFrame as pipe-delimited text with optional summary."""
    # Drop fully empty rows and columns
    df = df.dropna(how="all").dropna(axis=1, how="all")
    df = df.fillna("")
    lines: list[str] = []

    if sheet_label:
        lines.append(f"=== Sheet: {sheet_label} ===")
        lines.append("")

    if len(df.columns) > 0:
        lines.append(" | ".join(str(c) for c in df.columns))
        lines.append("-" * 40)

    for _, row in df.iterrows():
        values = []
        for v in row.values:
            cell_str = str(v).strip().replace("\n", " ")
            if cell_str and _arabic_char_ratio(cell_str) >= 0.15:
                cell_str = _fix_arabic_text(cell_str)
            values.append(cell_str)
            
        row_text = " | ".join(values)
        if row_text.strip(" |"):
            lines.append(row_text)

    n_rows = len(df)
    n_cols = len(df.columns)
    lines.append("")
    lines.append(f"[Summary: {n_rows} rows x {n_cols} columns]")

    for col in df.columns:
        numeric = pd.to_numeric(df[col], errors="coerce")
        non_null = numeric.dropna()
        if len(non_null) > 0:
            lines.append(
                f"  {col}: min={non_null.min():,.2f}, "
                f"max={non_null.max():,.2f}, "
                f"sum={non_null.sum():,.2f}"
            )

    return "\n".join(lines)



def parse_spreadsheet(path: Path) -> list[tuple[int, str]]:
    """Parse XLSX/XLS into (page_number, text) tuples, one per sheet.

    Args:
        path: Path to the spreadsheet file.

    Returns:
        List of ``(sheet_index, text)`` tuples.
    """
    sheets = pd.read_excel(path, sheet_name=None, dtype=str)
    pages: list[tuple[int, str]] = []

    for idx, (sheet_name, df) in enumerate(sheets.items(), start=1):
        text = _render_dataframe(df, sheet_label=sheet_name)
        pages.append((idx, text))
        logger.info(
            "table_extractor.sheet",
            file=path.name,
            sheet=sheet_name,
            rows=len(df),
            cols=len(df.columns),
        )

    return pages


def parse_csv(path: Path) -> str:
    """Parse a CSV file into a single page of pipe-delimited text.

    Tries multiple encodings to handle Arabic / Latin content.

    Args:
        path: Path to the CSV file.

    Returns:
        Text string of the CSV content.

    Raises:
        ValueError: If encoding cannot be detected.
    """
    df = None
    used_encoding = None
    # Order matters: try strict/likely-correct encodings first and keep the
    # never-failing catch-all (latin-1 maps all 256 byte values, so it NEVER
    # raises UnicodeDecodeError) dead last. If latin-1 came earlier, a genuine
    # UTF-8 or Windows-Arabic (cp1256) / ISO-8859-6 CSV would be silently
    # mis-decoded into mojibake (e.g. an em-dash "—" → "â€"") instead of
    # falling through to the codec that actually matches the bytes.
    for encoding in ("utf-8-sig", "utf-8", "cp1256", "iso-8859-6", "latin-1"):
        try:
            df = pd.read_csv(path, dtype=str, encoding=encoding)
            used_encoding = encoding
            break
        except UnicodeDecodeError:
            continue

    if df is None:
        raise ValueError(f"Cannot decode CSV file: {path.name}")

    logger.info(
        "table_extractor.csv",
        file=path.name,
        encoding=used_encoding,
        rows=len(df),
        cols=len(df.columns),
    )
    return _render_dataframe(df)
