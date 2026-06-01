# API Layer Refactor — Agent B

## 1. What Changed and Why

### New file: `backend/app/api/deps.py`
Extracted two repeated patterns (present 7+ times across the five routers) into
a single shared module:

| Helper | Purpose |
|---|---|
| `require_company(user)` | Returns `user.company_id` or raises HTTP 403. Replaced the verbatim `if current_user.company_id is None: raise HTTPException(403, ...)` guard in every handler. |
| `require_owned_record(db, model, id, user, ...)` | Fetches any ORM record by PK, then checks `company_id` match. Returns 404 for both "missing" and "wrong tenant" (existence leak protection). Replaced the four distinct fetch-and-scope blocks in `documents.py`, `pipeline.py` (partial), `reports.py`, and `metrics.py`. |
| Re-export `get_current_user` | Routers can now `from app.api.deps import get_current_user` without a dependency on the auth module directly. |

### `backend/app/api/documents.py`
- Replaced inline `_require_company` helper with `require_company` from `deps`.
- Replaced manual fetch + scope check in `get_document` with `require_owned_record`.
- Moved `select` import to module level (was inline inside `list_documents`).
- `except Exception` → HTTP 500 with a generic message (was 422 leaking `str(exc)`).
- Added `structlog` logging on upload success and unexpected errors.

### `backend/app/api/pipeline.py`
- Replaced inline `company_id is None` guard with `require_company`.
- `except Exception` → HTTP 500 (was 422 leaking `str(exc)`).
- Added structlog logging on successful enqueue and unexpected errors.
- Minor: cleaned up `_STATE_MAP` dict alignment for readability.

### `backend/app/api/metrics.py`
- Replaced inline `company_id is None` guard with `require_company`.
- Moved `reviewer_id` assignment before mutating other fields (more coherent ordering).
- `except Exception` → HTTP 500 (was 422 leaking raw exception text).
- Added structlog logging.

### `backend/app/api/reports.py`
- Fixed a missing blank line between `list_reports` and `generate_report` (caused confusing visual merge of two handlers in the original).
- Replaced all `company_id is None` guards with `require_company`.
- Replaced manual fetch + scope check in `generate_report`, `get_report`, and `download_report_pdf` with `require_owned_record`.
- `except Exception` → HTTP 500 (was 422 leaking raw exception text).
- Added structlog logging on task enqueue, missing PDF on disk (warns), and unexpected errors.

### `backend/app/api/auth.py`
- Added `structlog` logging on register, login, and admin role update.
- Fixed the `update_user_role` handler: the `uuid.UUID(user_id)` conversion was
  bare (would raise a 500 on invalid input); now catches `ValueError`/`TypeError`
  and returns HTTP 422 with a clear message.
- `except Exception` → HTTP 500 on register/login (was 422 leaking raw exception text).
- Minor: whitespace and docstring pass; `full_name` field noted as always `""` (no ORM column — pre-existing gap, flagged below).

### `backend/app/api/scoring.py`
- Extracted `_validate_sector(sector)` helper to DRY the two identical sector
  validation blocks.
- `except Exception` → HTTP 500 with generic messages (was already 500 in the
  original, but the detail leaked `str(exc)`).
- Added structlog logging.
- Added the `# FLAGGED FOR RECONCILIATION` comment block at the top of the module
  docstring — see section 2.

### `backend/app/main.py`
- Added `structlog` logging on startup and shutdown.
- Added grouped comment sections around router registration (auth / pipeline / scoring).
- Added type annotation `-> dict` to the `health` handler.
- Added the `# RECONCILE: register core.exceptions handlers here` hook block with
  the exact import pattern Agent C should implement.

---

## 2. Flagged — Not Fixed (Cross-area Seams / Bugs)

### CRITICAL: `scoring.py` imports `app.core.scoring.*` directly
**File:** `backend/app/api/scoring.py`, lines 35–44

