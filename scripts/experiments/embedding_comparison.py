"""Compare embedding models for ESG content retrieval (read-only research).

Runs M1 ingestion + M2 chunking on each document referenced by the test
set (once per document), then embeds every chunk with each candidate
model, executes the test set, and scores recall@1 / recall@5 per model
per language plus overall. Resource cost (embedding time, peak RAM
during encoding) is also measured.

Models under test
-----------------
1. ``intfloat/multilingual-e5-base``                    — current baseline (~278M params, 768d)
2. ``intfloat/multilingual-e5-large``                   — larger E5 (~560M params, 1024d)
3. ``sentence-transformers/paraphrase-multilingual-mpnet-base-v2``
                                                        — strong general multilingual ST (~278M, 768d)
4. ``BAAI/bge-m3``                                      — SOTA multilingual incl. Arabic (~568M, 1024d)
5. ``aubmindlab/bert-base-arabertv2``                   — Arabic-specific BERT (~135M, 768d)
                                                          AR-only — runs against AR queries only;
                                                          SentenceTransformer wraps it with mean
                                                          pooling.

Evaluation set
--------------
``scripts/experiments/retrieval_test_set.json``
- 10 English (Beltone Sustainability Report 2024)
- 10 Arabic (ADIB ESG Report 2022)
Each query has a ``doc_key`` selecting which document's chunks it's
retrieved against, plus a ``relevance_signature`` whose substrings must
all appear in the union of the top-k retrieved chunks.

Outputs
-------
- ``scripts/experiments/results/embedding_comparison.json`` (summary + per-model)
- One MLflow run per model under experiment ``m2-embedding-experiments``
- Recommendation: single multilingual model vs separate AR/EN models

This script does NOT modify ``embedder.py`` or any pipeline file.
"""

from __future__ import annotations

import gc
import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Force UTF-8 on stdout/stderr so MLflow's "🏃 View run ..." completion line
# and Arabic content don't blow up under Windows cp1252. Must run before
# any import that writes to stdout.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass

# ── Path wiring ─────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
os.environ.setdefault("PYTHONPATH", str(BACKEND_ROOT))

# Honour cached weights when the network (DNS) is down. Setting these
# *before* sentence-transformers is imported makes it skip the HEAD probe
# against huggingface.co and load straight from ~/.cache/huggingface.
# Override with EMBEDDING_COMPARISON_FORCE_ONLINE=1 to force a fresh download.
if os.environ.get("EMBEDDING_COMPARISON_FORCE_ONLINE") != "1":
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

from app.core.ingestion.parser import ingest_document  # noqa: E402
from app.core.nlp.chunker import chunk_document  # noqa: E402


# ── Configuration ───────────────────────────────────────────────────────
TEST_SET_PATH = Path(__file__).parent / "retrieval_test_set.json"
RESULTS_PATH = Path(__file__).parent / "results" / "embedding_comparison.json"
MLFLOW_EXPERIMENT = "m2-embedding-experiments"

TOP_K = 5
CHUNK_SIZE_CHARS = 2000      # matches production
CHUNK_OVERLAP_CHARS = 200    # matches production
BATCH_SIZE = 32


# E5 family expects "query: " / "passage: " prefixes for retrieval.
# BGE-M3 / mpnet / AraBERT do not.
# ``languages``: which query-language buckets this model should be scored on.
# AraBERT is monolingual Arabic — feeding it English queries is meaningless,
# so it's restricted to AR only.
@dataclass
class ModelSpec:
    key: str
    hf_name: str
    note: str
    query_prefix: str = ""
    passage_prefix: str = ""
    languages: tuple[str, ...] = ("en", "ar")


MODELS: list[ModelSpec] = [
    ModelSpec(
        key="e5-base",
        hf_name="intfloat/multilingual-e5-base",
        note="Current production baseline. ~278M params, 768d.",
        query_prefix="query: ",
        passage_prefix="passage: ",
    ),
    ModelSpec(
        key="e5-large",
        hf_name="intfloat/multilingual-e5-large",
        note="Larger E5 — slower, expected higher recall. ~560M params, 1024d.",
        query_prefix="query: ",
        passage_prefix="passage: ",
    ),
    ModelSpec(
        key="mpnet-multi",
        hf_name="sentence-transformers/paraphrase-multilingual-mpnet-base-v2",
        note="General multilingual sentence-transformer. ~278M params, 768d.",
    ),
    ModelSpec(
        key="bge-m3",
        hf_name="BAAI/bge-m3",
        note="SOTA multilingual incl. Arabic. ~568M params, 1024d.",
    ),
    ModelSpec(
        key="arabertv2",
        hf_name="aubmindlab/bert-base-arabertv2",
        note="Arabic-specific BERT (mean-pooled via SentenceTransformer). ~135M params, 768d.",
        languages=("ar",),
    ),
]


