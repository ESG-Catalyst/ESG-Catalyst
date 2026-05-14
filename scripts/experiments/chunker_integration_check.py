"""Compare old block_merge vs new sentence_window via the integrated chunker.

Apples-to-apples: both strategies are scored with the *current* 3-voter
ensemble classifier (post-C3). Numbers in A1 used ClimateBERT-only, so
this overrides the "ESG-passed" delta for the session log.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from app.core.ingestion.parser import ingest_document
from app.core.nlp.chunker import chunk_document
from app.core.nlp.classifier import classify_chunks


PDF = REPO_ROOT / "data" / "ingestion_test_files" / "en_beltone_report_summary.pdf"
OUT = Path(__file__).parent / "results" / "chunker_integration_check.json"


def run(strategy: str, doc) -> dict:
    t0 = time.time()
    chunks = chunk_document(doc, strategy=strategy)
    t_chunk = time.time() - t0
    t0 = time.time()
    classified = classify_chunks(chunks, threshold=0.3)
    t_clf = time.time() - t0
    relevant = [c for c in classified if c.esg_relevant]
    by_p = {"E": 0, "S": 0, "G": 0}
    for c in relevant:
        if c.pillar in by_p:
            by_p[c.pillar] += 1
    return {
        "strategy": strategy,
        "n_chunks": len(chunks),
        "n_esg_relevant": len(relevant),
        "pct_esg_relevant": round(100 * len(relevant) / max(len(chunks), 1), 2),
        "E": by_p["E"], "S": by_p["S"], "G": by_p["G"],
        "elapsed_chunking_s": round(t_chunk, 2),
        "elapsed_classify_s": round(t_clf, 1),
    }


def main() -> int:
    print(f"Ingesting {PDF.name} ...")
    doc = ingest_document(PDF)
    print(f"  pages={doc.page_count} chars={len(doc.full_text)}")

    print("--- block_merge ---")
    old = run("block_merge", doc)
    print(f"  chunks={old['n_chunks']} esg={old['n_esg_relevant']} ({old['pct_esg_relevant']}%) "
          f"E/S/G={old['E']}/{old['S']}/{old['G']} ({old['elapsed_classify_s']}s)")

    print("--- sentence_window ---")
    new = run("sentence_window", doc)
    print(f"  chunks={new['n_chunks']} esg={new['n_esg_relevant']} ({new['pct_esg_relevant']}%) "
          f"E/S/G={new['E']}/{new['S']}/{new['G']} ({new['elapsed_classify_s']}s)")

    print()
    print("OLD (block_merge)  ->  NEW (sentence_window)")
    print(f"  n_chunks       : {old['n_chunks']:>5}  ->  {new['n_chunks']:>5}   "
          f"delta={new['n_chunks'] - old['n_chunks']:+d}")
    print(f"  esg_relevant   : {old['n_esg_relevant']:>5}  ->  {new['n_esg_relevant']:>5}   "
          f"delta={new['n_esg_relevant'] - old['n_esg_relevant']:+d}")
    print(f"  E              : {old['E']:>5}  ->  {new['E']:>5}   delta={new['E'] - old['E']:+d}")
    print(f"  S              : {old['S']:>5}  ->  {new['S']:>5}   delta={new['S'] - old['S']:+d}")
    print(f"  G              : {old['G']:>5}  ->  {new['G']:>5}   delta={new['G'] - old['G']:+d}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(
        {"pdf": str(PDF), "old_block_merge": old, "new_sentence_window": new},
        indent=2,
    ), encoding="utf-8")
    print(f"\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
