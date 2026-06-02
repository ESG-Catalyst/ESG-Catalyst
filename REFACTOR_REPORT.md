# ESG Catalyst — Refactor Report

**Branch:** `test-opus` (6 commits over `main`; `main` untouched)
**Date:** 2026-06-01
**Method:** 5 parallel worktree-isolated subagents (pipeline / API / config / error-handling / tests),
cross-checked and reconciled centrally, verified with the full test suite + an app-import smoke,
then code-reviewed.

> Scope rule honored throughout: **refactor only** — no public API or behavior changes except
> where explicitly called out below. `models/` and `schemas/` (the `ExtractedMetric` contract)
> were **frozen** and never touched. No `core/agents/` created. Roadmapped items were flagged,
> not "fixed."

---

## 1. Outcome at a glance

| Signal | Before | After |
|---|---|---|
| `pytest` | `testpaths` pointed at a non-existent dir → **0 collected**; `gri_indicators.json` load **crashes on Windows** | **498 passed, 0 failed** (`tests/`) |
| `import app.main` | n/a | OK — 24 routes, 9 exception handlers |
| Shared exception hierarchy | none (bare `Exception` / `ValueError`) | `core/exceptions.py` (`ESGCatalystError` + 5 subclasses) |
| Unit tests | 1 real test file (`test_scoring.py`) + 3 stray scripts | +5 files, **~406 new tests** |
| `.env.example` ↔ `config.py` | 10 settings missing from example | synced |
| Cross-platform JSON reads | 4 `open()` calls without `encoding="utf-8"` | all fixed |
| API error leakage | unexpected errors → 422 leaking `str(exc)` | generic **500**, no leak (HTTPException re-raised first) |

Net diff: **38 files, +3785 / −524.**

---

## 2. What changed, by area

