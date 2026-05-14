"""Table and spreadsheet extraction — XLSX, XLS, CSV.

Preserves row-column relationships as pipe-delimited text.
Adds summary statistics (row/column counts, numeric totals) at the end
of each sheet so the downstream extractor has pre-computed aggregates.

Usage:
    from app.core.ingestion.table_extractor import parse_spreadsheet, parse_csv
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import structlog

logger = structlog.get_logger(__name__)


def _render_dataframe(df: pd.DataFrame, sheet_label: str | None = None) -> str:
    """Render a DataFrame as pipe-delimited text with optional summary.

    Args:
        df: The DataFrame to render.
        sheet_label: Optional sheet name for the header line.

    Returns:
        Pipe-delimited text representation.
    """
    df = df.fillna("")
    lines: list[str] = []

    if sheet_label:
        lines.append(f"=== Sheet: {sheet_label} ===")
        lines.append("")

    # Header row
    if len(df.columns) > 0:
        lines.append(" | ".join(str(c) for c in df.columns))
        lines.append("-" * 40)

    # Data rows — skip fully empty rows
    for _, row in df.iterrows():
        values = [str(v) for v in row.values if str(v).strip()]
        row_text = " | ".join(values)
        if row_text.strip():
            lines.append(row_text)

    # Summary: row count and numeric column aggregates
    n_rows = len(df)
    n_cols = len(df.columns)
    lines.append("")
    lines.append(f"[Summary: {n_rows} rows x {n_cols} columns]")

    # Detect numeric columns and add min/max/sum
    for col in df.columns:
        # Try to parse the column as numeric
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
    for encoding in ("utf-8", "utf-8-sig", "latin-1", "cp1256", "iso-8859-6"):
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