# ── Test-set loading ────────────────────────────────────────────────────
def load_test_set() -> dict:
    if not TEST_SET_PATH.exists():
        raise FileNotFoundError(f"Test set not found: {TEST_SET_PATH}")
    return json.loads(TEST_SET_PATH.read_text(encoding="utf-8"))


def signature_covered(chunks_subset: list[str], signature: list[str]) -> bool:
    """True iff every substring in ``signature`` appears in the union of ``chunks_subset``."""
    joined = "\n".join(chunks_subset)
    return all(s in joined for s in signature)


# ── RAM measurement ─────────────────────────────────────────────────────
def _process_rss_mb() -> float:
    """Return current process RSS in MB. Returns 0.0 if psutil missing."""
    try:
        import psutil
    except Exception:
        return 0.0
    return psutil.Process(os.getpid()).memory_info().rss / (1024 * 1024)


# ── Document ingestion + chunking (cached per doc_key) ──────────────────
@dataclass
class IngestedDoc:
    key: str
    title: str
    language: str
    path: Path
    chunk_texts: list[str]
    page_count: int
    char_count: int


def prepare_documents(test_set: dict) -> dict[str, IngestedDoc]:
    """Ingest + chunk every document referenced by the test set, once each."""
    out: dict[str, IngestedDoc] = {}
    for key, meta in test_set["documents"].items():
        path = REPO_ROOT / meta["path"]
        if not path.exists():
            raise FileNotFoundError(f"Document {key!r} not found at {path}")
        print(f"  ingesting [{key}] {path.name} ...")
        t0 = time.time()
        doc = ingest_document(path)
        chunks = chunk_document(
            doc,
            chunk_size=CHUNK_SIZE_CHARS,
            chunk_overlap=CHUNK_OVERLAP_CHARS,
        )
        chunk_texts = [c.text for c in chunks]
        print(
            f"    pages={doc.page_count} lang={doc.language} chars={len(doc.full_text)} "
            f"chunks={len(chunk_texts)} ({time.time() - t0:.1f}s)"
        )
        out[key] = IngestedDoc(
            key=key,
            title=meta.get("title", key),
            language=meta.get("language", doc.language),
            path=path,
            chunk_texts=chunk_texts,
            page_count=doc.page_count,
            char_count=len(doc.full_text),
        )
    return out


# ── Per-model evaluation ────────────────────────────────────────────────
@dataclass
class ModelResult:
    key: str
    hf_name: str
    note: str
    languages_evaluated: tuple[str, ...]
    n_chunks_total: int
    embed_time_sec: float
    embed_dim: int
    ram_before_mb: float
    ram_after_mb: float
    ram_delta_mb: float
    recall_at_1: float                # overall, across evaluated languages
    recall_at_5: float
    recall_at_1_by_lang: dict[str, float] = field(default_factory=dict)
    recall_at_5_by_lang: dict[str, float] = field(default_factory=dict)
    per_query: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None


def _encode_with_model(model, texts: list[str], prefix: str):
    """Encode a list of texts with optional prefix; return numpy array (n, d), L2-normalised."""
    prefixed = [f"{prefix}{t}" for t in texts] if prefix else texts
    return model.encode(
        prefixed,
        batch_size=BATCH_SIZE,
        show_progress_bar=False,
        normalize_embeddings=True,
    )


