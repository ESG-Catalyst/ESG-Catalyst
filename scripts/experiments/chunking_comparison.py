"""Compare five chunking strategies on the Beltone PDF (read-only research).

Runs M1 ingestion once, then chunks the resulting document with five
different strategies, measures size/noise/preservation stats on each,
runs ClimateBERT over every chunk, and logs one MLflow run per strategy
to the experiment ``m2-chunking-experiments``.

Strategies
----------
1. ``current``         current production chunker (chunk_size=2000, overlap=200)
2. ``sentence_window`` 3-sentence window, stride 1 sentence
3. ``semantic``        split where cosine similarity between adjacent sentence
                       embeddings drops below 0.7 (paraphrase-multilingual-e5-base)
4. ``section_aware``   regex-detected section headers; further split if >512 tokens
5. ``recursive``       LangChain RecursiveCharacterTextSplitter
                       separators=["\\n\\n", "\\n", ".", " "], 2000 chars, 200 overlap

Outputs
-------
- ``scripts/experiments/results/chunking_comparison.json`` (summary + per-strategy)
- One MLflow run per strategy under ``m2-chunking-experiments``

This script does NOT modify ``chunker.py`` or any pipeline file.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from statistics import mean, pstdev
from typing import Callable

# ── Path wiring ─────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
os.environ.setdefault("PYTHONPATH", str(BACKEND_ROOT))

from app.core.ingestion.parser import ingest_document, IngestedDocument  # noqa: E402
from app.core.nlp.chunker import chunk_document  # noqa: E402


# ── Configuration ───────────────────────────────────────────────────────
PDF_PATH = REPO_ROOT / "data" / "ingestion_test_files" / "en_beltone_report_summary.pdf"
RESULTS_PATH = Path(__file__).parent / "results" / "chunking_comparison.json"
MLFLOW_EXPERIMENT = "m2-chunking-experiments"

CHUNK_SIZE_CHARS = 2000          # matches production default
CHUNK_OVERLAP_CHARS = 200        # matches production default
TOKEN_PER_CHAR = 1 / 3           # ~3 chars/token (mixed AR+EN); same as Chunk.token_estimate
TOKENS_SHORT = 50
TOKENS_LONG = 512
SEMANTIC_THRESHOLD = 0.7
CLIMATEBERT_THRESHOLD = 0.5


# ── Three "known" tables from the Beltone PDF ───────────────────────────
# A table is "intact" if every signature string appears inside a SINGLE chunk.
# Pages identified by pre-flight inspection of ingested text.
KNOWN_TABLES: list[dict] = [
    {
        "name": "stakeholder_engagement_p7_8",
        "description": "Internal/external stakeholders matrix (pages 7-8).",
        "signature": ["BOARD OF DIRECTORS", "REGULATORY AUTHORITIES", "LEVEL OF"],
    },
    {
        "name": "materiality_matrix_p9",
        "description": "Materiality matrix — 14 topics with rank + H-H ratings (page 9).",
        "signature": [
            "CUSTOMER PRIVACY AND DATA SECURITY",
            "GHG EMISSIONS",
            "RESPONSIBLE PROCUREMENT",
        ],
    },
    {
        "name": "esg_risks_opportunities_p26",
        "description": "ESG areas vs efforts/risks/opportunities (page 26).",
        "signature": ["Credit default risks", "Sustainable loan growth", "Green financing"],
    },
]


def _tokens(text: str) -> int:
    """Rough token estimate (~3 chars/token); matches Chunk.token_estimate."""
    return max(1, int(len(text) * TOKEN_PER_CHAR))


# ── Strategy 1: current production chunker ──────────────────────────────
def strategy_current(doc: IngestedDocument) -> list[str]:
    chunks = chunk_document(
        doc,
        chunk_size=CHUNK_SIZE_CHARS,
        chunk_overlap=CHUNK_OVERLAP_CHARS,
    )
    return [c.text for c in chunks]


# ── Sentence splitter shared by strategies 2 + 3 ────────────────────────
_SENT_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z؀-ۿ])")


def _split_sentences(text: str) -> list[str]:
    """Sentence splitter that's safe for English + Arabic-script starts."""
    # Normalise whitespace, then split on .!? followed by capital / Arabic letter.
    cleaned = re.sub(r"\s+", " ", text).strip()
    if not cleaned:
        return []
    parts = _SENT_SPLIT_RE.split(cleaned)
    return [p.strip() for p in parts if p.strip()]