The scoring module imports from `app.core.scoring` directly in a route handler,
which violates the load-bearing invariant that **route modules must never import
core pipeline modules** (so the API container stays slim and doesn't pull in
`torch` / `transformers` / `MLflow`).

The scoring engine is relatively lightweight compared to the NLP pipeline, but
the principle applies. The correct fix is:

1. Add a `scoring.score_document` Celery task in `workers/tasks.py` (M6-owned)
   that wraps the M4 scorer.
2. Change `scoring.py` to call `celery_app.send_task("scoring.score_document", ...)`.

This is an M4 + M6 cross-area change. A `# FLAGGED` comment has been added to
the module docstring in `scoring.py`.

### `UserRecord.full_name` is always `""`
**File:** `backend/app/api/auth.py`, `list_users` and `update_user_role`

The `User` ORM model has no `full_name` column (field present in `RegisterRequest`
but never persisted). The admin response always returns `full_name: ""`.
Fix requires an ORM migration (models/user.py — frozen for this agent).

### Pipeline status endpoint not scoped by company
**File:** `backend/app/api/pipeline.py`, `get_pipeline_status`

`GET /pipeline/status/{job_id}` only checks that the caller is authenticated; it
does not verify that the `job_id` belongs to the caller's company. The original
code had the same gap, with a comment acknowledging it. A motivated attacker
who guesses a UUID4 can poll another tenant's job progress.

Full fix requires storing `job_id → company_id` in Postgres (or Redis) when
`run_pipeline` enqueues the task, then checking it here. Out of scope for this
pass (M6 work).

### `RECONCILE` hook in `main.py`
**File:** `backend/app/main.py`, lines 38–50

A clearly-marked comment block marks where Agent C's `core.exceptions` global
exception handler registration should land. Until that module exists, the
per-handler `except Exception → 500` pattern in each router is the fallback.

---

## 3. Recommended Next Priorities

1. **Wire Agent C's exception handlers** into `main.py` at the `# RECONCILE`
   hook once `app.core.exceptions` is available. This will unify error
   serialisation across all routers and allow removal of the per-handler
   `except Exception` blocks.

2. **Move `scoring.py` core imports to a Celery task** (M4 + M6 joint work).
   Create `workers/tasks.py:score_document_task`; change `scoring.py` to
   `celery_app.send_task(...)`. This keeps the API container slim.

3. **Persist `job_id → company_id`** on pipeline enqueue so
   `GET /pipeline/status/{job_id}` can be fully company-scoped.

4. **Add `full_name` column to `User`** and wire `RegisterRequest.full_name`
   through to the ORM (M6/schema team). Until then the admin table always
   shows empty names.

5. **Token refresh / revocation** (Iteration 2) — currently tokens are valid
   until expiry with no server-side revocation path.

---

## 4. py_compile Verification

Shell execution was denied in this worktree session. All files were verified by
careful static analysis (read-back after each write, cross-checked imports, type
annotations, and exception handling paths). The specific changes verified:

- `deps.py`: all imports resolvable; TypeVar + generic `_ORM` used correctly; no
  bare `return` in async function.
- `documents.py`: `select` moved to module-level import; all three handlers
  follow `try / except HTTPException: raise / except Exception → 500` pattern.
- `pipeline.py`: `Optional[Report]` typed correctly; `_STATE_MAP` types correct.
- `metrics.py`: `_ALLOWED_REVIEW_STATUSES` set constant correct; join query
  unchanged from original.
- `reports.py`: `list[ReportResponse]` return type; blank line between handlers
  restored; `require_owned_record` called correctly.
- `auth.py`: `UUID(user_id)` ValueError/TypeError caught before the DB query;
  `Optional[User]` annotation on `user` in `login`; `List[UserRecord]` uses
  `typing.List` for Python 3.9 compat (pre-existing style).
- `scoring.py`: `_validate_sector` helper factored out correctly; all original
  logic preserved.
- `main.py`: all router imports unchanged; hook comment well-formed Python comment.

**The user should run `python -m py_compile` on each file once shell access is
available to confirm no import-time errors.**
