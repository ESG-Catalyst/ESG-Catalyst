# -*- coding: utf-8 -*-
"""Test script for ingestion module - runs against each file type in test_files."""
import sys
import os
import io
import traceback
from pathlib import Path

# Force UTF-8 output on Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# Add backend to sys.path so we can import the ingestion module
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from app.core.ingestion.parser import ingest_document

TEST_DIR = Path(__file__).parent


def banner(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def test_file(file_path: Path) -> bool:
    """Test ingesting a single file. Returns True on success."""
    banner(f"Testing: {file_path.name}")
    try:
        result = ingest_document(file_path)
        print(f"  [OK] file_type   : {result.file_type}")
        print(f"  [OK] page_count  : {result.page_count}")
        print(f"  [OK] language    : {result.language}")
        print(f"  [OK] total_chars : {len(result.full_text)}")
        for page in result.pages:
            preview = page.text[:300].replace("\n", " | ")
            print(f"  [OK] page {page.page_number} [{page.method}]: {preview}")
        if not result.pages:
            print(f"  [WARN] No pages extracted!")
            return False
        if len(result.full_text) == 0:
            print(f"  [WARN] Empty text extracted!")
            return False
        return True
    except Exception as e:
        print(f"  [FAIL] {type(e).__name__}: {e}")
        traceback.print_exc()
        return False


def main():
    test_files = sorted(TEST_DIR.glob("*"))
    # Skip this script itself and __pycache__
    test_files = [
        f
        for f in test_files
        if f.is_file() and f.name != "test_ingestion.py" and not f.name.startswith("__")
    ]

    print(f"Found {len(test_files)} test files in {TEST_DIR}")
    for f in test_files:
        print(f"  - {f.name} ({f.stat().st_size:,} bytes)")

    results = {}
    for f in test_files:
        results[f.name] = test_file(f)

    banner("SUMMARY")
    for name, ok in results.items():
        status = "[PASS]" if ok else "[FAIL]"
        print(f"  {status}  {name}")

    passed = sum(1 for v in results.values() if v)
    total = len(results)
    print(f"\n  {passed}/{total} passed")

    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
