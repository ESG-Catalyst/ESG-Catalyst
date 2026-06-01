# Error Handling Refactor — Agent D

## 1. What changed and why

### `backend/app/core/exceptions.py` (NEW FILE)

**Why:** The codebase had no shared exception hierarchy. Stage failures were
raised as bare `Exception` or `ValueError`, making it impossible for callers
to distinguish a billing failure from a file-parse failure from a scoring
failure without string-matching on the error message. This introduced
`ESGCatalystError` as a base and four stage-specific subclasses.

**What:**
| Class | Parent | Stage |
|---|---|---|
| `ESGCatalystError` | `Exception` | base — catch all pipeline errors |
| `IngestionError` | `ESGCatalystError` | M1 — file parsing / OCR |
| `ExtractionError` | `ESGCatalystError` | M3 — LLM extraction |
| `LLMUnavailableError` | `ExtractionError` | both primary + fallback failed |
| `ScoringError` | `ESGCatalystError` | M4 — scorer / gap-analysis |
| `ReportError` | `ESGCatalystError` | M5 — builder / narrative / renderer |

Pure class definitions only — no torch, no DB, no heavy imports.

---

### `backend/app/core/llm/router.py`

**Lines changed:** import block (added `LLMUnavailableError`), the
`ainvoke_with_fallback` method body.

**What (behavior-preserving):**

1. **Credit-error trigger conditions unchanged.** `_is_credit_error()` is not
   touched. The same HTTP 402, HTTP 429, and `_CREDIT_ERROR_MARKERS` strings
   still trigger fallback activation.

2. **Log message unchanged.** The structlog `warning` event
   `model_router.fallback_activated` with
   `message="Primary model unavailable, using free fallback"` is identical to
   the previous code (line 154 in the new file).

3. **No-fallback path.** Previously `raise` re-raised the original credit
   error as a raw exception. Now it raises `LLMUnavailableError(...) from
   primary_exc`, which is an `ExtractionError` (and thus an
   `ESGCatalystError`). The original exception is chained via `__cause__`, so
   `str(exc)` still shows the root error. This is the one narrowly-allowed
   behavioral nuance per the mission brief.

4. **Fallback-also-fails path (new).** The previous code had no explicit
   `try/except` around `fallback.ainvoke(...)` — a fallback failure would
   bubble up as a raw LangChain / httpx exception. Now it is caught, logged
   with both primary and fallback error details, and re-raised as
   `LLMUnavailableError` with the fallback exception as `__cause__`. This
   fulfills the "if both fail, RAISE — never silently return empty" contract.

---

### `backend/app/workers/tasks.py`

**Lines changed:** module docstring, import block, `run_extraction_pipeline`
except clauses, `generate_report_task` except clauses.

**Docstring fix (lines 1–29):**
The old docstring described a 5-stage pipeline (`ingestion → chunker →
classifier → extractor → scorer`). The real flow has been 7 stages since the
2026-05-26 retrieval port. Updated to enumerate all 7 stages and called out
that `report.generate` is a *separate* Celery task.

**Import block:** Added all six new exception types from
`app.core.exceptions`. The `ExtractionError`, `IngestionError`,
`ScoringError`, `ReportError` imports are present for narrowed catching in
future — only `ESGCatalystError`, `LLMUnavailableError`, and `ReportError`
are actually caught in this file today.

**`run_extraction_pipeline` except chain (after `NoTextExtractedError`):**

| New clause | Behavior |
|---|---|
| `except LLMUnavailableError` | Logs `pipeline.llm_unavailable`, marks doc failed, re-raises WITHOUT retry — billing issues don't clear on retry |
| `except ESGCatalystError` | Logs `pipeline.stage_error` with `exc_type`, marks doc failed, retries up to `max_retries` (transient infra) |
| `except Exception` | Unchanged logic — now adds `exc_type` to the structlog call for better observability |

**`generate_report_task` except chain:**

| New clause | Behavior |
|---|---|
| `except LLMUnavailableError` | Logs `report.generate.llm_unavailable`, marks report failed, re-raises WITHOUT retry |
| `except (ReportError, ESGCatalystError)` | Logs `report.generate.stage_error` with `exc_type`, marks report failed, retries |
| `except Exception` | Unchanged logic + `exc_type` added to log |

All DB status strings (`DocumentStatus.failed`, `ReportStatus.draft`),
`error_message` text, and stage strings (`"INGESTING"`, etc.) are **unchanged**.
The `NullPool` reliance, `send_task` contract, and structlog usage are
**unchanged**.

---

## 2. FastAPI exception handler wire-up snippet (for `main.py`)

Add the following block after `app = FastAPI(...)` in
`backend/app/main.py`. This is ready to apply as-is during reconciliation.