### A · Pipeline core (`core/{ingestion,nlp,extraction,scoring,reporting,gri,tracking}`) — 12 files
Conservative, behavior-preserving cleanup (the brief's bias, given thin tests):
- Import hygiene (moved mid-module `import re` / `import math` / `import datetime` to the top; removed dead `import math`).
- `AssertionError` → `ValueError` in `scorer.score_q_plus_ql / score_pillar / score_composite` (runtime contract violations should not be `AssertionError`, which is stripped under `python -O`).
- Narrowed silent `except Exception` paths in `table_extractor.py` / `mlflow_tracker.py` and added `logger.warning` where errors were swallowed.
- Google-style docstrings + type hints across reporting/scoring helpers.
- **Did not** split `scorer.py` (969 LOC) / `extractor.py` (633 LOC) — proposed instead (see §6) to avoid unverifiable churn.

### B · API (`api/**`, `main.py`) — 8 files + new `api/deps.py`
- New `deps.py`: `require_company()` + `require_owned_record()` collapse **7 copies** of the company-scope guard and **4 copies** of the fetch-then-scope pattern. Cross-tenant access still returns **404** (no existence leak).
- Every router now does `except HTTPException: raise` **before** `except Exception → 500` — unexpected errors return a generic 500 (no `str(exc)` leak) **without** masking intentional 404/400/422. *(Verified across all 6 routers.)*
- structlog throughout; all handlers `async`.
- `main.py` left a `# RECONCILE` hook for the exception-handler seam (wired during reconciliation, see §3).

### C · Config (`config.py`, `database.py`, `celery_app.py`, `.env.example`)
- `config.py`: every field → `Field(default=…, description=…)`; added `@field_validator`s for `environment`, `pdf_backend`, `confidence_threshold`, and the extraction int knobs (fail at startup, not first use). No field renames.
- `database.py`: **NullPool preserved** (the Celery solo-pool asyncio fix) and documented with a "do not revert" banner.
- `.env.example`: added the 10 settings that existed in `config.py` but were missing from the example (`CHUNK_*`, `EXTRACTION_*`, `MODEL_REPORT_FALLBACK`).

### D · Error handling (`core/exceptions.py` NEW, `llm/router.py`, `workers/tasks.py`)
- `core/exceptions.py`: `ESGCatalystError` base + `IngestionError` / `ExtractionError` / `LLMUnavailableError(ExtractionError)` / `ScoringError` / `ReportError`. Pure definitions, no heavy imports (keeps the API image slim).
- `router.py`: credit-error trigger + the exact `"Primary model unavailable, using free fallback"` log are **unchanged**; the fallback call is now wrapped so that **both-fail raises `LLMUnavailableError`** (was an unguarded raw raise). *(Verified behavior-preserving.)*
- `tasks.py`: fixed the **stale 5-stage docstring → accurate 7 stages**; typed except-chains (`LLMUnavailableError` no-retry → `ESGCatalystError` retry → `Exception` retry), correctly ordered most-specific-first. Status strings / `error_message` / NullPool / `send_task` contract unchanged.

### E · Tests (`tests/**`) — 5 new files, ~406 tests
`test_validator.py`, `test_confidence.py`, `test_indicators.py`, `test_v1_scorer.py`, `test_builder.py` —
fast, dependency-light (no torch / network / DB), targeting stable public APIs: monetary/currency
parsing, confidence adjustment, the 46-indicator catalog, the v1 disclosure-quality tiers +
confidence-factor bands + composite weights + unknown-sector fallback, and report-section building.

---

## 3. Reconciliation (central, post-merge) — bugs found by the workflow and fixed

These were surfaced by the test suite + Windows verification and fixed during reconciliation (commit `ac1d525`):

1. **UTF-8 JSON reads (4 sites)** — `gri/indicators.py`, `scoring/gri_scorer.py`, `scoring/materiality.py`, `scoring/sasb_scorer.py` opened JSON without `encoding="utf-8"`. On a Windows host this **crashes** (`UnicodeDecodeError`, cp1252) on the Arabic/em-dash bytes. On the critical path (extractor/scorer/gap-analysis all load the catalog). Now consistent with `parser.py`. **High-value cross-platform fix.**
2. **`pyproject.toml` `testpaths`** — pointed at non-existent `backend/tests` → default `pytest` collected nothing. Fixed to `tests`.
3. **Exception-handler seam** — wired D's handlers into `main.py` (LLMUnavailable→503, Ingestion/Extraction/Scoring→422, Report→500, base→500), importing the pure `core.exceptions` (no image bloat).
4. **Test precision** — `test_validator.py` asserted the exact gallon factor `0.003785`; `normalize_water` rounds to 4 dp (`0.0038`). Corrected the expectation (no code bug — the factor is precise).

---

## 4. Code review (after) — findings

Reviewed the full `main...test-opus` diff (correctness + removed-behavior + cross-file + language
pitfalls + cleanup). Most candidates **refuted** (router behavior preserved; HTTPException re-raised
before the generic 500 in every router; config validators load cleanly; except-chain ordering correct).
Surviving findings, most-severe first:

```json
[
  {
    "file": "backend/app/core/extraction/extractor.py",
    "line": 333,
    "summary": "Per-indicator `except Exception` swallows LLMUnavailableError, so D's new task-level handler is inert for the main credit-exhaustion case.",
    "failure_scenario": "OpenRouter credits exhausted AND fallback fails -> router raises LLMUnavailableError inside _extract_single -> caught at extractor.py:333 -> logged as indicator_failed + a _missing_metric appended -> loop continues for all 46 indicators -> extraction 'completes' with 0 metrics and the document is marked complete (not failed). run_extraction_pipeline's new `except LLMUnavailableError` never fires."
  },
  {
    "file": "backend/app/api/deps.py",
    "line": 60,
    "summary": "require_company() raises 403 when current_user.company_id is None — a new response code for the 'user has no company' case.",
    "failure_scenario": "A consultant account with company_id=None hitting a per-company list/detail route now gets 403 instead of the prior route-specific behavior (empty list / 404). Low impact, but it's a contract nuance worth confirming against the React client's handling."
  }
]
```

**Deliberate contract changes (not defects — flagged for team sign-off):**
- Unexpected errors on `documents/pipeline/metrics/reports/scoring/auth` and `auth/login|register` now return **500 generic** instead of **422 + `str(exc)`**. More correct + no leak, but it's an API-contract shift.
- Malformed `user_id` UUID in `PATCH /admin/users/{id}/role` now → **422** instead of an unhandled 500.

---

## 5. Bugs found but NOT fixed (out of scope — owner / frozen-schema / roadmap)

| Item | Location | Why deferred |
|---|---|---|
| `gap_analysis` keys on `materiality_score` (field is `materiality_weights`) → **every gap silently scores `priority="medium"`** | `core/scoring/gap_analysis.py` | M4-owned logic bug; real, found by Agent A. Recommend M4 fix next. |
| `compute_tcfd_score` references `m.tcfd_pillar` (absent from the frozen schema) → always falls through to keyword path | `core/scoring/*tcfd*` | Frozen schema — needs team discussion. |
| `LLMUnavailableError` swallowed by extractor (see §4 #1) | `core/extraction/extractor.py:333` | Making it effective = let it propagate (whole-run failure, not per-indicator). M3 + M6. |
| `datetime.utcnow()` deprecation | `core/scoring/fra_compliance.py:269` | Pre-existing; modernize to `datetime.now(UTC)`. |
| `--max-tasks-per-child=1` (worker recycle) | `docker-compose.yml` | Runtime flag, not code; carried over from prior sessions. |
| 3 stray test scripts not pytest-collectible | `backend/test_*.py`, `data/ingestion_test_files/test_ingestion.py` | `asyncio.run(main())` scripts — move to `scripts/`. |
| `extraction_concurrency` declared + logged but unwired; `CLIMATEBERT_MODEL` dead-as-a-setting | `config.py` | Flagged by Agent C. |

---

## 6. Recommended next priorities

1. **Make the resilience refactor effective end-to-end** — let `LLMUnavailableError` propagate out of `extract_metrics` (it's a whole-run failure) so a credit-exhausted run marks the document **failed** with a clear reason instead of silently producing 0 metrics. *(Highest leverage; it's why the error hierarchy exists.)*
2. **Fix `gap_analysis` `materiality_score` → `materiality_weights`** — one-line correctness fix that restores real gap prioritization (M4).
3. **Confirm `_build_models_dict` maps the `report` fallback** so `MODEL_REPORT_FALLBACK` actually reaches `model_fallbacks["report"]` (now that the field + `.env.example` exist).
4. **Decompose `scorer.py` (969) / `extractor.py` (633)** behind the now-stable public APIs, with the new tests as a safety net.
5. **Consolidate triplicated helpers** — `_MT_MAP` (extractor/gri_scorer/sasb_scorer) and the Arabic BiDi helpers (pdf/docx/table parsers) into shared modules.
6. **Team sign-off on the 422→500 contract change** + move the stray test scripts.

---

## 7. Verification evidence
- `pytest tests/ -q` → **498 passed, 0 failed** (2 warnings: the `utcnow()` deprecation above).
- `PYTHONPATH=backend python -c "import app.main"` → OK (24 routes, 9 exception handlers).
- `py_compile` clean on every changed file (per-area during fan-out + on the reconciled tree).

## 8. Commit map (on `test-opus`)
```
ac1d525  fix(reconcile): UTF-8 JSON reads on Windows; pytest testpaths; wire exception handlers; test precision
6ae1952  test: add ~406 unit tests
c4c1b68  refactor(errors): shared exception hierarchy; LLMUnavailableError in router; fix 7-stage docstring
8ededa5  refactor(config): typed settings + validators, document NullPool, sync .env.example
6f65f6d  refactor(api): shared deps module, uniform 500 errors, structlog
13036bb  refactor(pipeline): import hygiene, docstrings, narrow excepts, AssertionError->ValueError
```
Per-area detail: `REFACTOR_pipeline.md`, `REFACTOR_api.md`, `REFACTOR_config.md`, `REFACTOR_errorhandling.md`, `REFACTOR_tests.md`.
