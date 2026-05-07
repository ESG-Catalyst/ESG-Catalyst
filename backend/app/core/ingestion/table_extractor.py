"""Table and spreadsheet extraction — XLSX, XLS, CSV.

Preserves row-column relationships as pipe-delimited text.

Usage:
    from app.core.ingestion.table_extractor import parse_spreadsheet, parse_csv
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import structlog

logger = structlog.get_logger(__name__)


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
        df = df.fillna("")
        lines: list[str] = [f"=== Sheet: {sheet_name} ===", ""]

        if len(df.columns) > 0:
            lines.append(" | ".join(str(c) for c in df.columns))
            lines.append("-" * 40)

        for _, row in df.iterrows():
            row_text = " | ".join(str(v) for v in row.values if str(v).strip())
            if row_text.strip():
                lines.append(row_text)

        pages.append((idx, "\n".join(lines)))

    return pages


def parse_csv(path: Path) -> str:
    """Parse a CSV file into a single page of pipe-delimited text.

    Args:
        path: Path to the CSV file.

    Returns:
        Text string of the CSV content.

    Raises:
        ValueError: If encoding cannot be detected.
    """
    df = None
    for encoding in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            df = pd.read_csv(path, dtype=str, encoding=encoding)
            break
        except UnicodeDecodeError:
            continue

    if df is None:
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

    return "\n".join(lines)
