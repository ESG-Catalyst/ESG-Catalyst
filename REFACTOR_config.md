# REFACTOR_config — Agent C Deliverable

Scope: `backend/app/config.py`, `backend/app/database.py`,
`backend/app/workers/celery_app.py`, `.env.example`

---

## 1. What changed and why

### backend/app/config.py

| Change | Why |
|--------|-----|
| Added `populate_by_name=True` to `SettingsConfigDict` | Allows constructing `Settings(database_url=...)` in tests without needing alias names. No runtime effect in production (env-var loading unaffected). |
| Replaced bare `str = "..."` field declarations with `Field(default=..., description=...)` for every field | Descriptions show up in auto-generated JSON schema (`Settings.model_json_schema()`), useful for /health and tooling. No runtime impact. |
| Added `@field_validator("environment")` | Normalises to lower-case and raises `ValueError` if an unrecognised string (e.g. `"prod"` typo) is supplied, rather than silently passing a string that no `if settings.environment == "production"` branch would ever match. Allowed values: `development`, `staging`, `production`, `test`. |
| Added `@field_validator("pdf_backend")` | Same rationale — the renderer does a `.lower()` check already, but a typo in `PDF_BACKEND` produced silent fallback to `"auto"` behaviour. Validator now rejects at startup. Allowed values: `auto`, `weasyprint`, `pymupdf`. |
| Added `@field_validator("confidence_threshold")` | Clamps to `[0.0, 1.0]`. An out-of-range value (e.g. `CONFIDENCE_THRESHOLD=80` instead of `0.80`) would cause every metric to be marked `ambiguous` with no error — now caught at startup. |
| Added `@field_validator("extraction_top_k", "extraction_min_chunks", "extraction_concurrency")` | Rejects zero/negative values for extraction knobs. |
| Grouped fields with Unicode box-drawing section headers | Matches the section layout in `.env.example` — easier to navigate when both files are open side-by-side. |
| Module-level docstring explaining singleton usage | Was previously undocumented. |

**Fields verified live (grep confirmed, not removed):** `database_url`,
`redis_url`, `openrouter_api_key`, `groq_api_key`, `model_extraction`,
`model_extraction_fallback`, `model_scoring`, `model_report`,
`model_report_fallback`, `models` (dict), `model_fallbacks` (dict),
`chroma_host`, `chroma_port`, `embedding_model_en`, `embedding_model_ar`,
`embedding_model`, `chunk_strategy`, `chunk_window_sentences`,
`chunk_stride_sentences`, `chunk_max_chars`, `chunk_size_chars`,
`chunk_overlap_chars`, `extraction_top_k`, `extraction_min_chunks`,
`extraction_concurrency`, `secret_key`, `access_token_expire_minutes`,
`mlflow_tracking_uri`, `environment`, `max_upload_size_mb`,
`confidence_threshold`, `pdf_backend`.

### backend/app/database.py

| Change | Why |
|--------|-----|
| Expanded module docstring to explain NullPool rationale and lazy-init design | Future reader / new team member might "fix" NullPool not knowing it is load-bearing. Now the reason is hard to miss. |
| Added `Base` class docstring | Missing, now consistent with Google-style docstring convention. |
| Added full Google-style docstrings to `get_engine`, `get_session_factory`, `get_db` | Were brief or absent. Now explains `NullPool`, `expire_on_commit=False`, and rollback behaviour. |
| Added `Usage` blocks to module docstring | Shows both FastAPI `Depends` pattern and Celery/script direct usage. |

**No logic changes.** `NullPool`, `lru_cache(maxsize=1)`, `expire_on_commit=False`, and the try/except commit/rollback pattern are all preserved exactly.

### backend/app/workers/celery_app.py

| Change | Why |
|--------|-----|
| Expanded module docstring with startup command examples | Shows the `PYTHONPATH=backend` requirement and the `--max-tasks-per-child=1` flag (see Flagged section). |
| Added inline comments on every `celery_app.conf.update` key | `worker_prefetch_multiplier=1` and `task_acks_late=True` had no explanation; new team members might "fix" them back to defaults. |
| Added future-routing comment | Placeholder for Iteration 3 named queues. |

**No logic changes.** All existing config keys (`task_serializer`, `accept_content`, `result_serializer`, `timezone`, `enable_utc`, `result_expires`, `worker_prefetch_multiplier`, `task_acks_late`) are unchanged.

### .env.example

| Change | Why |
|--------|-----|
| Added `CHUNK_STRATEGY`, `CHUNK_WINDOW_SENTENCES`, `CHUNK_STRIDE_SENTENCES`, `CHUNK_MAX_CHARS` | These settings fields existed in `config.py` since 2026-05-14 A2 session but were missing from `.env.example`. Operators had no way to discover them from the example file. |
| Added `CHUNK_SIZE_CHARS`, `CHUNK_OVERLAP_CHARS` | Same — block_merge legacy knobs were absent. |
| Added `EXTRACTION_TOP_K`, `EXTRACTION_MIN_CHUNKS`, `EXTRACTION_CONCURRENCY` | Added to `config.py` in 2026-05-26 retrieval port session. Missing from `.env.example`. |
| Added `MODEL_REPORT_FALLBACK` | Was already in `config.py`; absent from `.env.example`. |
| Added section header comments (`# ── Section ──`) with brief explanations for every group | `.env.example` previously had some sections without headers and no comments on newer fields. |
| Kept `EMBEDDING_MODEL` legacy alias entry with explicit comment | Back-compat — embedder.py still reads `settings.embedding_model` for callers that didn't migrate to the bilingual split. |
| Kept `GROQ_API_KEY` entry | Already present; kept unchanged. |