# ── Strategy 2: sentence-window ─────────────────────────────────────────
def strategy_sentence_window(doc: IngestedDocument, window: int = 3, stride: int = 1) -> list[str]:
    sents = _split_sentences(doc.full_text)
    if not sents:
        return []
    out: list[str] = []
    for i in range(0, len(sents), stride):
        window_sents = sents[i : i + window]
        if not window_sents:
            break
        out.append(" ".join(window_sents))
        if i + window >= len(sents):
            break
    return out


# ── Strategy 3: semantic (cosine-similarity cut on adjacent sentences) ──
def strategy_semantic(doc: IngestedDocument, threshold: float = SEMANTIC_THRESHOLD) -> list[str]:
    from sentence_transformers import SentenceTransformer
    import numpy as np

    sents = _split_sentences(doc.full_text)
    if not sents:
        return []

    # Use the same model the production embedder uses so the chunk boundaries
    # are computed in the same vector space the retriever will use later.
    from app.config import settings

    model = SentenceTransformer(settings.embedding_model)
    # E5 family expects a "passage:" prefix for retrieval text.
    prefixed = [f"passage: {s}" for s in sents]
    vecs = model.encode(prefixed, batch_size=32, show_progress_bar=False, normalize_embeddings=True)

    chunks: list[str] = []
    current: list[str] = [sents[0]]
    for i in range(1, len(sents)):
        # Cosine sim between normalised vectors = dot product.
        sim = float(np.dot(vecs[i - 1], vecs[i]))
        if sim < threshold:
            chunks.append(" ".join(current))
            current = [sents[i]]
        else:
            current.append(sents[i])
    if current:
        chunks.append(" ".join(current))
    return chunks


# ── Strategy 4: section-aware ───────────────────────────────────────────
# A section header looks like one of:
#   • a numbered section "2.1 PROGRESS TOWARDS"
#   • an ALL-CAPS line of letters/spaces (allowing & - , ()) — short
#   • a line ending with ":" that is also <=80 chars
_NUMBERED_SECTION_RE = re.compile(r"^\s*\d+(?:\.\d+)*\.?\s+[A-Z]")
_ALL_CAPS_RE = re.compile(r"^[A-Z0-9 ,&\-\(\)/]{4,80}$")
_COLON_HEADING_RE = re.compile(r"^.{1,80}:\s*$")


