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


def _clean_cell(v: object) -> str:
    """Stringify, trim, collapse newlines, and logical-order Arabic a cell."""
    cell = str(v).strip().replace("\n", " ")
    if cell.lower() == "nan":
        cell = ""
    if cell and _arabic_char_ratio(cell) >= 0.15:
        cell = _fix_arabic_text(cell)
    return cell


def _is_number(s: str) -> bool:
    """True if the cell is a plain number (ignoring thousands/percent/currency)."""
    s = s.strip().replace(",", "").replace("%", "").replace("EGP", "").strip()
    if not s:
        return False
    try:
        float(s)
        return True
    except ValueError:
        return False


def _detect_header_row(grid: list[list[str]]) -> int | None:
    """Index of the most likely header row near the top of a grid.

    A header is the first row (scanning the top) with at least two non-empty
    cells, none of which is a plain number — i.e. a row of text labels. Rows
    above it (merged titles, subtitles that ``read_excel`` mis-promotes to the
    header) become context. Returns ``None`` when no such row exists (e.g.
    purely numeric tables, or year-only headers like 2021/2022/2023), in which
    case the caller keeps flat pipe rendering — so detection can never make the
    output worse than before.
    """
    for i, row in enumerate(grid[:8]):
        nonempty = [c for c in row if c]
        if len(nonempty) < 2:
            continue
        if any(_is_number(c) for c in nonempty):
            continue
        return i
    return None


def _append_numeric_summary(
    lines: list[str], data_rows: list[list[str]], headers: list[str] | None
) -> None:
    """Append row/col counts and per-column min/max/sum for numeric columns."""
    n_rows = len(data_rows)
    n_cols = max((len(r) for r in data_rows), default=0)
    lines.append("")
    lines.append(f"[Summary: {n_rows} rows x {n_cols} columns]")
    if not headers:
        return
    for j, col_name in enumerate(headers):
        vals: list[float] = []
        for r in data_rows:
            if j < len(r) and _is_number(r[j]):
                vals.append(float(r[j].replace(",", "").replace("%", "").replace("EGP", "").strip()))
        if vals:
            lines.append(
                f"  {col_name}: min={min(vals):,.2f}, "
                f"max={max(vals):,.2f}, sum={sum(vals):,.2f}"
            )


def _render_dataframe(df: pd.DataFrame, sheet_label: str | None = None) -> str:
    """Render a table as text, one self-describing ``Header: value`` row each.

    Each data row repeats its column headers inline (``Count: 4,230 | Value
    (EGP M): 2,980 | ...``). This keeps a row interpretable even after the
    downstream chunker splits a sheet mid-table — the old "header printed once
    at the top" layout stranded the column meaning in a different chunk, so a
    retrieved value row arrived with no labels and the extractor could not bind
    the number to the right field. Row-wise labelling also enriches the chunk
    embedding (the field names sit next to the indicator code), improving
    retrieval recall. Falls back to the flat pipe layout when no header row can
    be identified.
    """
    df = df.dropna(how="all").dropna(axis=1, how="all")
    df = df.fillna("")

    # Rebuild the full grid INCLUDING whatever pandas pulled into df.columns:
    # our sheets carry a merged title in row 1, so the header=0 guess is usually
    # the title, not the real header — folding columns back in lets detection
    # recover the true header wherever it sits.
    header_as_row = [
        "" if str(c).startswith("Unnamed") else _clean_cell(c) for c in df.columns
    ]
    grid: list[list[str]] = [header_as_row]
    grid += [[_clean_cell(v) for v in row] for row in df.values.tolist()]
    grid = [r for r in grid if any(c for c in r)]  # drop fully empty rows

    lines: list[str] = []
    if sheet_label:
        lines.append(f"=== Sheet: {sheet_label} ===")
        lines.append("")

    hdr_idx = _detect_header_row(grid)

    if hdr_idx is None:
        # No identifiable header — keep the original flat rendering (no regression).
        for row in grid:
            row_text = " | ".join(row)
            if row_text.strip(" |"):
                lines.append(row_text)
        _append_numeric_summary(lines, grid, headers=None)
        return "\n".join(lines)

    headers = [h if h else f"Col{j + 1}" for j, h in enumerate(grid[hdr_idx])]

    # Context rows above the header (merged title/subtitle) carry the indicator
    # code + sheet purpose — keep them verbatim so retrieval still anchors on them.
    for row in grid[:hdr_idx]:
        ctx = " ".join(c for c in row if c)
        if ctx:
            lines.append(ctx)

    # Header once (human + retrieval), then self-describing data rows.
    lines.append(" | ".join(headers))
    lines.append("-" * 40)

    data_rows = grid[hdr_idx + 1:]
    for row in data_rows:
        pairs = []
        for j, val in enumerate(row):
            if not val:
                continue
            key = headers[j] if j < len(headers) else f"Col{j + 1}"
            pairs.append(f"{key}: {val}")
        if pairs:
            lines.append(" | ".join(pairs))

    _append_numeric_summary(lines, data_rows, headers=headers)
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
