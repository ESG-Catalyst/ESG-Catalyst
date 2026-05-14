"""One-time model download script — safe to re-run (skips if already cached).

Downloads:
  1. intfloat/multilingual-e5-base (~420 MB)  — sentence embedding
  2. climatebert/distilroberta-base-climate-detector (~250 MB) — ESG classifier

Run from the project root:
    python scripts/download_models.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

HF_CACHE = Path.home() / ".cache" / "huggingface" / "hub"

EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "intfloat/multilingual-e5-base")
CLASSIFIER_MODEL = "climatebert/distilroberta-base-climate-detector"


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

    print("1. Sentence-embedding model")
    download_embedding_model(EMBEDDING_MODEL)

    print("\n2. ClimateBERT classifier")
    download_classifier_model(CLASSIFIER_MODEL)

    print("\nAll models ready.")


if __name__ == "__main__":
    main()