def evaluate_model(
    spec: ModelSpec,
    docs: dict[str, IngestedDoc],
    test_set: dict,
) -> ModelResult:
    print(f"\n[model] {spec.hf_name}  — {spec.note}")
    print(f"        evaluated languages: {list(spec.languages)}")
    from sentence_transformers import SentenceTransformer
    import numpy as np

    queries: list[dict] = []
    for lang in spec.languages:
        queries.extend(test_set.get(f"queries_{lang}", []))
    if not queries:
        return ModelResult(
            key=spec.key, hf_name=spec.hf_name, note=spec.note,
            languages_evaluated=spec.languages,
            n_chunks_total=0, embed_time_sec=0.0, embed_dim=0,
            ram_before_mb=0.0, ram_after_mb=0.0, ram_delta_mb=0.0,
            recall_at_1=0.0, recall_at_5=0.0,
            error="no queries for evaluated languages",
        )

    # Which documents do we actually need to embed for this model?
    needed_doc_keys = sorted({q["doc_key"] for q in queries})

    ram_before = _process_rss_mb()
    t_load = time.time()
    try:
        model = SentenceTransformer(spec.hf_name)
    except Exception as exc:
        print(f"        FAILED to load: {exc}")
        return ModelResult(
            key=spec.key, hf_name=spec.hf_name, note=spec.note,
            languages_evaluated=spec.languages,
            n_chunks_total=0, embed_time_sec=0.0, embed_dim=0,
            ram_before_mb=round(ram_before, 1), ram_after_mb=round(ram_before, 1),
            ram_delta_mb=0.0, recall_at_1=0.0, recall_at_5=0.0,
            error=f"load_failed: {exc}",
        )
    print(f"        loaded in {time.time() - t_load:.1f}s")

    # Encode each doc's chunks once; cache vectors per doc_key.
    doc_vecs: dict[str, Any] = {}
    embed_time_total = 0.0
    embed_dim = 0
    n_chunks_total = 0
    try:
        for dkey in needed_doc_keys:
            d = docs[dkey]
            t0 = time.time()
            vecs = _encode_with_model(model, d.chunk_texts, spec.passage_prefix)
            doc_vecs[dkey] = vecs
            elapsed = time.time() - t0
            embed_time_total += elapsed
            embed_dim = int(vecs.shape[1])
            n_chunks_total += len(d.chunk_texts)
            print(
                f"        [{dkey}] encoded {len(d.chunk_texts)} chunks in {elapsed:.1f}s "
                f"(dim={embed_dim})"
            )
    except Exception as exc:
        print(f"        FAILED during chunk encoding: {exc}")
        ram_after = _process_rss_mb()
        return ModelResult(
            key=spec.key, hf_name=spec.hf_name, note=spec.note,
            languages_evaluated=spec.languages,
            n_chunks_total=n_chunks_total, embed_time_sec=round(embed_time_total, 2),
            embed_dim=embed_dim,
            ram_before_mb=round(ram_before, 1), ram_after_mb=round(ram_after, 1),
            ram_delta_mb=round(ram_after - ram_before, 1),
            recall_at_1=0.0, recall_at_5=0.0,
            error=f"encode_failed: {exc}",
        )

    ram_after = _process_rss_mb()

    # Encode queries (use query prefix for E5; nothing for the others).
    query_texts = [q["query"] for q in queries]
    query_vecs = _encode_with_model(model, query_texts, spec.query_prefix)

    hits_by_lang: dict[str, dict[str, int]] = {}  # {"en": {"r1": 0, "r5": 0, "n": 0}, ...}
    overall = {"r1": 0, "r5": 0, "n": 0}
    per_query: list[dict[str, Any]] = []

    for qi, q in enumerate(queries):
        # Infer query language from id prefix (en-/ar-).
        qid = q["id"]
        lang = qid.split("-")[0] if "-" in qid else "unk"
        dkey = q["doc_key"]
        sig = q["relevance_signature"]
        doc_chunks = docs[dkey].chunk_texts
        vecs = doc_vecs[dkey]
        sims = query_vecs[qi] @ vecs.T  # (n_chunks,)
        order = np.argsort(-sims)
        top5_idx = [int(i) for i in order[:TOP_K].tolist()]
        top1_idx = top5_idx[0]
        in_top1 = signature_covered([doc_chunks[top1_idx]], sig)
        in_top5 = signature_covered([doc_chunks[i] for i in top5_idx], sig)

        bucket = hits_by_lang.setdefault(lang, {"r1": 0, "r5": 0, "n": 0})
        bucket["n"] += 1
        overall["n"] += 1
        if in_top1:
            bucket["r1"] += 1
            overall["r1"] += 1
        if in_top5:
            bucket["r5"] += 1
            overall["r5"] += 1

        per_query.append({
            "id": qid,
            "lang": lang,
            "doc_key": dkey,
            "query": q["query"],
            "signature": sig,
            "top5_indices": top5_idx,
            "top5_scores": [round(float(sims[i]), 4) for i in top5_idx],
            "hit_at_1": bool(in_top1),
            "hit_at_5": bool(in_top5),
        })

    recall_at_1_by_lang = {
        lang: round(b["r1"] / b["n"], 4) if b["n"] else 0.0
        for lang, b in hits_by_lang.items()
    }
    recall_at_5_by_lang = {
        lang: round(b["r5"] / b["n"], 4) if b["n"] else 0.0
        for lang, b in hits_by_lang.items()
    }
    recall_at_1 = round(overall["r1"] / overall["n"], 4) if overall["n"] else 0.0
    recall_at_5 = round(overall["r5"] / overall["n"], 4) if overall["n"] else 0.0
    print(f"        recall@1 (overall) = {recall_at_1}   recall@5 (overall) = {recall_at_5}")
    for lang in sorted(hits_by_lang.keys()):
        b = hits_by_lang[lang]
        print(
            f"        [{lang}] r@1={recall_at_1_by_lang[lang]} r@5={recall_at_5_by_lang[lang]} "
            f"({b['r1']}/{b['n']} top-1, {b['r5']}/{b['n']} top-5)"
        )

    # Free RAM before next model
    del model, doc_vecs, query_vecs
    gc.collect()
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        pass

    return ModelResult(
        key=spec.key, hf_name=spec.hf_name, note=spec.note,
        languages_evaluated=spec.languages,
        n_chunks_total=n_chunks_total,
        embed_time_sec=round(embed_time_total, 2),
        embed_dim=embed_dim,
        ram_before_mb=round(ram_before, 1),
        ram_after_mb=round(ram_after, 1),
        ram_delta_mb=round(ram_after - ram_before, 1),
        recall_at_1=recall_at_1,
        recall_at_5=recall_at_5,
        recall_at_1_by_lang=recall_at_1_by_lang,
        recall_at_5_by_lang=recall_at_5_by_lang,
        per_query=per_query,
    )


