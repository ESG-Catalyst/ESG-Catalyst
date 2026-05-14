"""One-time model download script — safe to re-run (skips if already cached).

Downloads:
  1a. intfloat/multilingual-e5-base (~420 MB) — EN sentence embedding
  1b. BAAI/bge-m3 (~2.3 GB)                  — AR sentence embedding
  2.  climatebert/distilroberta-base-climate-detector (~250 MB) — ESG E-pillar
  3.  yiyanghkust/finbert-esg-9-categories (~440 MB) — ESG 9-category classifier
  4.  nbroad/ESG-BERT (~440 MB) — 26 SASB sustainability topics

Models 2-4 form the arch-B ensemble used in the production M2 classifier
(see ``ESG_Catalyst_Wiki/wiki/decisions/classification-architecture.md``).

Embedder uses language-routed bilingual embeddings — EN chunks go through
e5-base, AR chunks through bge-m3. Both must be cached locally.

Run from the project root:
    python scripts/download_models.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

HF_CACHE = Path.home() / ".cache" / "huggingface" / "hub"

EMBEDDING_MODEL_EN = os.environ.get("EMBEDDING_MODEL_EN", "intfloat/multilingual-e5-base")
EMBEDDING_MODEL_AR = os.environ.get("EMBEDDING_MODEL_AR", "BAAI/bge-m3")
CLASSIFIER_MODELS = [
    "climatebert/distilroberta-base-climate-detector",
    "yiyanghkust/finbert-esg-9-categories",
    "nbroad/ESG-BERT",
]


def _cache_dir(model_id: str) -> Path:
    """Return the expected HuggingFace cache directory for a model."""
    slug = model_id.replace("/", "--")
    return HF_CACHE / f"models--{slug}"


def _dir_size_mb(path: Path) -> float:
    total = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
    return total / (1024 * 1024)


def download_embedding_model(model_id: str) -> None:
    cache = _cache_dir(model_id)
    if cache.exists():
        print(f"  [cached] {model_id}  ({_dir_size_mb(cache):.0f} MB)")
        return

    print(f"  [downloading] {model_id} ...")
    from sentence_transformers import SentenceTransformer

    SentenceTransformer(model_id)
    print(f"  [ok] {model_id}  ({_dir_size_mb(cache):.0f} MB)")


def download_classifier_model(model_id: str) -> None:
    cache = _cache_dir(model_id)
    if cache.exists():
        print(f"  [cached] {model_id}  ({_dir_size_mb(cache):.0f} MB)")
        return

    print(f"  [downloading] {model_id} ...")
    from transformers import pipeline as hf_pipeline

    hf_pipeline(
        "text-classification",
        model=model_id,
        top_k=None,
        truncation=True,
        max_length=512,
    )
    print(f"  [ok] {model_id}  ({_dir_size_mb(cache):.0f} MB)")


def main() -> None:
    print("ESG Catalyst — model download")
    print(f"Cache: {HF_CACHE}\n")

    print("1. Sentence-embedding models (language-routed)")
    print("  1a. English ->")
    download_embedding_model(EMBEDDING_MODEL_EN)
    print("  1b. Arabic ->")
    download_embedding_model(EMBEDDING_MODEL_AR)

    print("\n2. ESG classifier ensemble (arch-B)")
    for i, model_id in enumerate(CLASSIFIER_MODELS, start=1):
        print(f"  2.{i}  {model_id}")
        download_classifier_model(model_id)

    print("\nAll models ready.")


if __name__ == "__main__":
    main()