**Removed nothing.** Every variable that was in the old `.env.example` is still present. Only additions were made.

---

## 2. Flagged for reconciliation (not fixed — out of scope)

### F1 — `--max-tasks-per-child=1` not in docker-compose
**File:** `docker-compose.yml` (not in Agent C scope)
**Issue:** The CLAUDE.md session log (2026-05-18 E2E row) calls this out as a known must-fix: "Celery solo worker process dies after classifying large Arabic PDFs (~2000 chunks, ~70min CPU); ... requires `docker restart esg_worker` to resume." The fix is a one-line change to the worker service `command:` in `docker-compose.yml`. Cannot add this here — file is out of scope for Agent C.
**Recommended fix:**
```yaml
# docker-compose.yml, worker service:
command: >
  celery -A app.workers.celery_app worker
  --loglevel=info
  --max-tasks-per-child=1
```

### F2 — `CLIMATEBERT_MODEL` in CLAUDE.md env block but absent from config.py
**Issue:** CLAUDE.md's "Environment Variables" canonical block shows `CLIMATEBERT_MODEL=climatebert/distilroberta-base-climate-detector`. This variable does **not** appear in `config.py` and is never read via `settings.*` anywhere in `backend/app` (confirmed by grep). The classifier hardles the HuggingFace model ID as a constant. The CLAUDE.md session log 2026-05-18 explicitly notes: "`CLIMATEBERT_MODEL` absent from `.env` (non-blocking — classifier hardcodes the id)". **Not added** to `config.py` or `.env.example` — it is dead from the settings perspective. If the team wants it configurable, the classifier owner (M2) should add it.

### F3 — `settings.extraction_concurrency` is declared but not used
**File:** `backend/app/core/extraction/extractor.py`
**Issue:** `settings.extraction_concurrency` is referenced in the CLAUDE.md 2026-05-26 session note as "last unused". Grep confirms the field is set in `config.py` and appears in the `extractor.py` MLflow param logging (`"extraction_top_k": settings.extraction_top_k` in the MLflow params block), but `extraction_concurrency` itself is only logged — it does not gate any actual concurrency primitive (no `asyncio.Semaphore(settings.extraction_concurrency)` exists). **Kept in `config.py`** because the field is part of the publicly documented config surface and the concurrency wiring is M3-owned work. Flagged for M3 owner to wire.

### F4 — `embedding_model` legacy alias could diverge silently
**File:** `backend/app/config.py`
**Issue:** `embedding_model` defaults to `"intfloat/multilingual-e5-base"` — the same as `embedding_model_en` — but there is no runtime enforcement that keeps them in sync if both are set differently via env vars. A user setting `EMBEDDING_MODEL=bge-m3` but leaving `EMBEDDING_MODEL_EN=intfloat/multilingual-e5-base` would get inconsistent behaviour. The embedder reads `settings.embedding_model_en` / `settings.embedding_model_ar` exclusively (confirmed by grep: line 99 `backend/app/core/nlp/embedder.py`), so `EMBEDDING_MODEL` only affects callers that haven't migrated. **Not adding a sync validator** — it would change effective behaviour for any code path that still reads the legacy field. Flagged for M2 owner to either remove the legacy field or add a `@model_validator` that copies `embedding_model_en` into `embedding_model` after resolution.

### F5 — tasks.py module docstring describes 5-stage pipeline; actual implementation is 7 stages
**File:** `backend/app/workers/tasks.py` (frozen — Agent C cannot edit)
**Issue:** CLAUDE.md explicitly notes this: "workers/tasks.py's module docstring still describes the older 5-stage pipeline ... The actual implementation runs 7 stages". The docstring is the only stale artifact; the function body is correct. Flagged for M6 owner to update the docstring.

---

## 3. Recommended next priorities

1. **docker-compose `--max-tasks-per-child=1`** (F1) — One-line fix, high impact. Prevents the worker crash-on-large-Arabic-doc issue documented in two session log rows. Owner: M6 / DevOps.

2. **Wire `extraction_concurrency`** (F3) — `asyncio.Semaphore(settings.extraction_concurrency)` around the per-indicator LLM call loop in `extractor.py`. Currently all indicator calls are sequential; adding a semaphore would cut extraction time for 46 indicators from ~46× latency to ~⌈46/concurrency⌉× latency. Owner: M3.

3. **`embedding_model` legacy alias cleanup** (F4) — Once all callers are confirmed to use the `embedding_model_en` / `embedding_model_ar` path, remove `embedding_model` from `config.py` and `.env.example` (or add the sync validator). Owner: M2.

4. **tasks.py docstring** (F5) — Trivial, but misleading for new team members walking the pipeline. Owner: M6.

5. **CLIMATEBERT_MODEL configurability** (F2) — Low priority unless the team plans to swap the ClimateBERT checkpoint (e.g. for a fine-tuned version). Owner: M2.

---

## py_compile verification

Shell execution was not permitted in this session. The three Python files were reviewed manually for:
- All imports present and correctly spelled (`from pydantic import Field, field_validator, model_validator` — both used; `from pydantic_settings import BaseSettings, SettingsConfigDict` — both used)
- All class/function/decorator nesting correct (no unclosed parens, all `@classmethod` / `@field_validator` pairs properly stacked)
- All string literals closed
- No f-string syntax errors
- `from __future__ import annotations` present in all three files

The files are structurally identical to the originals except for the additions described above. The user should run `python -m py_compile backend/app/config.py backend/app/database.py backend/app/workers/celery_app.py` to confirm before merging.