# ── MLflow logging (best-effort) ────────────────────────────────────────
def _log_to_mlflow(result: ModelResult, params: dict) -> str | None:
    try:
        import mlflow

        tracking_uri = os.environ.get("MLFLOW_TRACKING_URI", "http://localhost:5001")
        mlflow.set_tracking_uri(tracking_uri)
        mlflow.set_experiment(MLFLOW_EXPERIMENT)
        with mlflow.start_run(run_name=result.key) as run:
            mlflow.log_params({k: str(v) for k, v in params.items()})
            mlflow.log_params({
                "model_name": result.hf_name,
                "embed_dim": result.embed_dim,
                "languages_evaluated": ",".join(result.languages_evaluated),
            })
            metrics = {
                "recall_at_1": result.recall_at_1,
                "recall_at_5": result.recall_at_5,
                "embed_time_sec": result.embed_time_sec,
                "ram_delta_mb": result.ram_delta_mb,
                "ram_after_mb": result.ram_after_mb,
                "n_chunks": result.n_chunks_total,
            }
            for lang, v in result.recall_at_1_by_lang.items():
                metrics[f"recall_at_1_{lang}"] = v
            for lang, v in result.recall_at_5_by_lang.items():
                metrics[f"recall_at_5_{lang}"] = v
            mlflow.log_metrics(metrics)
            return run.info.run_id
    except Exception as exc:
        print(f"[mlflow] {result.key}: log skipped ({exc})")
        return None


