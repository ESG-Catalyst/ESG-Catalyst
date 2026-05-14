"""A2 — tune the sentence-window chunker on the Beltone PDF.

A1 (``chunking_comparison.py``) picked ``sentence_window`` as the winning
strategy. This script tries three parameter variations of the same
strategy and picks the one that maximises ESG-relevant chunk count under
the **upgraded 3-voter ensemble classifier** (ClimateBERT + FinBERT-ESG
+ ESG-BERT) while keeping short and long chunks low.

Each variation is logged to MLflow experiment ``m2-chunking-experiments``.

Outputs
-------
- ``scripts/experiments/results/chunking_tuning.json``
- MLflow runs (best-effort — skipped if server unreachable)
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from statistics import mean, pstdev

# ── Path wiring ─────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
os.environ.setdefault("PYTHONPATH", str(BACKEND_ROOT))

from app.core.ingestion.parser import ingest_document, IngestedDocument  # noqa: E402
from app.core.nlp.chunker import Chunk  # noqa: E402
from app.core.nlp.classifier import classify_chunks  # noqa: E402


# ── Configuration ───────────────────────────────────────────────────────
PDF_PATH = REPO_ROOT / "data" / "ingestion_test_files" / "en_beltone_report_summary.pdf"
RESULTS_PATH = Path(__file__).parent / "results" / "chunking_tuning.json"
MLFLOW_EXPERIMENT = "m2-chunking-experiments"

TOKEN_PER_CHAR = 1 / 3
TOKENS_SHORT = 50
TOKENS_LONG = 512
ENSEMBLE_THRESHOLD = 0.3   # production default in classifier.py


# ── Variations ──────────────────────────────────────────────────────────
# All three vary the same knobs of sentence_window. A `max_chars` cap is
# new vs. A1 — the A1 winner had max_tokens=2068 because long table rows
# weren't sentence-terminated and ran past the LLM 512-token ceiling.
VARIATIONS: list[dict] = [
    # baseline from A1 + a hard char cap to stop runaway table rows
    {"name": "sw_w3_s1_cap1500", "window": 3, "stride": 1, "max_chars": 1500},
    # bigger window, longer stride — 3× fewer chunks, more context per chunk
    {"name": "sw_w5_s2_cap1500", "window": 5, "stride": 2, "max_chars": 1500},
    # generous cap — keep more long-table fidelity at the cost of >512-token chunks
    {"name": "sw_w3_s1_cap2000", "window": 3, "stride": 1, "max_chars": 2000},
]


def _tokens(text: str) -> int:
    return max(1, int(len(text) * TOKEN_PER_CHAR))


# ── Sentence splitter — same as A1 (EN + Arabic-start safe) ─────────────
_SENT_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z؀-ۿ])")


def _split_sentences(text: str) -> list[str]:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if not cleaned:
        return []
    parts = _SENT_SPLIT_RE.split(cleaned)
    return [p.strip() for p in parts if p.strip()]


# ── Sentence-window chunker (per-page, so Chunk.page_number is correct) ─
def _sentence_window_chunks(
    doc: IngestedDocument,
    window: int,
    stride: int,
    max_chars: int,
) -> list[Chunk]:
    """Sentence-window applied per page so page_number metadata is preserved.

    If a single window exceeds ``max_chars`` it's split on sentence
    boundaries inside the window. This is what stops a 2K-char run-on
    table row from producing one giant > 512-token chunk.
    """
    import uuid

    out: list[Chunk] = []
    for page in doc.pages:
        sents = _split_sentences(page.text)
        if not sents:
            continue
        i = 0
        while i < len(sents):
            window_sents = sents[i : i + window]
            text = " ".join(window_sents).strip()

            # Hard cap — sub-split this window if it's too long.
            if len(text) > max_chars:
                acc = ""
                for s in window_sents:
                    candidate = (acc + " " + s).strip() if acc else s
                    if len(candidate) > max_chars and acc:
                        out.append(Chunk(
                            chunk_id=uuid.uuid4().hex,
                            text=acc,
                            page_number=page.page_number,
                            section_header=None,
                            chunk_type="text",
                            source_file=doc.source_file,
                            char_offset=0,
                        ))
                        acc = s
                    else:
                        acc = candidate
                if acc:
                    out.append(Chunk(
                        chunk_id=uuid.uuid4().hex,
                        text=acc,
                        page_number=page.page_number,
                        section_header=None,
                        chunk_type="text",
                        source_file=doc.source_file,
                        char_offset=0,
                    ))
            else:
                if text:
                    out.append(Chunk(
                        chunk_id=uuid.uuid4().hex,
                        text=text,
                        page_number=page.page_number,
                        section_header=None,
                        chunk_type="text",
                        source_file=doc.source_file,
                        char_offset=0,
                    ))

            if i + window >= len(sents):
                break
            i += stride
    return out


# ── Stats ───────────────────────────────────────────────────────────────
@dataclass
class TuningStats:
    name: str
    window: int
    stride: int
    max_chars: int
    n_chunks: int
    avg_tokens: float
    min_tokens: int
    max_tokens: int
    std_tokens: float
    pct_too_short: float
    pct_too_long: float
    n_esg_relevant: int
    pct_esg_relevant: float
    n_E: int
    n_S: int
    n_G: int
    elapsed_chunking_s: float
    elapsed_classify_s: float


def _stats(name: str, params: dict, chunks: list[Chunk], chunking_secs: float) -> TuningStats:
    if not chunks:
        return TuningStats(
            name=name, window=params["window"], stride=params["stride"],
            max_chars=params["max_chars"], n_chunks=0, avg_tokens=0.0,
            min_tokens=0, max_tokens=0, std_tokens=0.0,
            pct_too_short=0.0, pct_too_long=0.0, n_esg_relevant=0,
            pct_esg_relevant=0.0, n_E=0, n_S=0, n_G=0,
            elapsed_chunking_s=chunking_secs, elapsed_classify_s=0.0,
        )

    toks = [_tokens(c.text) for c in chunks]
    n = len(chunks)
    too_short = sum(1 for t in toks if t < TOKENS_SHORT)
    too_long = sum(1 for t in toks if t > TOKENS_LONG)

    t0 = time.time()
    classified = classify_chunks(chunks, threshold=ENSEMBLE_THRESHOLD, use_climate_model=True)
    elapsed_clf = time.time() - t0

    relevant = [r for r in classified if r.esg_relevant]
    n_E = sum(1 for r in relevant if r.pillar == "E")
    n_S = sum(1 for r in relevant if r.pillar == "S")
    n_G = sum(1 for r in relevant if r.pillar == "G")

    return TuningStats(
        name=name,
        window=params["window"], stride=params["stride"], max_chars=params["max_chars"],
        n_chunks=n,
        avg_tokens=round(mean(toks), 1),
        min_tokens=min(toks), max_tokens=max(toks),
        std_tokens=round(pstdev(toks), 1) if n > 1 else 0.0,
        pct_too_short=round(100 * too_short / n, 2),
        pct_too_long=round(100 * too_long / n, 2),
        n_esg_relevant=len(relevant),
        pct_esg_relevant=round(100 * len(relevant) / n, 2),
        n_E=n_E, n_S=n_S, n_G=n_G,
        elapsed_chunking_s=round(chunking_secs, 2),
        elapsed_classify_s=round(elapsed_clf, 2),
    )


# ── MLflow ──────────────────────────────────────────────────────────────
def _log_to_mlflow(stats: TuningStats) -> str | None:
    try:
        import mlflow

        tracking_uri = os.environ.get("MLFLOW_TRACKING_URI", "http://localhost:5001")
        mlflow.set_tracking_uri(tracking_uri)
        mlflow.set_experiment(MLFLOW_EXPERIMENT)
        with mlflow.start_run(run_name=stats.name) as run:
            mlflow.log_params({
                "strategy": "sentence_window",
                "window": stats.window,
                "stride": stats.stride,
                "max_chars": stats.max_chars,
                "ensemble_threshold": ENSEMBLE_THRESHOLD,
                "phase": "A2-tuning",
            })
            mlflow.log_metrics({
                "n_chunks": stats.n_chunks,
                "avg_tokens": stats.avg_tokens,
                "min_tokens": stats.min_tokens,
                "max_tokens": stats.max_tokens,
                "std_tokens": stats.std_tokens,
                "pct_too_short": stats.pct_too_short,
                "pct_too_long": stats.pct_too_long,
                "n_esg_relevant": stats.n_esg_relevant,
                "pct_esg_relevant": stats.pct_esg_relevant,
                "n_E": stats.n_E,
                "n_S": stats.n_S,
                "n_G": stats.n_G,
                "elapsed_chunking_s": stats.elapsed_chunking_s,
                "elapsed_classify_s": stats.elapsed_classify_s,
            })
            return run.info.run_id
    except Exception as exc:
        print(f"[mlflow] {stats.name}: log skipped ({exc})")
        return None


# ── Picker ──────────────────────────────────────────────────────────────
def _pick_winner(rows: list[TuningStats]) -> dict:
    """Maximise ESG-relevant count while penalising short + long chunks.

    Composite score:
        n_esg_relevant - 2*n_too_short - 5*n_too_long

    Tuned penalties: short chunks are mostly harmless noise; long chunks
    actively hurt the M3 LLM extractor (truncation at 512 tokens).
    """
    def score(r: TuningStats) -> float:
        n_short = r.n_chunks * r.pct_too_short / 100.0
        n_long = r.n_chunks * r.pct_too_long / 100.0
        return r.n_esg_relevant - 2.0 * n_short - 5.0 * n_long

    ranked = sorted(rows, key=score, reverse=True)
    winner = ranked[0]
    return {
        "recommended": winner.name,
        "rationale": (
            f"{winner.name}: {winner.n_esg_relevant} ESG-relevant chunks "
            f"({winner.pct_esg_relevant}%) with {winner.pct_too_short}% short "
            f"and {winner.pct_too_long}% long; composite score {round(score(winner), 1)}."
        ),
        "ranking": [r.name for r in ranked],
        "scores": {r.name: round(score(r), 1) for r in rows},
    }


# ── Table print ─────────────────────────────────────────────────────────
def _print_table(rows: list[TuningStats]) -> None:
    header = (
        f"{'variation':<22} {'w':>2} {'s':>2} {'cap':>5} {'n':>5} "
        f"{'avg':>6} {'min':>4} {'max':>5} {'%<50':>6} {'%>512':>7} "
        f"{'esg':>5} {'%esg':>6} {'E/S/G':>13} {'sec':>6}"
    )
    print()
    print("=" * len(header))
    print("Sentence-window tuning — Beltone PDF (ensemble classifier)")
    print("=" * len(header))
    print(header)
    print("-" * len(header))
    for r in rows:
        print(
            f"{r.name:<22} {r.window:>2} {r.stride:>2} {r.max_chars:>5} "
            f"{r.n_chunks:>5} {r.avg_tokens:>6.1f} {r.min_tokens:>4} {r.max_tokens:>5} "
            f"{r.pct_too_short:>5.1f}% {r.pct_too_long:>6.1f}% "
            f"{r.n_esg_relevant:>5} {r.pct_esg_relevant:>5.1f}% "
            f"{f'{r.n_E}/{r.n_S}/{r.n_G}':>13} "
            f"{r.elapsed_chunking_s + r.elapsed_classify_s:>6.1f}"
        )
    print("=" * len(header))


# ── Main ────────────────────────────────────────────────────────────────
def main() -> int:
    if not PDF_PATH.exists():
        print(f"PDF not found: {PDF_PATH}", file=sys.stderr)
        return 1

    print(f"[1/3] Ingesting {PDF_PATH.name} ...")
    t0 = time.time()
    doc = ingest_document(PDF_PATH)
    print(f"      pages={doc.page_count} chars={len(doc.full_text)} ({time.time()-t0:.1f}s)")

    rows: list[TuningStats] = []
    payload: dict = {}

    for v in VARIATIONS:
        print(f"[2/3] Variation '{v['name']}' (w={v['window']} s={v['stride']} cap={v['max_chars']}) ...")
        t0 = time.time()
        chunks = _sentence_window_chunks(doc, v["window"], v["stride"], v["max_chars"])
        elapsed = time.time() - t0
        print(f"      produced {len(chunks)} chunks in {elapsed:.1f}s — classifying with ensemble ...")

        stats = _stats(v["name"], v, chunks, elapsed)
        rows.append(stats)
        run_id = _log_to_mlflow(stats)
        payload[v["name"]] = {
            "params": v,
            "stats": asdict(stats),
            "mlflow_run_id": run_id,
            "sample_chunks": [c.text[:300] for c in chunks[:3]],
        }

    print("[3/3] Saving + ranking ...")
    recommendation = _pick_winner(rows)

    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(json.dumps({
        "pdf": str(PDF_PATH),
        "doc_pages": doc.page_count,
        "ensemble_threshold": ENSEMBLE_THRESHOLD,
        "variations": payload,
        "recommendation": recommendation,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"      wrote {RESULTS_PATH}")

    _print_table(rows)
    print()
    print(f"Winner: {recommendation['recommended']}")
    print(f"  why : {recommendation['rationale']}")
    print(f"  rank: {' > '.join(recommendation['ranking'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())