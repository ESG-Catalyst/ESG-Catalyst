"""Embedding pipeline — encode chunks with multilingual E5 and store in ChromaDB.

Uses ``sentence-transformers`` with the model specified in ``settings.embedding_model``
(default: ``paraphrase-multilingual-e5-base``).  Handles Arabic + English equally.

Usage:
    from app.core.nlp.embedder import compute_embeddings, embed_and_store

    embedded = compute_embeddings(chunks)
    ids = embed_and_store(chunks, collection_name="document_chunks")
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import structlog
from sentence_transformers import SentenceTransformer

from app.config import settings
from app.core.nlp.chunker import Chunk

logger = structlog.get_logger(__name__)

_model: SentenceTransformer | None = None


# ── Data class ───────────────────────────────────────────────────────────
@dataclass
class EmbeddedChunk:
    """A chunk with its computed embedding vector."""

    chunk: Chunk
    embedding: np.ndarray  # shape (dim,)

    @property
    def dimension(self) -> int:
        return self.embedding.shape[0]


# ── Model loading ────────────────────────────────────────────────────────
def _get_model() -> SentenceTransformer:
    """Lazy-load and cache the sentence-transformer model."""
    global _model
    if _model is None:
        model_name = settings.embedding_model
        logger.info("embedder.loading_model", model=model_name)
        _model = SentenceTransformer(model_name)
        logger.info(
            "embedder.model_loaded",
            model=model_name,
            dimension=_model.get_sentence_embedding_dimension(),
        )
    return _model


# ── Prefix handling for E5 models ────────────────────────────────────────
def _prepare_texts(texts: list[str]) -> list[str]:
    """Add ``passage:`` prefix for E5 family models (improves retrieval quality)."""
    if "e5" in settings.embedding_model.lower():
        return [f"passage: {t}" for t in texts]
    return texts


# ── Public API ───────────────────────────────────────────────────────────
def compute_embeddings(chunks: list[Chunk]) -> list[EmbeddedChunk]:
    """Compute embedding vectors for a list of chunks (no ChromaDB needed).

    Args:
        chunks: Output of ``chunk_document()``.

    Returns:
        List of ``EmbeddedChunk`` with numpy vectors.
    """
    if not chunks:
        return []

    model = _get_model()
    texts = _prepare_texts([c.text for c in chunks])

    logger.info("embedder.encoding", count=len(texts))
    vectors = model.encode(
        texts,
        show_progress_bar=False,
        normalize_embeddings=True,
        batch_size=32,
    )

    result = [
        EmbeddedChunk(chunk=chunk, embedding=vec)
        for chunk, vec in zip(chunks, vectors)
    ]
    logger.info(
        "embedder.encoded",
        count=len(result),
        dimension=result[0].dimension if result else 0,
    )
    return result


def embed_and_store(
    chunks: list[Chunk],
    collection_name: str = "document_chunks",
    company_id: str | None = None,
    report_id: str | None = None,
) -> list[str]:
    """Compute embeddings and upsert into a ChromaDB collection.

    Args:
        chunks: Output of ``chunk_document()``.
        collection_name: ChromaDB collection (``document_chunks`` or ``corrections_store``).
        company_id: Optional filter metadata.
        report_id: Optional filter metadata.

    Returns:
        List of ``chunk_id`` strings stored in ChromaDB.
    """
    import chromadb

    embedded = compute_embeddings(chunks)
    if not embedded:
        return []

    client = chromadb.HttpClient(host=settings.chroma_host, port=settings.chroma_port)
    collection = client.get_or_create_collection(
        name=collection_name,
        metadata={"hnsw:space": "cosine"},
    )

    ids = [ec.chunk.chunk_id for ec in embedded]
    embeddings = [ec.embedding.tolist() for ec in embedded]
    documents = [ec.chunk.text for ec in embedded]
    metadatas = [
        {
            "source_file": ec.chunk.source_file,
            "page_number": ec.chunk.page_number,
            "section_header": ec.chunk.section_header or "",
            "chunk_type": ec.chunk.chunk_type,
            "company_id": company_id or "",
            "report_id": report_id or "",
        }
        for ec in embedded
    ]

    collection.upsert(
        ids=ids,
        embeddings=embeddings,
        documents=documents,
        metadatas=metadatas,
    )

    logger.info("embedder.stored", collection=collection_name, count=len(ids))
    return ids