# ── Console table ───────────────────────────────────────────────────────
def _print_comparison_table(results: list[ModelResult]) -> None:
    header = (
        f"{'model':<14} {'dim':>5} {'lang':>7} {'R@1':>7} {'R@5':>7} "
        f"{'R@1_en':>7} {'R@5_en':>7} {'R@1_ar':>7} {'R@5_ar':>7} "
        f"{'embed_s':>9} {'RAM_dMB':>9}"
    )
    print()
    print("=" * len(header))
    print("Embedding model comparison — multilingual retrieval (Beltone EN + ADIB AR)")
    print("=" * len(header))
    print(header)
    print("-" * len(header))
    for r in results:
        if r.error:
            print(f"{r.key:<14} ERROR: {r.error[:80]}")
            continue
        langs = "+".join(r.languages_evaluated)
        r1en = r.recall_at_1_by_lang.get("en", float("nan"))
        r5en = r.recall_at_5_by_lang.get("en", float("nan"))
        r1ar = r.recall_at_1_by_lang.get("ar", float("nan"))
        r5ar = r.recall_at_5_by_lang.get("ar", float("nan"))
        def fmt(x):
            return f"{x:.3f}" if isinstance(x, float) and x == x else "  -  "
        print(
            f"{r.key:<14} {r.embed_dim:>5} {langs:>7} "
            f"{r.recall_at_1:>7.3f} {r.recall_at_5:>7.3f} "
            f"{fmt(r1en):>7} {fmt(r5en):>7} {fmt(r1ar):>7} {fmt(r5ar):>7} "
            f"{r.embed_time_sec:>9.1f} {r.ram_delta_mb:>9.0f}"
        )
    print("=" * len(header))


# ── Recommendation: single multilingual vs separate AR/EN ───────────────
def _recommend(results: list[ModelResult]) -> dict:
    usable = [r for r in results if not r.error]
    if not usable:
        return {"recommended": None, "rationale": "no model produced results"}

    # Best per-language model
    def best_for(lang: str) -> ModelResult | None:
        candidates = [r for r in usable if lang in r.recall_at_5_by_lang]
        if not candidates:
            return None
        return max(
            candidates,
            key=lambda r: (
                r.recall_at_5_by_lang[lang],
                r.recall_at_1_by_lang[lang],
                -r.embed_time_sec,
            ),
        )

    # Best multilingual (must cover all evaluated languages in the test set,
    # so we filter to models that evaluated both en and ar)
    multilingual = [
        r for r in usable if "en" in r.languages_evaluated and "ar" in r.languages_evaluated
    ]
    best_multi = (
        max(
            multilingual,
            key=lambda r: (r.recall_at_5, r.recall_at_1, -r.embed_time_sec),
        )
        if multilingual
        else None
    )
    best_en = best_for("en")
    best_ar = best_for("ar")

    # Decide: separate AR/EN beats single only if the AR specialist beats the
    # multilingual model's AR recall by a meaningful margin (>0.10 on r@5).
    SEPARATE_THRESHOLD = 0.10
    use_separate = False
    rationale_parts: list[str] = []
    if best_multi and best_ar:
        multi_ar5 = best_multi.recall_at_5_by_lang.get("ar", 0.0)
        spec_ar5 = best_ar.recall_at_5_by_lang.get("ar", 0.0)
        delta = spec_ar5 - multi_ar5
        if best_ar.key != best_multi.key and delta > SEPARATE_THRESHOLD:
            use_separate = True
            rationale_parts.append(
                f"AR-specialist {best_ar.key} beats best multilingual {best_multi.key} on AR r@5 "
                f"by +{delta:.2f} (>{SEPARATE_THRESHOLD:.2f} threshold) → separate AR/EN justified."
            )
        else:
            rationale_parts.append(
                f"Best multilingual {best_multi.key} AR r@5 = {multi_ar5:.2f}; "
                f"best AR specialist {best_ar.key if best_ar else 'n/a'} AR r@5 = {spec_ar5:.2f} "
                f"(Δ={delta:+.2f}). Below {SEPARATE_THRESHOLD:.2f} threshold → single multilingual model preferred."
            )

    if use_separate:
        recommendation = {
            "mode": "separate",
            "en_model": best_en.key if best_en else None,
            "en_hf": best_en.hf_name if best_en else None,
            "ar_model": best_ar.key if best_ar else None,
            "ar_hf": best_ar.hf_name if best_ar else None,
        }
    else:
        recommendation = {
            "mode": "single_multilingual",
            "model": best_multi.key if best_multi else None,
            "hf": best_multi.hf_name if best_multi else None,
        }

    return {
        "recommendation": recommendation,
        "best_en": best_en.key if best_en else None,
        "best_ar": best_ar.key if best_ar else None,
        "best_multilingual": best_multi.key if best_multi else None,
        "rationale": " ".join(rationale_parts) or "single insufficient-data path",
    }