def _is_section_header(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    if _NUMBERED_SECTION_RE.match(stripped):
        return True
    if _ALL_CAPS_RE.match(stripped) and any(c.isalpha() for c in stripped):
        return True
    if _COLON_HEADING_RE.match(stripped) and stripped[:-1].strip():
        return True
    return False


def _hard_split_by_tokens(text: str, max_tokens: int) -> list[str]:
    """Greedy paragraph/sentence-aware split when one section exceeds the cap."""
    if _tokens(text) <= max_tokens:
        return [text]
    max_chars = int(max_tokens / TOKEN_PER_CHAR)
    paragraphs = re.split(r"\n\n+", text)
    out: list[str] = []
    buf = ""
    for para in paragraphs:
        if len(buf) + len(para) + 2 <= max_chars:
            buf = (buf + "\n\n" + para) if buf else para
        else:
            if buf:
                out.append(buf)
            if len(para) <= max_chars:
                buf = para
            else:
                # Fall back to sentence-level packing.
                sents = re.split(r"(?<=[.!?])\s+", para)
                buf = ""
                for s in sents:
                    if len(buf) + len(s) + 1 <= max_chars:
                        buf = (buf + " " + s) if buf else s
                    else:
                        if buf:
                            out.append(buf)
                        buf = s
    if buf:
        out.append(buf)
    return out


def strategy_section_aware(doc: IngestedDocument) -> list[str]:
    lines = doc.full_text.split("\n")
    sections: list[list[str]] = []
    current: list[str] = []
    for ln in lines:
        if _is_section_header(ln) and current and any(x.strip() for x in current):
            sections.append(current)
            current = [ln]
        else:
            current.append(ln)
    if current:
        sections.append(current)

    chunks: list[str] = []
    for sec_lines in sections:
        text = "\n".join(sec_lines).strip()
        if not text:
            continue
        chunks.extend(_hard_split_by_tokens(text, TOKENS_LONG))
    return chunks


# ── Strategy 5: LangChain RecursiveCharacterTextSplitter ────────────────
def strategy_recursive(doc: IngestedDocument) -> list[str]:
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    splitter = RecursiveCharacterTextSplitter(
        separators=["\n\n", "\n", ".", " "],
        chunk_size=CHUNK_SIZE_CHARS,
        chunk_overlap=CHUNK_OVERLAP_CHARS,
        length_function=len,
    )
    return splitter.split_text(doc.full_text)


# ── ClimateBERT scoring (shared across strategies) ──────────────────────
_clf = None


def _climate_scores(texts: list[str]) -> list[float]:
    """Return P(yes) per text from ClimateBERT (cached pipeline)."""
    global _clf
    if _clf is None:
        from transformers import pipeline as hf_pipeline

        _clf = hf_pipeline(
            "text-classification",
            model="climatebert/distilroberta-base-climate-detector",
            top_k=None,
            truncation=True,
            max_length=512,
        )
    # ClimateBERT max input 512 tokens; truncation handles the rest.
    truncated = [t[:2000] for t in texts]
    raw = _clf(truncated, batch_size=16)
    out: list[float] = []
    for row in raw:
        label_scores = {d["label"]: d["score"] for d in row}
        out.append(label_scores.get("yes", 0.0))
    return out


# ── Table preservation check ────────────────────────────────────────────
def _table_preservation(chunks: list[str]) -> dict:
    """Return per-table {found, intact_in_single_chunk} flags."""
    results: dict[str, dict] = {}
    for tbl in KNOWN_TABLES:
        sig = tbl["signature"]
        # intact iff some chunk contains every signature string
        intact = any(all(s in chunk for s in sig) for chunk in chunks)
        # found at all iff every signature string appears somewhere (possibly split)
        found_anywhere = all(any(s in chunk for chunk in chunks) for s in sig)
        results[tbl["name"]] = {
            "description": tbl["description"],
            "found_anywhere": found_anywhere,
            "intact_in_single_chunk": intact,
        }
    return results


# ── Per-strategy stats ──────────────────────────────────────────────────
@dataclass
class StrategyStats:
    name: str
    n_chunks: int
    avg_tokens: float
    min_tokens: int
    max_tokens: int
    std_tokens: float
    pct_too_short: float
    pct_too_long: float
    n_climate_passed: int
    pct_climate_passed: float
    tables: dict
    elapsed_chunking_s: float
    elapsed_climate_s: float


def _compute_stats(name: str, chunks: list[str], chunking_secs: float) -> StrategyStats:
    if not chunks:
        return StrategyStats(
            name=name, n_chunks=0, avg_tokens=0.0, min_tokens=0, max_tokens=0,
            std_tokens=0.0, pct_too_short=0.0, pct_too_long=0.0,
            n_climate_passed=0, pct_climate_passed=0.0,
            tables=_table_preservation(chunks), elapsed_chunking_s=chunking_secs,
            elapsed_climate_s=0.0,
        )
    tokens = [_tokens(c) for c in chunks]
    n = len(chunks)
    too_short = sum(1 for t in tokens if t < TOKENS_SHORT)
    too_long = sum(1 for t in tokens if t > TOKENS_LONG)

    t0 = time.time()
    scores = _climate_scores(chunks)
    elapsed_clf = time.time() - t0
    n_passed = sum(1 for s in scores if s >= CLIMATEBERT_THRESHOLD)

    return StrategyStats(
        name=name,
        n_chunks=n,
        avg_tokens=round(mean(tokens), 1),
        min_tokens=min(tokens),
        max_tokens=max(tokens),
        std_tokens=round(pstdev(tokens), 1) if n > 1 else 0.0,
        pct_too_short=round(100 * too_short / n, 2),
        pct_too_long=round(100 * too_long / n, 2),
        n_climate_passed=n_passed,
        pct_climate_passed=round(100 * n_passed / n, 2),
        tables=_table_preservation(chunks),
        elapsed_chunking_s=round(chunking_secs, 2),
        elapsed_climate_s=round(elapsed_clf, 2),
    )


# ── MLflow logging (best-effort) ────────────────────────────────────────
def _log_strategy_to_mlflow(stats: StrategyStats, params: dict) -> str | None:
    try:
        import mlflow

        tracking_uri = os.environ.get("MLFLOW_TRACKING_URI", "http://localhost:5001")
        mlflow.set_tracking_uri(tracking_uri)
        mlflow.set_experiment(MLFLOW_EXPERIMENT)
        with mlflow.start_run(run_name=stats.name) as run:
            mlflow.log_params({k: str(v) for k, v in params.items()})
            mlflow.log_metrics({
                "n_chunks": stats.n_chunks,
                "avg_tokens": stats.avg_tokens,
                "min_tokens": stats.min_tokens,
                "max_tokens": stats.max_tokens,
                "std_tokens": stats.std_tokens,
                "pct_too_short": stats.pct_too_short,
                "pct_too_long": stats.pct_too_long,
                "n_climate_passed": stats.n_climate_passed,
                "pct_climate_passed": stats.pct_climate_passed,
                "tables_intact": sum(1 for v in stats.tables.values() if v["intact_in_single_chunk"]),
                "tables_found_anywhere": sum(1 for v in stats.tables.values() if v["found_anywhere"]),
                "elapsed_chunking_s": stats.elapsed_chunking_s,
                "elapsed_climate_s": stats.elapsed_climate_s,
            })
            return run.info.run_id
    except Exception as exc:
        print(f"[mlflow] {stats.name}: log skipped ({exc})")
        return None


# ── Console table ───────────────────────────────────────────────────────
def _print_comparison_table(rows: list[StrategyStats]) -> None:
    header = (
        f"{'strategy':<18} {'n':>5} {'avg_tok':>8} {'min':>5} {'max':>6} "
        f"{'std':>7} {'%<50':>6} {'%>512':>7} {'tbl_intact':>11} "
        f"{'CB_pass':>9} {'%CB':>6} {'sec':>6}"
    )
    print()
    print("=" * len(header))
    print("Chunking strategy comparison — Beltone PDF")
    print("=" * len(header))
    print(header)
    print("-" * len(header))
    for r in rows:
        tbl_intact = sum(1 for v in r.tables.values() if v["intact_in_single_chunk"])
        tbl_total = len(r.tables)
        print(
            f"{r.name:<18} {r.n_chunks:>5} {r.avg_tokens:>8.1f} {r.min_tokens:>5} "
            f"{r.max_tokens:>6} {r.std_tokens:>7.1f} "
            f"{r.pct_too_short:>5.1f}% {r.pct_too_long:>6.1f}% "
            f"{f'{tbl_intact}/{tbl_total}':>11} "
            f"{r.n_climate_passed:>9} {r.pct_climate_passed:>5.1f}% "
            f"{r.elapsed_chunking_s + r.elapsed_climate_s:>6.1f}"
        )
    print("=" * len(header))


# ── Recommendation heuristic ────────────────────────────────────────────
def _recommend(rows: list[StrategyStats]) -> dict:
    """Pick the strategy with the best M3-friendly profile.

    Priorities (in order):
      1. preserves the most known tables intact
      2. fewest %too-long chunks (LLM truncation risk)
      3. fewest %too-short chunks (noise)
      4. highest absolute count of ClimateBERT-passing chunks (E recall)
    """
    def score(r: StrategyStats) -> tuple:
        intact = sum(1 for v in r.tables.values() if v["intact_in_single_chunk"])
        return (
            intact,                         # higher is better
            -r.pct_too_long,                # lower %>512 is better
            -r.pct_too_short,               # lower %<50 is better
            r.n_climate_passed,             # higher is better
        )

    ranked = sorted(rows, key=score, reverse=True)
    winner = ranked[0]
    rationale = (
        f"{winner.name}: {sum(1 for v in winner.tables.values() if v['intact_in_single_chunk'])}/"
        f"{len(winner.tables)} known tables intact; {winner.pct_too_long}% chunks >512 tokens; "
        f"{winner.pct_too_short}% <50 tokens; {winner.n_climate_passed} chunks pass ClimateBERT."
    )
    return {"recommended": winner.name, "rationale": rationale,
            "ranking": [r.name for r in ranked]}


# ── Main ────────────────────────────────────────────────────────────────
STRATEGIES: dict[str, Callable[[IngestedDocument], list[str]]] = {
    "current": strategy_current,
    "sentence_window": strategy_sentence_window,
    "semantic": strategy_semantic,
    "section_aware": strategy_section_aware,
    "recursive": strategy_recursive,
}

STRATEGY_PARAMS: dict[str, dict] = {
    "current": {
        "chunk_size_chars": CHUNK_SIZE_CHARS,
        "chunk_overlap_chars": CHUNK_OVERLAP_CHARS,
    },
    "sentence_window": {"window_sentences": 3, "stride_sentences": 1},
    "semantic": {
        "threshold_cosine": SEMANTIC_THRESHOLD,
        "embedding_model": "paraphrase-multilingual-e5-base",
    },
    "section_aware": {"max_tokens_per_chunk": TOKENS_LONG},
    "recursive": {
        "chunk_size_chars": CHUNK_SIZE_CHARS,
        "chunk_overlap_chars": CHUNK_OVERLAP_CHARS,
        "separators": ["\\n\\n", "\\n", ".", " "],
    },
}


def main() -> int:
    if not PDF_PATH.exists():
        print(f"PDF not found: {PDF_PATH}", file=sys.stderr)
        return 1

    print(f"[1/3] Ingesting {PDF_PATH.name} ...")
    t0 = time.time()
    doc = ingest_document(PDF_PATH)
    print(f"      pages={doc.page_count} lang={doc.language} chars={len(doc.full_text)} ({time.time()-t0:.1f}s)")

    rows: list[StrategyStats] = []
    per_strategy_payload: dict[str, dict] = {}

    for name, fn in STRATEGIES.items():
        print(f"[2/3] Chunking with strategy='{name}' ...")
        t0 = time.time()
        try:
            chunks = fn(doc)
        except Exception as exc:
            print(f"      FAILED: {exc}")
            continue
        elapsed = time.time() - t0
        print(f"      produced {len(chunks)} chunks in {elapsed:.1f}s — scoring with ClimateBERT ...")

        stats = _compute_stats(name, chunks, elapsed)
        rows.append(stats)
        run_id = _log_strategy_to_mlflow(stats, STRATEGY_PARAMS.get(name, {}))
        per_strategy_payload[name] = {
            "stats": stats.__dict__,
            "params": STRATEGY_PARAMS.get(name, {}),
            "mlflow_run_id": run_id,
            "sample_chunks": [c[:300] for c in chunks[:3]],
        }

    print("[3/3] Saving results ...")
    recommendation = _recommend(rows) if rows else {"recommended": None, "rationale": "no strategy completed"}

    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "pdf": str(PDF_PATH),
        "doc_pages": doc.page_count,
        "doc_chars": len(doc.full_text),
        "climatebert_threshold": CLIMATEBERT_THRESHOLD,
        "token_per_char": TOKEN_PER_CHAR,
        "tokens_short": TOKENS_SHORT,
        "tokens_long": TOKENS_LONG,
        "known_tables": KNOWN_TABLES,
        "strategies": per_strategy_payload,
        "recommendation": recommendation,
    }
    RESULTS_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"      wrote {RESULTS_PATH}")

    _print_comparison_table(rows)
    print()
    print(f"Recommended next-A2 strategy: {recommendation['recommended']}")
    print(f"  why: {recommendation['rationale']}")
    print()
    print(f"  full ranking (best -> worst): {' > '.join(recommendation['ranking'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
