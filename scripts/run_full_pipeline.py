"""Full M1-M5 pipeline driver — runs end-to-end on a real PDF and writes a
report file to ``data/generated_reports/``.

Steps:
    M1  Ingestion           parser.ingest_document
    M2  Chunk + Classify    chunker + classifier (filters ESG-relevant chunks)
    M3  Extraction          extractor.extract_metrics  (LLM via ModelRouter)
    M4  Scoring             scorer.score_report
    M5  Report              builder + narrative + renderer (PDF / HTML fallback)

Usage:
    python scripts/run_full_pipeline.py
    python scripts/run_full_pipeline.py --pdf "data/ADCB - ESG-report-english.pdf"

This script is for local verification, not production. It bypasses the
database (no Document/Report rows are persisted) so M5 can be exercised
even when Postgres / Redis are not running.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from uuid import uuid4

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env")


DEFAULT_PDF = PROJECT_ROOT / "data" / "ADCB - ESG-report-english.pdf"
DEFAULT_OUT_DIR = PROJECT_ROOT / "data" / "generated_reports"


async def run(pdf_path: Path, out_dir: Path, company_name: str) -> Path:
    from app.core.extraction.extractor import extract_metrics
    from app.core.ingestion.parser import ingest_document
    from app.core.nlp.chunker import chunk_document
    from app.core.nlp.classifier import classify_chunks
    from app.core.reporting.builder import CompanyProfile, build_report_sections
    from app.core.reporting.narrative import generate_narratives
    from app.core.reporting.renderer import render_pdf
    from app.core.scoring.scorer import score_report

    company_id = uuid4()
    report_id = uuid4()

    print(f"\n[M1] Ingesting {pdf_path.name} ...")
    doc = ingest_document(str(pdf_path))
    print(f"     -> {doc.page_count} pages, {len(doc.full_text):,} chars")

    print("[M2] Chunking + classifying ESG relevance ...")
    chunks = chunk_document(doc)
    classified = classify_chunks(chunks, threshold=0.3, use_climate_model=True)
    relevant = [c.chunk for c in classified if c.is_relevant]
    print(f"     -> {len(chunks)} chunks, {len(relevant)} ESG-relevant")

    if len(relevant) >= 3:
        extraction_text = "\n\n".join(c.text for c in relevant)
    else:
        print("     -> too few relevant chunks; falling back to full text")
        extraction_text = doc.full_text

    print("[M3] Extracting metrics via LLM (with credit fallback) ...")
    metrics = await extract_metrics(
        document_text=extraction_text,
        company_id=company_id,
        report_id=report_id,
        source_file=pdf_path.name,
    )
    print(f"     -> {len(metrics)} metrics produced")
    for m in metrics:
        print(f"        {m.gri_code:>10}  status={m.status.value:<10}  conf={m.confidence:.2f}")

    print("[M4] Scoring against GRI / FRA / SASB ...")
    score = score_report(metrics)
    print(
        f"     -> total={score.total_score}  GRI={score.gri_score}  "
        f"FRA={score.fra_score}  SASB={score.sasb_score}  tier={score.benchmark_tier}"
    )

    print("[M5] Building report sections + narratives + rendering ...")
    company = CompanyProfile(
        name=company_name,
        sector="banking",
        reporting_period="2023",
        headquarters="Abu Dhabi, UAE",
    )
    bundle = build_report_sections(metrics=metrics, score=score, company=company)
    bundle.sections = await generate_narratives(bundle.sections)

    out_dir.mkdir(parents=True, exist_ok=True)
    safe_name = company_name.replace(" ", "_").replace("(", "").replace(")", "")
    output_path = out_dir / f"{safe_name}_ESG_report.pdf"

    final_path = render_pdf(bundle, output_path)
    print(f"     -> written: {final_path}")
    return final_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the full ESG pipeline end-to-end")
    parser.add_argument("--pdf", type=Path, default=DEFAULT_PDF)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--company", type=str, default="Abu Dhabi Commercial Bank (ADCB)")
    args = parser.parse_args()

    if not args.pdf.exists():
        sys.exit(f"PDF not found: {args.pdf}")

    final = asyncio.run(run(args.pdf, args.out_dir, args.company))
    print(f"\nDone. Report at:\n  {final}")


if __name__ == "__main__":
    main()