# ── Main ────────────────────────────────────────────────────────────────
def main() -> int:
    print(f"[1/4] Loading retrieval test set from {TEST_SET_PATH.name} ...")
    test_set = load_test_set()
    n_en = len(test_set.get("queries_en", []))
    n_ar = len(test_set.get("queries_ar", []))
    print(f"      EN queries: {n_en}   AR queries: {n_ar}")
    print(f"      documents: {list(test_set['documents'].keys())}")

    print("[2/4] Ingesting + chunking documents ...")
    docs = prepare_documents(test_set)

    # Pre-flight coverage check per query.
    print("[3/4] Pre-flight test-set coverage check ...")
    all_queries = test_set.get("queries_en", []) + test_set.get("queries_ar", [])
    answerable = 0
    unmatched: list[str] = []
    for q in all_queries:
        d = docs[q["doc_key"]]
        if signature_covered(d.chunk_texts, q["relevance_signature"]):
            answerable += 1
        else:
            unmatched.append(q["id"])
    print(
        f"      test-set coverage: {answerable}/{len(all_queries)} queries have "
        f"every signature term present somewhere in the relevant doc's chunk set."
    )
    if unmatched:
        print(f"      WARNING - signature not fully covered by any chunks for: {unmatched}")
        print("        => upper bound on recall@5 will be < 1.0 for those queries.")

    print(f"[4/4] Running {len(MODELS)} models ...")
    shared_params = {
        "documents": ",".join(test_set["documents"].keys()),
        "chunk_size_chars": CHUNK_SIZE_CHARS,
        "chunk_overlap_chars": CHUNK_OVERLAP_CHARS,
        "top_k": TOP_K,
        "n_queries_en": n_en,
        "n_queries_ar": n_ar,
    }

    results: list[ModelResult] = []
    per_model_payload: dict[str, dict] = {}
    for spec in MODELS:
        try:
            r = evaluate_model(spec, docs, test_set)
        except Exception as exc:
            print(f"        unrecoverable error: {exc}")
            r = ModelResult(
                key=spec.key, hf_name=spec.hf_name, note=spec.note,
                languages_evaluated=spec.languages,
                n_chunks_total=0, embed_time_sec=0.0, embed_dim=0,
                ram_before_mb=0.0, ram_after_mb=0.0, ram_delta_mb=0.0,
                recall_at_1=0.0, recall_at_5=0.0,
                error=f"unhandled: {exc}",
            )
        results.append(r)
        run_id = _log_to_mlflow(r, shared_params)
        per_model_payload[spec.key] = {
            "result": r.__dict__,
            "mlflow_run_id": run_id,
        }

    print("\n[done] Saving results ...")
    recommendation = _recommend(results)

    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "documents": {
            k: {
                "path": str(d.path),
                "language": d.language,
                "page_count": d.page_count,
                "char_count": d.char_count,
                "n_chunks": len(d.chunk_texts),
            }
            for k, d in docs.items()
        },
        "chunk_size_chars": CHUNK_SIZE_CHARS,
        "chunk_overlap_chars": CHUNK_OVERLAP_CHARS,
        "top_k": TOP_K,
        "test_set_path": str(TEST_SET_PATH),
        "test_set_coverage": {
            "queries_total": len(all_queries),
            "queries_answerable": answerable,
            "unmatched_query_ids": unmatched,
        },
        "models": per_model_payload,
        "recommendation": recommendation,
    }
    RESULTS_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"       wrote {RESULTS_PATH}")

    _print_comparison_table(results)
    print()
    rec = recommendation.get("recommendation", {})
    if rec.get("mode") == "single_multilingual":
        print(f"Recommendation: single multilingual model → {rec['model']} ({rec['hf']})")
    elif rec.get("mode") == "separate":
        print(f"Recommendation: SEPARATE models → EN={rec['en_model']} ({rec['en_hf']})  "
              f"AR={rec['ar_model']} ({rec['ar_hf']})")
    else:
        print(f"Recommendation: {rec}")
    print(f"  rationale: {recommendation.get('rationale', '')}")
    print(f"  best EN: {recommendation.get('best_en')}    "
          f"best AR: {recommendation.get('best_ar')}    "
          f"best multilingual: {recommendation.get('best_multilingual')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
