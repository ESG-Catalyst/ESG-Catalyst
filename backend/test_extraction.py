"""M3 extraction test — runs the full M1→M2→M3 chain on the test PDF.

Mirrors the orchestration in workers/tasks.py:
    ingest → chunk → classify → filter to relevant chunks → extract.

Verifies the ModelRouter free-tier fallback (Blocker 2 fix). If the primary
model returns HTTP 402 / "key limit exceeded" / insufficient credits, the
router silently switches to MODEL_EXTRACTION_FALLBACK.
"""
import asyncio
import sys
from pathlib import Path
from uuid import uuid4

# Force UTF-8 stdout on Windows so we can print non-ASCII evidence/notes.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

PDF = str(PROJECT_ROOT / "data" / "ADCB - ESG-report-english.pdf")

# Run a small subset to keep the test fast and cheap on the free fallback.
TEST_INDICATORS = ["GRI 2-1", "GRI 302-1", "GRI 305-1", "GRI 405-1"]


async def main() -> None:
    from app.config import settings
    from app.core.extraction.extractor import extract_metrics
    from app.core.ingestion.parser import ingest_document
    from app.core.nlp.chunker import chunk_document
    from app.core.nlp.classifier import classify_chunks

    print(f"Primary model : {settings.model_extraction}")
    print(f"Fallback model: {settings.model_extraction_fallback}\n")

    # ── M1: Ingest ──────────────────────────────────────────────────────
    print("M1: Ingesting PDF...")
    doc = ingest_document(PDF)
    print(f"  -> {doc.page_count} pages, {len(doc.full_text):,} chars\n")

    # ── M2a: Chunk ─────────────────────────────────────────────────────
    print("M2a: Chunking...")
    chunks = chunk_document(doc)
    print(f"  -> {len(chunks)} chunks\n")

    # ── M2b: Classify + filter to ESG-relevant chunks ──────────────────
    print("M2b: Classifying ESG relevance (ClimateBERT + keywords)...")
    classified = classify_chunks(chunks, threshold=0.3, use_climate_model=True)
    relevant = [c.chunk for c in classified if c.is_relevant]
    print(f"  -> {len(relevant)} relevant of {len(classified)} total\n")

    # Match tasks.py:163-171 — join relevant chunk text, fall back to full
    # text if classification filtered too aggressively.
    if len(relevant) >= 3:
        extraction_text = "\n\n".join(c.text for c in relevant)
        print(f"  -> extraction_text: {len(extraction_text):,} chars from relevant chunks")
    else:
        extraction_text = doc.full_text
        print(f"  -> extraction_text: {len(extraction_text):,} chars (full doc — too few relevant)")
    print()

    # ── M3: Extract ────────────────────────────────────────────────────
    print(f"M3: Extracting {len(TEST_INDICATORS)} indicators: {TEST_INDICATORS}")
    metrics = await extract_metrics(
        document_text=extraction_text,
        company_id=uuid4(),
        report_id=uuid4(),
        source_file=Path(PDF).name,
        indicator_codes=TEST_INDICATORS,
    )

    print(f"\n=== {len(metrics)} ExtractedMetric outputs ===\n")
    for i, m in enumerate(metrics, 1):
        print(f"[{i}] gri_code   : {m.gri_code}")
        print(f"    label      : {m.label}")
        print(f"    value      : {m.value}")
        print(f"    unit       : {m.unit}")
        print(f"    original   : {m.original_value} {m.original_unit or ''}")
        print(f"    confidence : {m.confidence:.2f}")
        print(f"    status     : {m.status.value}")
        if m.evidence_chunk:
            print(f"    evidence   : {m.evidence_chunk[:140]}")
        if m.note:
            print(f"    note       : {m.note[:140]}")
        print()


if __name__ == "__main__":
    asyncio.run(main())
