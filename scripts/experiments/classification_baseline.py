"""Audit ClimateBERT E/S/G bias on the Beltone report (read-only).

Runs M1 ingestion + M2 chunking on the Beltone PDF, then scores every
chunk with ClimateBERT directly (no S/G keyword supplement from
classifier.py). Each passing chunk (score > THRESHOLD) is bucketed
E/S/G/Unknown by a *simple* keyword heuristic that matches the audit
spec, NOT the production classifier's regex sets.

Does NOT mutate any pipeline file. All findings are written to
``scripts/experiments/results/baseline.json`` and logged to the MLflow
experiment ``m2-classification-experiments``.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path
from statistics import mean
from typing import Iterable

# ── Path wiring so this script can be run from the repo root ────────────
REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

# Match the dev-run convention in CLAUDE.md
os.environ.setdefault("PYTHONPATH", str(BACKEND_ROOT))

from app.core.ingestion.parser import ingest_document  # noqa: E402
from app.core.nlp.chunker import chunk_document, Chunk  # noqa: E402


# ── Audit configuration (do not change without team discussion) ─────────
PDF_PATH = REPO_ROOT / "data" / "ingestion_test_files" / "en_beltone_report_summary.pdf"
RESULTS_PATH = Path(__file__).parent / "results" / "baseline.json"
MLFLOW_EXPERIMENT = "m2-classification-experiments"
MLFLOW_RUN_NAME = "baseline-climatebert"
THRESHOLD = 0.3
DOC_LABEL = "beltone"  # spec said "ADCB" but the PDF is Beltone; logging the truth


# ── Simple audit heuristic — intentionally cruder than classifier.py ────
E_KEYWORDS = [
    r"energy", r"emission", r"carbon", r"climate", r"water", r"waste", r"GHG",
]
S_KEYWORDS = [
    r"employee", r"diversity", r"injury", r"community", r"training", r"gender",
]
G_KEYWORDS = [
    r"board", r"governance", r"audit", r"compliance", r"risk", r"director",
]


def _compile(words: Iterable[str]) -> re.Pattern[str]:
    return re.compile(r"\b(?:" + "|".join(words) + r")\b", re.IGNORECASE)


_E_RE = _compile(E_KEYWORDS)
_S_RE = _compile(S_KEYWORDS)
_G_RE = _compile(G_KEYWORDS)


def heuristic_pillar(text: str) -> str:
    """Label a chunk E / S / G / Unknown by raw keyword hit-count.

    Ties (e.g., equal E and S counts) go to the alphabetically earlier
    pillar, which is fine for a bias audit — we just need a consistent rule.
    """
    counts = {
        "E": len(_E_RE.findall(text)),
        "S": len(_S_RE.findall(text)),
        "G": len(_G_RE.findall(text)),
    }
    if max(counts.values()) == 0:
        return "Unknown"
    return max(counts, key=counts.get)


# ── ClimateBERT scoring (direct, no S/G supplement) ─────────────────────
def climate_scores(texts: list[str]) -> list[float]:
    """P(yes) from climatebert/distilroberta-base-climate-detector."""
    from transformers import pipeline as hf_pipeline

    clf = hf_pipeline(
        "text-classification",
        model="climatebert/distilroberta-base-climate-detector",
        top_k=None,
        truncation=True,
        max_length=512,
    )
    truncated = [t[:2000] for t in texts]
    raw = clf(truncated, batch_size=16)
    out: list[float] = []
    for row in raw:
        label_scores = {d["label"]: d["score"] for d in row}
        out.append(label_scores.get("yes", 0.0))
    return out


# ── MLflow (best-effort; audit JSON is authoritative) ───────────────────
def _mlflow_log(params: dict, metrics: dict, artifact_path: Path) -> str | None:
    try:
        import mlflow

        tracking_uri = os.environ.get("MLFLOW_TRACKING_URI", "http://localhost:5001")
        mlflow.set_tracking_uri(tracking_uri)
        mlflow.set_experiment(MLFLOW_EXPERIMENT)
        with mlflow.start_run(run_name=MLFLOW_RUN_NAME) as run:
            mlflow.log_params({k: str(v) for k, v in params.items()})
            mlflow.log_metrics({k: float(v) for k, v in metrics.items()})
            mlflow.log_artifact(str(artifact_path))
            return run.info.run_id
    except Exception as exc:
        print(f"[mlflow] log skipped: {exc}")
        return None


# ── Main ────────────────────────────────────────────────────────────────
def main() -> int:
    if not PDF_PATH.exists():
        print(f"PDF not found: {PDF_PATH}", file=sys.stderr)
        return 1

    print(f"[1/4] Ingesting {PDF_PATH.name} ...")
    t0 = time.time()
    doc = ingest_document(PDF_PATH)
    print(f"      pages={doc.page_count} lang={doc.language} ({time.time()-t0:.1f}s)")

    print("[2/4] Chunking ...")
    t0 = time.time()
    chunks: list[Chunk] = chunk_document(doc)
    print(f"      chunks={len(chunks)} ({time.time()-t0:.1f}s)")

    print("[3/4] Scoring with ClimateBERT ...")
    t0 = time.time()
    scores = climate_scores([c.text for c in chunks])
    print(f"      done ({time.time()-t0:.1f}s)")

    # ── Per-chunk records ───────────────────────────────────────────────
    per_chunk = []
    for c, s in zip(chunks, scores):
        per_chunk.append({
            "chunk_id": c.chunk_id,
            "page_number": c.page_number,
            "section_header": c.section_header,
            "climatebert_score": float(s),
            "passes_threshold": bool(s > THRESHOLD),
            "heuristic_pillar": heuristic_pillar(c.text) if s > THRESHOLD else None,
            "text": c.text,
        })

    passed = [r for r in per_chunk if r["passes_threshold"]]
    filtered = [r for r in per_chunk if not r["passes_threshold"]]
    n_passed = len(passed)
    n_filtered = len(filtered)

    # Pillar distribution among passing chunks
    pillars = {"E": 0, "S": 0, "G": 0, "Unknown": 0}
    pillar_scores: dict[str, list[float]] = {"E": [], "S": [], "G": [], "Unknown": []}
    for r in passed:
        p = r["heuristic_pillar"] or "Unknown"
        pillars[p] += 1
        pillar_scores[p].append(r["climatebert_score"])

    def pct(n: int) -> float:
        return round(100.0 * n / n_passed, 2) if n_passed else 0.0

    pct_E, pct_S, pct_G, pct_unknown = pct(pillars["E"]), pct(pillars["S"]), pct(pillars["G"]), pct(pillars["Unknown"])
    avg_E = round(mean(pillar_scores["E"]), 4) if pillar_scores["E"] else 0.0
    avg_S = round(mean(pillar_scores["S"]), 4) if pillar_scores["S"] else 0.0
    avg_G = round(mean(pillar_scores["G"]), 4) if pillar_scores["G"] else 0.0

    # Example chunks — top 5 S and top 5 G that PASSED (highest ClimateBERT score)
    top_S_passed = sorted(
        [r for r in passed if r["heuristic_pillar"] == "S"],
        key=lambda r: r["climatebert_score"], reverse=True,
    )[:5]
    top_G_passed = sorted(
        [r for r in passed if r["heuristic_pillar"] == "G"],
        key=lambda r: r["climatebert_score"], reverse=True,
    )[:5]

    # FILTERED-OUT S and G — chunks the heuristic *would* label S or G but
    # ClimateBERT scored under the threshold. Show the highest-scoring near-miss
    # examples (most worrying — almost made it, but lost).
    filtered_with_pillar = [
        {**r, "heuristic_pillar_when_filtered": heuristic_pillar(r["text"])}
        for r in filtered
    ]
    top_S_filtered = sorted(
        [r for r in filtered_with_pillar if r["heuristic_pillar_when_filtered"] == "S"],
        key=lambda r: r["climatebert_score"], reverse=True,
    )[:5]
    top_G_filtered = sorted(
        [r for r in filtered_with_pillar if r["heuristic_pillar_when_filtered"] == "G"],
        key=lambda r: r["climatebert_score"], reverse=True,
    )[:5]

    def _slim(r: dict) -> dict:
        return {
            "chunk_id": r["chunk_id"],
            "page_number": r["page_number"],
            "section_header": r["section_header"],
            "climatebert_score": round(r["climatebert_score"], 4),
            "text_preview": r["text"][:400],
        }

    summary = {
        "doc": DOC_LABEL,
        "pdf_path": str(PDF_PATH),
        "threshold": THRESHOLD,
        "n_chunks_total": len(chunks),
        "n_passed": n_passed,
        "n_filtered": n_filtered,
        "pillar_counts_passed": pillars,
        "pillar_percent_passed": {
            "E": pct_E, "S": pct_S, "G": pct_G, "Unknown": pct_unknown,
        },
        "avg_climatebert_score_by_pillar_passed": {
            "E": avg_E, "S": avg_S, "G": avg_G,
        },
        "top5_S_passed": [_slim(r) for r in top_S_passed],
        "top5_G_passed": [_slim(r) for r in top_G_passed],
        "top5_S_filtered_out": [_slim(r) for r in top_S_filtered],
        "top5_G_filtered_out": [_slim(r) for r in top_G_filtered],
    }

    print("[4/4] Writing results ...")
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    # Save the audit JSON (summary + every chunk for full reproducibility).
    payload = {"summary": summary, "per_chunk": per_chunk}
    RESULTS_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"      wrote {RESULTS_PATH}")

    run_id = _mlflow_log(
        params={
            "model": "climatebert/distilroberta-base-climate-detector",
            "threshold": THRESHOLD,
            "doc": DOC_LABEL,
            "n_chunks_total": len(chunks),
        },
        metrics={
            "pct_E": pct_E, "pct_S": pct_S, "pct_G": pct_G, "pct_unknown": pct_unknown,
            "n_passed": n_passed, "n_filtered": n_filtered,
            "avg_score_E": avg_E, "avg_score_S": avg_S, "avg_score_G": avg_G,
        },
        artifact_path=RESULTS_PATH,
    )
    if run_id:
        print(f"      mlflow run_id={run_id}")

    # ── Console report ──────────────────────────────────────────────────
    print()
    print("=" * 70)
    print(f"ClimateBERT bias audit — {DOC_LABEL} — threshold={THRESHOLD}")
    print("=" * 70)
    print(f"chunks total       : {len(chunks)}")
    print(f"passed (>{THRESHOLD})       : {n_passed}")
    print(f"filtered out       : {n_filtered}")
    print()
    print("Pillar distribution of PASSING chunks (heuristic):")
    print(f"  E       : {pillars['E']:4d}  ({pct_E:5.2f}%)   avg score = {avg_E}")
    print(f"  S       : {pillars['S']:4d}  ({pct_S:5.2f}%)   avg score = {avg_S}")
    print(f"  G       : {pillars['G']:4d}  ({pct_G:5.2f}%)   avg score = {avg_G}")
    print(f"  Unknown : {pillars['Unknown']:4d}  ({pct_unknown:5.2f}%)")
    print()
    print("See JSON for the top-5 S / G examples (passed) and the top-5")
    print("S / G chunks ClimateBERT *filtered out*.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())