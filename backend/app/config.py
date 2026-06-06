"""Application configuration — loaded from environment variables / .env.

All settings are declared as typed Pydantic fields so that:
  - missing required values fail at startup, not at first use
  - every setting is discoverable in one place
  - model defaults are visible in the running process (e.g. /health)

Usage:
    from app.config import settings

    settings.database_url          # "postgresql+asyncpg://..."
    settings.models["extraction"]  # built by _build_models_dict
"""

from __future__ import annotations

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application-wide configuration populated from environment variables.

    Pydantic-settings reads variables from the OS environment first, then
    falls back to a ``.env`` file in the current working directory.  All
    field names map directly to the upper-cased environment variable name
    (e.g. ``database_url`` ← ``DATABASE_URL``).

    Never add secrets as hard-coded default values — use placeholder strings
    that will obviously fail in production (empty string, ``"change-me"``,
    etc.).
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        # Unknown env vars are silently ignored so third-party tooling can
        # co-exist without causing startup failures.
        extra="ignore",
        # Allow both snake_case and the aliased UPPER_CASE forms when
        # constructing Settings programmatically in tests.
        populate_by_name=True,
    )

    # ── Database ─────────────────────────────────────────────────────────────
    # Default: SQLite (local dev, no Postgres needed).
    # Override: DATABASE_URL=postgresql+asyncpg://user:pass@host:port/db
    database_url: str = Field(
        default="sqlite+aiosqlite:///./esg_catalyst.db",
        description=(
            "SQLAlchemy async database URL. "
            "Use postgresql+asyncpg:// for production; "
            "sqlite+aiosqlite:// is the local-dev fallback."
        ),
    )

    # ── Redis / Celery broker ────────────────────────────────────────────────
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        description=(
            "Redis URL used as both Celery broker and result backend. "
            "Format: redis://<host>:<port>/<db-index>"
        ),
    )

    # ── LLM model IDs ────────────────────────────────────────────────────────
    # These are assembled into settings.models / settings.model_fallbacks by
    # _build_models_dict so ModelRouter can read them as a dict.
    #
    # Supported prefixes:
    #   groq/<model>              → Groq API (free, fast)
    #   openrouter/<provider>/<model>  → OpenRouter (paid + free tiers)
    openrouter_api_key: str = Field(
        default="",
        description="OpenRouter API key (sk-or-...). Required only for openrouter/ model IDs.",
    )
    groq_api_key: str = Field(
        default="",
        description=(
            "Groq API key (gsk_...). Required for groq/ model IDs. "
            "Free keys available at https://console.groq.com"
        ),
    )
    model_extraction: str = Field(
        default="groq/llama-3.1-8b-instant",
        description="Primary model for M3 metric extraction.",
    )
    model_extraction_fallback: str = Field(
        default="openrouter/qwen/qwen-2.5-7b-instruct:free",
        description=(
            "Free-tier fallback for M3 extraction. Activated on HTTP 402 / "
            "rate-limit from the primary model."
        ),
    )
    model_scoring: str = Field(
        default="groq/llama-3.3-70b-versatile",
        description="Model used for M4 LLM-assisted scoring (gap analysis narratives).",
    )
    model_report: str = Field(
        default="groq/llama-3.3-70b-versatile",
        description="Primary model for M5 report narrative generation.",
    )
    model_report_fallback: str = Field(
        default="groq/llama-3.1-8b-instant",
        description="Free-tier fallback for M5 report narrative generation.",
    )

    # ── LLM completion-length caps (per task) ────────────────────────────────
    # An UNCAPPED request defaults to the model's full output ceiling (e.g.
    # 64000 tokens for Claude Sonnet). OpenRouter's affordability pre-check then
    # reserves credit for that entire ceiling — so a tiny prompt 402s on a low
    # balance ("requires more credits, or fewer max_tokens"). Capping per task
    # both fixes that and bounds runaway generations. These are assembled into
    # settings.model_max_tokens by _build_models_dict and injected by
    # ModelRouter.ainvoke_with_fallback. Tune via env without code changes.
    model_extraction_max_tokens: int = Field(
        default=2000,
        description=(
            "Max completion tokens per M3 extraction call. One indicator's JSON "
            "response is a few hundred tokens, so 2000 is ample headroom while "
            "staying affordable on a low OpenRouter balance. "
            "Env: MODEL_EXTRACTION_MAX_TOKENS."
        ),
    )
    model_scoring_max_tokens: int = Field(
        default=2000,
        description=(
            "Max completion tokens per M4 LLM-assisted scoring call (unused in "
            "v1 deterministic scoring; kept for future LLM gap narratives). "
            "Env: MODEL_SCORING_MAX_TOKENS."
        ),
    )
    model_report_max_tokens: int = Field(
        default=3000,
        description=(
            "Max completion tokens per M5 narrative call. Narratives are "
            "generated one-section-per-call, so each only needs a single "
            "section of prose. Env: MODEL_REPORT_MAX_TOKENS."
        ),
    )

    # Assembled dicts consumed by ModelRouter — populated by _build_models_dict.
    # Do NOT set these directly via env vars; they are derived fields.
    models: dict[str, str] = Field(
        default_factory=dict,
        description="Derived: task → primary model ID. Built by _build_models_dict.",
    )
    model_fallbacks: dict[str, str] = Field(
        default_factory=dict,
        description="Derived: task → fallback model ID. Built by _build_models_dict.",
    )
    model_max_tokens: dict[str, int] = Field(
        default_factory=dict,
        description="Derived: task → max completion tokens. Built by _build_models_dict.",
    )

    @model_validator(mode="after")
    def _build_models_dict(self) -> "Settings":
        """Assemble the models / model_fallbacks dicts from individual fields.

        Called after all field validators run so all model_* fields are already
        resolved from env vars.  ModelRouter reads these dicts exclusively —
        it never reads model_extraction etc. directly.
        """
        self.models = {
            "extraction": self.model_extraction,
            "scoring": self.model_scoring,
            "report": self.model_report,
        }
        self.model_fallbacks = {
            "extraction": self.model_extraction_fallback,
            # report fallback added 2026-05-10 — was missing, caused silent
            # no-fallback bug when primary 402'd during report generation.
            "report": self.model_report_fallback,
        }
        self.model_max_tokens = {
            "extraction": self.model_extraction_max_tokens,
            "scoring": self.model_scoring_max_tokens,
            "report": self.model_report_max_tokens,
        }
        return self

    # ── Vector store (ChromaDB) ──────────────────────────────────────────────
    chroma_host: str = Field(
        default="localhost",
        description="ChromaDB HTTP host. Use the docker-compose service name inside containers.",
    )
    chroma_port: int = Field(
        default=8001,
        description="ChromaDB HTTP port. Default 8001 to avoid collision with the API (8000).",
    )

    # ── Embeddings ───────────────────────────────────────────────────────────
    # Language-routed: EN chunks use embedding_model_en, AR chunks use
    # embedding_model_ar.  Both models are downloaded once by
    # scripts/download_models.py and loaded lazily on first encode call.
    embedding_model_en: str = Field(
        default="intfloat/multilingual-e5-base",
        description=(
            "HuggingFace model ID for English chunk embeddings. "
            "Used by embedder.py when the chunk language is 'en'. "
            "Default: multilingual-e5-base (768d, 1.6 GB RAM)."
        ),
    )
    embedding_model_ar: str = Field(
        default="BAAI/bge-m3",
        description=(
            "HuggingFace model ID for Arabic chunk embeddings. "
            "Used by embedder.py when the chunk language is 'ar'. "
            "Default: bge-m3 (1024d, 2.6 GB RAM) — 10pp better AR recall "
            "than e5-base per M2-B1 benchmark."
        ),
    )
    # Legacy single-model alias kept for back-compat with code that was written
    # before the bilingual split (embedder.py B2 session 2026-05-14).
    # Always mirrors embedding_model_en; do not set it to something different.
    embedding_model: str = Field(
        default="intfloat/multilingual-e5-base",
        description=(
            "Legacy alias — mirrors embedding_model_en. "
            "Kept for back-compat; prefer embedding_model_en / embedding_model_ar."
        ),
    )

    # ── Chunker ──────────────────────────────────────────────────────────────
    # Two strategies available — switch via CHUNK_STRATEGY env var, no code change.
    #   sentence_window — A2 winner (3-sent window, stride 1, 1500-char hard cap)
    #   block_merge     — legacy regex + header-merge approach
    chunk_strategy: str = Field(
        default="sentence_window",
        description=(
            "Chunking strategy. "
            "'sentence_window' (default, A2 winner) or 'block_merge' (legacy). "
            "Switch via CHUNK_STRATEGY env var without code changes."
        ),
    )
    # sentence_window knobs
    chunk_window_sentences: int = Field(
        default=3,
        description="sentence_window: number of sentences per window (A2 tuning winner: 3).",
    )
    chunk_stride_sentences: int = Field(
        default=1,
        description="sentence_window: stride between consecutive windows (A2 tuning winner: 1).",
    )
    chunk_max_chars: int = Field(
        default=1500,
        description=(
            "sentence_window: hard character cap per chunk. "
            "Prevents table rows without sentence terminators from ballooning. "
            "(A2 tuning winner: 1500 — only 1.3% of chunks exceed 512 tokens.)"
        ),
    )
    # block_merge knobs (legacy)
    chunk_size_chars: int = Field(
        default=2000,
        description="block_merge only: target chunk size in characters.",
    )
    chunk_overlap_chars: int = Field(
        default=200,
        description="block_merge only: overlap between consecutive chunks in characters.",
    )

    # ── Extraction (M3 per-indicator retrieval) ──────────────────────────────
    extraction_top_k: int = Field(
        default=3,
        description=(
            "Chunks retrieved per indicator from ChromaDB. "
            "3 = faster / lower cost; 5 = more context for difficult indicators."
        ),
    )
    extraction_min_chunks: int = Field(
        default=1,
        description=(
            "Minimum chunks retrieved before an LLM extraction call is issued. "
            "If ChromaDB returns fewer than this, the indicator is skipped "
            "(status=missing, no LLM call)."
        ),
    )
    extraction_concurrency: int = Field(
        default=4,
        description=(
            "How many per-indicator LLM extraction calls run concurrently. "
            "Local Ollama queues internally so 4–6 is safe; "
            "remote APIs (Groq / OpenRouter) may need 2–3 to stay under rate limits."
        ),
    )

    # ── Auth ─────────────────────────────────────────────────────────────────
    secret_key: str = Field(
        default="dev-secret-change-in-production",
        description=(
            "HS256 JWT signing key. MUST be overridden in production. "
            "Generate with: python -c \"import secrets; print(secrets.token_hex(32))\""
        ),
    )
    access_token_expire_minutes: int = Field(
        default=30,
        description="JWT access token lifetime in minutes.",
    )

    # ── MLflow experiment tracking ───────────────────────────────────────────
    mlflow_tracking_uri: str = Field(
        default="http://localhost:5001",
        description=(
            "MLflow tracking server URL. "
            "Set to 'http://mlflow:5001' inside docker-compose containers. "
            "mlflow_tracker.py wraps all calls in try/except so a dead server "
            "cannot break the pipeline."
        ),
    )

    # ── Application ──────────────────────────────────────────────────────────
    environment: str = Field(
        default="development",
        description="Runtime environment. Controls SQL echo and debug modes.",
    )
    max_upload_size_mb: int = Field(
        default=50,
        description="Maximum upload file size in megabytes. Enforced in documents.py.",
    )
    confidence_threshold: float = Field(
        default=0.80,
        description=(
            "Minimum extraction confidence to mark a metric 'extracted' vs 'ambiguous'. "
            "Used in extractor.py and scorer.py. Does NOT gate the M2 classifier."
        ),
    )

    # ── M5 PDF renderer backend ──────────────────────────────────────────────
    pdf_backend: str = Field(
        default="auto",
        description=(
            "PDF rendering backend for report generation. "
            "'auto'       — WeasyPrint primary, PyMuPDF Story fallback (default). "
            "'weasyprint' — WeasyPrint only; raises if GTK3 unavailable. "
            "'pymupdf'    — skip WeasyPrint entirely. One-line revert if WeasyPrint regresses."
        ),
    )

    # ── Field validators ─────────────────────────────────────────────────────

    @field_validator("environment")
    @classmethod
    def _validate_environment(cls, v: str) -> str:
        """Normalise to lower-case and reject obviously wrong values."""
        v = v.lower().strip()
        allowed = {"development", "staging", "production", "test"}
        if v not in allowed:
            raise ValueError(
                f"ENVIRONMENT must be one of {sorted(allowed)!r}, got {v!r}"
            )
        return v

    @field_validator("pdf_backend")
    @classmethod
    def _validate_pdf_backend(cls, v: str) -> str:
        """Normalise to lower-case and reject unrecognised backend names."""
        v = v.lower().strip()
        allowed = {"auto", "weasyprint", "pymupdf"}
        if v not in allowed:
            raise ValueError(
                f"PDF_BACKEND must be one of {sorted(allowed)!r}, got {v!r}"
            )
        return v

    @field_validator("confidence_threshold")
    @classmethod
    def _validate_confidence_threshold(cls, v: float) -> float:
        """Confidence must be a probability in [0, 1]."""
        if not (0.0 <= v <= 1.0):
            raise ValueError(
                f"CONFIDENCE_THRESHOLD must be in [0.0, 1.0], got {v}"
            )
        return v

    @field_validator("extraction_top_k", "extraction_min_chunks", "extraction_concurrency")
    @classmethod
    def _validate_positive_int(cls, v: int) -> int:
        """Extraction knobs must be positive integers."""
        if v < 1:
            raise ValueError(f"Value must be >= 1, got {v}")
        return v


# Module-level singleton — import this everywhere.
settings = Settings()
