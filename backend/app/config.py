from __future__ import annotations

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Database (default: SQLite for local dev; override with DATABASE_URL env var for Postgres)
    database_url: str = "sqlite+aiosqlite:///./esg_catalyst.db"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # LLM — individual env vars, assembled into dict by validator below
    openrouter_api_key: str = ""
    model_extraction: str = "openrouter/anthropic/claude-3.5-sonnet"
    model_extraction_fallback: str = "openrouter/meta-llama/llama-3.3-70b-instruct:free"
    model_scoring: str = "openrouter/meta-llama/llama-3.1-70b-instruct"
    model_report: str = "openrouter/anthropic/claude-3.5-sonnet"
    model_report_fallback: str = "openrouter/mistralai/mistral-7b-instruct:free"

    # Assembled dict used by ModelRouter: settings.models["extraction"]
    models: dict[str, str] = {}
    model_fallbacks: dict[str, str] = {}

    @model_validator(mode="after")
    def _build_models_dict(self) -> "Settings":
        self.models = {
            "extraction": self.model_extraction,
            "scoring": self.model_scoring,
            "report": self.model_report,
        }
        self.model_fallbacks = {
            "extraction": self.model_extraction_fallback,
            "report": self.model_report_fallback,
        }
        return self

    # Vector store
    chroma_host: str = "localhost"
    chroma_port: int = 8001

    # Embeddings (local models — no API key). Separate models per language:
    # EN chunks → embedding_model_en; AR chunks → embedding_model_ar. The
    # legacy ``embedding_model`` field is kept as a fallback for callers that
    # haven't migrated, and mirrors the EN model.
    embedding_model_en: str = "intfloat/multilingual-e5-base"
    embedding_model_ar: str = "BAAI/bge-m3"
    embedding_model: str = "intfloat/multilingual-e5-base"

    # Chunker — strategy + per-strategy knobs. Switching strategy is an
    # env-var change (CHUNK_STRATEGY=...) — no code change required.
    # Valid values:
    #   "sentence_window" — A2 winner: 3-sentence window, stride 1, 1500-char cap
    #   "block_merge"     — legacy header/table-aware merge of regex blocks
    chunk_strategy: str = "sentence_window"
    chunk_window_sentences: int = 3        # sentence_window only
    chunk_stride_sentences: int = 1        # sentence_window only
    chunk_max_chars: int = 1500            # sentence_window only — hard cap
    chunk_size_chars: int = 2000           # block_merge only
    chunk_overlap_chars: int = 200         # block_merge only

    # Auth
    secret_key: str = "dev-secret-change-in-production"
    access_token_expire_minutes: int = 30

    # MLflow
    mlflow_tracking_uri: str = "http://localhost:5001"

    # App
    environment: str = "development"
    max_upload_size_mb: int = 50
    confidence_threshold: float = 0.80


settings = Settings()