```python
# ── Shared exception handlers ─────────────────────────────────────────────
from fastapi import Request
from fastapi.responses import JSONResponse
from app.core.exceptions import (
    ESGCatalystError,
    LLMUnavailableError,
    IngestionError,
    ExtractionError,
    ScoringError,
    ReportError,
)


@app.exception_handler(LLMUnavailableError)
async def llm_unavailable_handler(request: Request, exc: LLMUnavailableError) -> JSONResponse:
    """Both primary and fallback LLM are unavailable (billing / quota).

    HTTP 503 Service Unavailable — the client should retry later or an
    operator needs to top up credits.
    """
    return JSONResponse(
        status_code=503,
        content={"detail": "LLM service is temporarily unavailable. Please try again later."},
    )


@app.exception_handler(IngestionError)
async def ingestion_error_handler(request: Request, exc: IngestionError) -> JSONResponse:
    """File could not be parsed — bad input, not a server fault."""
    return JSONResponse(
        status_code=422,
        content={"detail": f"Document ingestion failed: {exc}"},
    )


@app.exception_handler(ExtractionError)
async def extraction_error_handler(request: Request, exc: ExtractionError) -> JSONResponse:
    """Metric extraction failed (LLM returned garbage or ChromaDB unreachable)."""
    return JSONResponse(
        status_code=422,
        content={"detail": f"Metric extraction failed: {exc}"},
    )


@app.exception_handler(ScoringError)
async def scoring_error_handler(request: Request, exc: ScoringError) -> JSONResponse:
    """Scoring / gap-analysis failed."""
    return JSONResponse(
        status_code=422,
        content={"detail": f"ESG scoring failed: {exc}"},
    )


@app.exception_handler(ReportError)
async def report_error_handler(request: Request, exc: ReportError) -> JSONResponse:
    """Report builder / renderer failed."""
    return JSONResponse(
        status_code=500,
        content={"detail": f"Report generation failed: {exc}"},
    )


@app.exception_handler(ESGCatalystError)
async def esg_catalyst_error_handler(request: Request, exc: ESGCatalystError) -> JSONResponse:
    """Catch-all for any unhandled pipeline-level error."""
    return JSONResponse(
        status_code=500,
        content={"detail": f"Pipeline error: {exc}"},
    )
```

> **Ordering matters.** FastAPI checks handlers from most-specific to least.
> Because `LLMUnavailableError` is a subclass of `ExtractionError` which is a
> subclass of `ESGCatalystError`, list `LLMUnavailableError` first (as shown).
> FastAPI resolves by exact type match — it does NOT walk the MRO — but
> registering from most-specific to least is the conventional safe ordering.

---

## 3. Flagged for reconciliation (not fixed — outside my files)

| Item | Location | Detail |
|---|---|---|
| `MODEL_REPORT_FALLBACK` not configured | `core/llm/router.py` + `.env.example` | `report.generate` narrative calls use `model_router.ainvoke_with_fallback("report", …)` but `MODEL_REPORT_FALLBACK` is absent from `.env.example`. Add `MODEL_REPORT_FALLBACK=openrouter/mistralai/mistral-7b-instruct:free` (or any free model). Config owner: M6. |
| `--max-tasks-per-child=1` not added | `docker-compose.yml` | Celery worker process dies after classifying large Arabic PDFs (~2000 chunks, ~70 min CPU). Flagged in session log 2026-05-18 (E2E). Fix is one compose line. Owner: M6. |
| `M4 gap_analysis` depth | `core/scoring/gap_analysis.py` | Returns 0 gaps despite missing indicators in some runs. Flagged repeatedly in session log. Owner: M4. |
| `score_metric` (v2 scoring path) unwired | `core/scoring/scorer.py:237` | Exists but is never called by the pipeline. v2 backlog item. Owner: M4. |
| `NoTextExtractedError` should extend `IngestionError` | `workers/tasks.py:64` | Currently extends bare `Exception`. Should extend `IngestionError` (from `core/exceptions`) for consistency. Changing it is a one-line edit in my file but was noted post-write — keeping `NoTextExtractedError` as a local signal class is defensible since it's caught before `ESGCatalystError`. Low priority. |

---

## 4. Recommended next priorities

1. **Wire `MODEL_REPORT_FALLBACK`** — the narrative LLM call in
   `_generate_report_async` will raise `LLMUnavailableError` correctly now,
   but there is no fallback configured for the `"report"` task, so every
   OpenRouter credit-exhausted run will hit the no-fallback path immediately.
   One `.env.example` + config line.

2. **Register exception handlers in `main.py`** — use the snippet in section 2
   above. Without it, `LLMUnavailableError` surfaces as an unhandled 500 to
   clients instead of a clean 503.

3. **Add `--max-tasks-per-child=1` to docker-compose** — prevents the known
   Celery worker-process death on large Arabic documents.

4. **Incrementally adopt `IngestionError` / `ScoringError` / `ReportError`**
   in `parser.py`, `scorer.py`, and `renderer.py` — each module owner wraps
   their top-level functions with `raise <StageError>(...) from exc` so that
   stack traces flow through the hierarchy to the tasks.py handlers.
