"""Embedding pipeline — language-routed bilingual embeddings + ChromaDB.

Each chunk is auto-detected as Arabic or English from a Unicode-range
heuristic, then encoded with the model best-suited to that language:

    EN chunks → ``settings.embedding_model_en`` (default: multilingual-e5-base)
    AR chunks → ``settings.embedding_model_ar`` (default: BAAI/bge-m3)

Justification (see ``scripts/experiments/results/embedding_comparison.json``
and MLflow experiment ``m2-embedding-experiments``):

    *  e5-base   AR R@5 = 0.80  | EN R@5 = 0.80  | 126 s | 1.6 GB RAM
    *  bge-m3    AR R@5 = 0.90  | EN R@5 = 0.80  | 696 s | 2.6 GB RAM

bge-m3 lifts AR retrieval by 10 points but costs 5.5× the encode time
of e5-base. Splitting per language means we only pay the bge-m3 cost on
AR chunks, while EN chunks (the majority of the MENA banking corpus today)
keep the cheaper e5-base path.

Both models load once per process (lazy singleton). Call ``preload_models``
at startup if you want the cold-start cost paid up front instead of on
the first encode.

ChromaDB collections are created with ``hnsw:space=cosine`` because both
e5 and bge-m3 produce L2-normalised vectors — the default L2 distance
would penalise on magnitude noise instead of angle. Existing collections
created with default L2 must be deleted + re-embedded (one-time migration).

Usage:
    from app.core.nlp.embedder import embed_chunks, embed_and_store, embed_query

    embedded = embed_chunks(chunks)             # list[EmbeddedChunk], routed per chunk
    out = embed_and_store(chunks, company_id="…")  # writes to document_chunks_en / _ar
    qvec = embed_query("How many female directors?", lang="en")
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

import numpy as np
import structlog
from sentence_transformers import SentenceTransformer

from app.config import settings
from app.core.nlp.chunker import Chunk

logger = structlog.get_logger(__name__)


# ── Public types ────────────────────────────────────────────────────────
Language = Literal["en", "ar"]


@dataclass
class EmbeddedChunk:
    """A chunk paired with its embedding vector and detected language."""

    chunk: Chunk
    embedding: np.ndarray  # shape (dim,), L2-normalised
    language: Language

    @property
    def dimension(self) -> int:
        return self.embedding.shape[0]


# ── Language detection (chunk-level) ────────────────────────────────────
# Covers Arabic, Arabic Supplement, Arabic Extended-A, Arabic Presentation
# Forms-A and -B. Tested on the ADIB AR PDF (consistently >40% Arabic
# chars per chunk) and the Beltone EN PDF (0% Arabic chars per chunk).
_ARABIC_CHAR_RE = re.compile(
    r"[؀-ۿݐ-ݿࢠ-ࣿﭐ-﷿ﹰ-﻿]"
)
_AR_DETECT_THRESHOLD = 0.10  # ≥10% Arabic chars → classify as AR


def detect_chunk_language(text: str) -> Language:
    """Classify a chunk as ``"ar"`` or ``"en"`` from its Unicode character mix.

    A chunk is treated as Arabic when ≥10% of its characters fall in any
    Arabic Unicode block. The 10% floor handles bilingual chunks (e.g.
    ADIB pages mixing Arabic body text with English company names + ratios)
    while still routing them to the AR-specialist model where it matters.
    """
    if not text:
        return "en"
    n_ar = len(_ARABIC_CHAR_RE.findall(text))
    return "ar" if (n_ar / len(text)) >= _AR_DETECT_THRESHOLD else "en"


# ── Model loading (lazy singleton, one per language) ────────────────────
_models: dict[Language, SentenceTransformer | None] = {"en": None, "ar": None}


def _model_name_for(lang: Language) -> str:
    return settings.embedding_model_ar if lang == "ar" else settings.embedding_model_en


def _get_model(lang: Language) -> SentenceTransformer:
    """Lazy-load and cache the sentence-transformer model for ``lang``."""
    cached = _models[lang]
    if cached is not None:
        return cached
    model_name = _model_name_for(lang)
    logger.info("embedder.loading_model", lang=lang, model=model_name)
    model = SentenceTransformer(model_name)
    _models[lang] = model
    logger.info(
        "embedder.model_loaded",
        lang=lang,
        model=model_name,
        dimension=model.get_sentence_embedding_dimension(),
    )
    return model


def preload_models() -> None:
    """Eagerly load both EN and AR models. Call at worker startup to pay
    cold-start cost up front rather than on the first request."""
    _get_model("en")
    _get_model("ar")


# ── Prefix handling (E5 family expects ``passage:`` / ``query:``) ───────
def _prepare_texts(texts: list[str], lang: Language, role: Literal["passage", "query"]) -> list[str]:
    """Add ``passage:`` / ``query:`` prefix for E5 family models."""
    if "e5" in _model_name_for(lang).lower():
        return [f"{role}: {t}" for t in texts]
    return texts


# ── Public API ──────────────────────────────────────────────────────────
def embed_chunks(chunks: list[Chunk]) -> list[EmbeddedChunk]:
    """Embed a list of chunks via language-routed bilingual models.

    Chunks are partitioned by detected language, each partition encoded
    with the appropriate model in a single batched call, then results
    are merged back in original order.

    Args:
        chunks: Output of ``chunk_document()``.

    Returns:
        ``EmbeddedChunk`` list, same order as the input chunks.
    """
    if not chunks:
        return []

    # Partition by language while keeping original positions.
    buckets: dict[Language, list[tuple[int, Chunk]]] = {"en": [], "ar": []}
    for i, c in enumerate(chunks):
        buckets[detect_chunk_language(c.text)].append((i, c))

    out: list[EmbeddedChunk | None] = [None] * len(chunks)
    for lang in ("en", "ar"):
        items = buckets[lang]  # type: ignore[index]
        if not items:
            continue
        model = _get_model(lang)  # type: ignore[arg-type]
        prepared = _prepare_texts([c.text for _, c in items], lang, role="passage")  # type: ignore[arg-type]
        vectors = model.encode(
            prepared,
            batch_size=32,
            show_progress_bar=False,
            normalize_embeddings=True,
        )
        for (idx, chunk), vec in zip(items, vectors):
            out[idx] = EmbeddedChunk(chunk=chunk, embedding=vec, language=lang)  # type: ignore[arg-type]

    logger.info(
        "embedder.encoded",
        count=len(chunks),
        en=len(buckets["en"]),
        ar=len(buckets["ar"]),
    )
    # All slots are filled (we covered both languages above).
    return [ec for ec in out if ec is not None]


# Backward-compat alias — existing callers (e.g. backend/test_nlp.py) and
# any imports from ``app.core.nlp.embedder import compute_embeddings`` keep
# working. New code should prefer ``embed_chunks``.
compute_embeddings = embed_chunks


def embed_query(query: str, lang: Language | None = None) -> np.ndarray:
    """Embed a single query string for retrieval.

    Args:
        query: The user's natural-language query.
        lang: Override language routing. If None, auto-detected from the
              query text — same heuristic as for chunks.

    Returns:
        L2-normalised numpy vector. Use ``np.dot(q, chunk_vec)`` for cosine.
    """
    if lang is None:
        lang = detect_chunk_language(query)
    model = _get_model(lang)
    prepared = _prepare_texts([query], lang, role="query")
    return model.encode(prepared, normalize_embeddings=True, show_progress_bar=False)[0]


# ── ChromaDB persistence (one collection per language) ──────────────────
def _collection_name(lang: Language) -> str:
    return f"document_chunks_{lang}"


def embed_and_store(
    chunks: list[Chunk],
    company_id: str | None = None,
    report_id: str | None = None,
) -> dict[Language, list[str]]:
    """Compute embeddings and upsert into per-language ChromaDB collections.

    Two collections are written to (created on demand with cosine distance):
        * ``document_chunks_en`` — 768-d (multilingual-e5-base)
        * ``document_chunks_ar`` — 1024-d (BAAI/bge-m3)

    Args:
        chunks: Output of ``chunk_document()``.
        company_id: Optional metadata filter.
        report_id: Optional metadata filter.

    Returns:
        ``{"en": [chunk_id, ...], "ar": [chunk_id, ...]}`` — IDs that were
        written, partitioned by detected language.
    """
    import chromadb

    embedded = embed_chunks(chunks)
    if not embedded:
        return {"en": [], "ar": []}

    client = chromadb.HttpClient(host=settings.chroma_host, port=settings.chroma_port)

    buckets: dict[Language, list[EmbeddedChunk]] = {"en": [], "ar": []}
    for ec in embedded:
        buckets[ec.language].append(ec)

    out: dict[Language, list[str]] = {"en": [], "ar": []}
    for lang in ("en", "ar"):
        items = buckets[lang]  # type: ignore[index]
        if not items:
            continue
        collection = client.get_or_create_collection(
            name=_collection_name(lang),  # type: ignore[arg-type]
            metadata={"hnsw:space": "cosine"},
        )
        ids = [ec.chunk.chunk_id for ec in items]
        embeddings = [ec.embedding.tolist() for ec in items]
        documents = [ec.chunk.text for ec in items]
        metadatas = [
            {
                "source_file": ec.chunk.source_file,
                "page_number": ec.chunk.page_number,
                "section_header": ec.chunk.section_header or "",
                "chunk_type": ec.chunk.chunk_type,
                "language": ec.language,
                "company_id": company_id or "",
                "report_id": report_id or "",
            }
            for ec in items
        ]
        collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas,
        )
        logger.info(
            "embedder.stored",
            collection=_collection_name(lang),  # type: ignore[arg-type]
            count=len(ids),
        )
        out[lang] = ids  # type: ignore[index]

    return out
