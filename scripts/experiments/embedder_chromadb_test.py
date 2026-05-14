"""End-to-end test of the bilingual embedder against a live ChromaDB.

Pipeline under test:
    chunk_document(doc) → embed_and_store(chunks) → chromadb
    query → embed_query(q, lang) → collection.query() → top-5

Runs the 20-query test set from B1 (10 EN against Beltone + 10 AR
against ADIB) and reports recall@1 / recall@5 per language and overall.
If everything works, numbers should match the in-memory cosine results
from B1: bge-m3 AR R@5 = 0.90, e5-base EN R@5 = 0.80, overall ≈ 0.85.

Requires:
    * ChromaDB running on settings.chroma_host:chroma_port (the
      ``CHROMA_HOST``/``CHROMA_PORT`` env vars; default localhost:8001).
    * Embedding models cached locally (run ``scripts/download_models.py``).

Outputs:
    ``scripts/experiments/results/embedder_chromadb_test.json``
    One MLflow run per language under ``m2-embedding-experiments``
    with run names ``chromadb-en-e5-base`` and ``chromadb-ar-bge-m3``.

This script does NOT mutate any pipeline file. It does write to
ChromaDB collections ``document_chunks_en`` and ``document_chunks_ar``,
which it resets at the start of the run for a clean baseline.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

# Force UTF-8 on stdout so MLflow + Arabic content don't trip Windows cp1252.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
os.environ.setdefault("PYTHONPATH", str(BACKEND_ROOT))
# Models are cached locally; skip the HF Hub HEAD probe.
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

from app.config import settings  # noqa: E402
from app.core.ingestion.parser import ingest_document  # noqa: E402
from app.core.nlp.chunker import chunk_document  # noqa: E402
from app.core.nlp.embedder import embed_and_store, embed_query, preload_models  # noqa: E402

TEST_SET_PATH = Path(__file__).parent / "retrieval_test_set.json"
RESULTS_PATH = Path(__file__).parent / "results" / "embedder_chromadb_test.json"
MLFLOW_EXPERIMENT = "m2-embedding-experiments"
TOP_K = 5
COLLECTIONS = {"en": "document_chunks_en", "ar": "document_chunks_ar"}


def signature_covered(chunks_subset: list[str], signature: list[str]) -> bool:
    """True iff every substring in ``signature`` appears in the union of ``chunks_subset``."""
    joined = "\n".join(chunks_subset)
    return all(s in joined for s in signature)


def reset_collection(client, name: str) -> None:
    """Delete a collection if it exists, so each run starts clean."""
    try:
        client.delete_collection(name=name)
        print(f"      deleted existing collection {name!r}")
    except Exception:
        pass  # doesn't exist


def main() -> int:
    print(f"[1/5] Loading test set from {TEST_SET_PATH.name} ...")
    test_set = json.loads(TEST_SET_PATH.read_text(encoding="utf-8"))
    n_en = len(test_set.get("queries_en", []))
    n_ar = len(test_set.get("queries_ar", []))
    print(f"      {n_en} EN queries, {n_ar} AR queries, docs={list(test_set['documents'].keys())}")

    print("[2/5] Pre-loading EN + AR embedding models ...")
    t0 = time.time()
    preload_models()
    print(f"      ready in {time.time() - t0:.1f}s")

    print("[3/5] Resetting + populating ChromaDB collections ...")
    import chromadb
    client = chromadb.HttpClient(host=settings.chroma_host, port=settings.chroma_port)
    for name in COLLECTIONS.values():
        reset_collection(client, name)

    # Ingest + chunk every doc once, then push chunks through embed_and_store.
    doc_chunk_index: dict[str, dict[str, list[str]]] = {}
    # ↑ {doc_key: {lang: [chunk_text, ...]}} — needed for signature coverage
    #   checks at query time (we ask: did the retrieved doc contain the answer?).
    stored_ids: dict[str, dict[str, list[str]]] = {}

    for dkey, meta in test_set["documents"].items():
        path = REPO_ROOT / meta["path"]
        print(f"      ingesting [{dkey}] {path.name} ...")
        t0 = time.time()
        doc = ingest_document(path)
        chunks = chunk_document(doc)
        print(
            f"        pages={doc.page_count} lang={doc.language} "
            f"chunks={len(chunks)} ({time.time() - t0:.1f}s)"
        )

        t0 = time.time()
        out = embed_and_store(chunks, company_id=dkey, report_id=f"{dkey}-run")
        elapsed = time.time() - t0
        print(
            f"        stored EN={len(out['en'])}  AR={len(out['ar'])}  ({elapsed:.1f}s)"
        )
        stored_ids[dkey] = {"en": list(out["en"]), "ar": list(out["ar"])}

        # Build a chunk-text index per (doc, lang) so we can map retrieved
        # IDs back to the chunk text for signature checking.
        text_by_id: dict[str, str] = {c.chunk_id: c.text for c in chunks}
        doc_chunk_index[dkey] = {
            "en": [text_by_id[i] for i in out["en"]],
            "ar": [text_by_id[i] for i in out["ar"]],
            "_id_to_text": text_by_id,  # type: ignore[dict-item]
        }

    # Sanity: report collection sizes (post-write).
    for lang, cname in COLLECTIONS.items():
        try:
            col = client.get_collection(name=cname)
            print(f"      collection {cname}: {col.count()} vectors")
        except Exception as exc:
            print(f"      collection {cname}: missing ({exc})")

    print("[4/5] Querying ChromaDB ...")
    all_queries = test_set.get("queries_en", []) + test_set.get("queries_ar", [])
    per_query: list[dict[str, Any]] = []
    hits = {"en": {"r1": 0, "r5": 0, "n": 0}, "ar": {"r1": 0, "r5": 0, "n": 0}}

    for q in all_queries:
        qid = q["id"]
        lang = qid.split("-", 1)[0] if "-" in qid else "en"
        dkey = q["doc_key"]
        sig = q["relevance_signature"]

        # Embed the query with the language-appropriate model.
        qvec = embed_query(q["query"], lang=lang)
        collection = client.get_collection(name=COLLECTIONS[lang])

        # ChromaDB returns ascending distance (we configured cosine, so
        # distance = 1 - cosine_sim; lower = more similar).
        result = collection.query(
            query_embeddings=[qvec.tolist()],
            n_results=TOP_K,
            where={"company_id": dkey},  # restrict to this document
        )
        top_ids: list[str] = result["ids"][0] if result.get("ids") else []
        top_docs: list[str] = result["documents"][0] if result.get("documents") else []
        top_distances: list[float] = (
            result["distances"][0] if result.get("distances") else []
        )

        in_top1 = bool(top_docs) and signature_covered([top_docs[0]], sig)
        in_top5 = bool(top_docs) and signature_covered(top_docs, sig)

        bucket = hits[lang]
        bucket["n"] += 1
        if in_top1:
            bucket["r1"] += 1
        if in_top5:
            bucket["r5"] += 1

        per_query.append({
            "id": qid,
            "lang": lang,
            "doc_key": dkey,
            "query": q["query"],
            "signature": sig,
            "top_ids": top_ids,
            "top_distances": [round(float(d), 4) for d in top_distances],
            "hit_at_1": in_top1,
            "hit_at_5": in_top5,
        })
        print(f"        [{qid}] hit@1={in_top1}  hit@5={in_top5}  dists={[round(d,3) for d in top_distances]}")

    print("[5/5] Summary + MLflow logging ...")
    summary: dict[str, dict[str, float | int]] = {}
    for lang in ("en", "ar"):
        b = hits[lang]
        summary[lang] = {
            "n": b["n"],
            "recall_at_1": round(b["r1"] / b["n"], 4) if b["n"] else 0.0,
            "recall_at_5": round(b["r5"] / b["n"], 4) if b["n"] else 0.0,
        }
    total_n = hits["en"]["n"] + hits["ar"]["n"]
    total_r1 = hits["en"]["r1"] + hits["ar"]["r1"]
    total_r5 = hits["en"]["r5"] + hits["ar"]["r5"]
    summary["overall"] = {
        "n": total_n,
        "recall_at_1": round(total_r1 / total_n, 4) if total_n else 0.0,
        "recall_at_5": round(total_r5 / total_n, 4) if total_n else 0.0,
    }

    # Best-effort MLflow logging — one run per language so it's directly
    # comparable to the per-model rows already in the experiment.
    try:
        import mlflow

        mlflow.set_tracking_uri(os.environ.get("MLFLOW_TRACKING_URI", settings.mlflow_tracking_uri))
        mlflow.set_experiment(MLFLOW_EXPERIMENT)
        for lang in ("en", "ar"):
            model_name = settings.embedding_model_ar if lang == "ar" else settings.embedding_model_en
            run_name = f"chromadb-{lang}-{Path(model_name).name}"
            with mlflow.start_run(run_name=run_name):
                mlflow.log_params({
                    "model_name": model_name,
                    "language": lang,
                    "store": "chromadb",
                    "chroma_collection": COLLECTIONS[lang],
                    "hnsw_space": "cosine",
                    "top_k": TOP_K,
                })
                mlflow.log_metrics({
                    "recall_at_1": float(summary[lang]["recall_at_1"]),
                    "recall_at_5": float(summary[lang]["recall_at_5"]),
                    "n_queries": int(summary[lang]["n"]),
                })
    except Exception as exc:
        print(f"      [mlflow] skipped: {exc}")

    payload = {
        "test_set_path": str(TEST_SET_PATH),
        "embedding_model_en": settings.embedding_model_en,
        "embedding_model_ar": settings.embedding_model_ar,
        "chroma_host": settings.chroma_host,
        "chroma_port": settings.chroma_port,
        "collections": COLLECTIONS,
        "hnsw_space": "cosine",
        "top_k": TOP_K,
        "summary": summary,
        "per_query": per_query,
        "stored_ids": {k: {l: len(v) for l, v in ids.items()} for k, ids in stored_ids.items()},
    }
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"      wrote {RESULTS_PATH}")

    print()
    print("=" * 72)
    print("ChromaDB retrieval — recall on the B1 test set")
    print("=" * 72)
    print(f"{'lang':<8} {'model':<32} {'n':>4} {'R@1':>7} {'R@5':>7}")
    print("-" * 72)
    for lang in ("en", "ar"):
        mname = settings.embedding_model_ar if lang == "ar" else settings.embedding_model_en
        s = summary[lang]
        print(f"{lang:<8} {mname:<32} {s['n']:>4} {s['recall_at_1']:>7.3f} {s['recall_at_5']:>7.3f}")
    o = summary["overall"]
    print(f"{'overall':<8} {'(routed)':<32} {o['n']:>4} {o['recall_at_1']:>7.3f} {o['recall_at_5']:>7.3f}")
    print("=" * 72)
    print()
    print("Reference (B1 in-memory cosine, same test set):")
    print("  EN     intfloat/multilingual-e5-base    10  R@1=0.20  R@5=0.80")
    print("  AR     BAAI/bge-m3                      10  R@1=0.40  R@5=0.90")
    print("  ovr    (per-language routed)            20  R@1=0.30  R@5=0.85")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
