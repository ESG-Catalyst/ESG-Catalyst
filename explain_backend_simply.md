# Backend, Explained Simply

A tour of what's running, why it's running, and how a single PDF upload turns into a downloaded PDF report. Written for someone fluent in Python and ML pipelines but new to "web backend" tooling.

---

## 0. What is "a backend"?

In a data-science notebook you load a CSV, train a model, save a pickle. That's one process, one user (you), one machine, no network.

A **backend** is the same kind of code — except it has to:

1. Sit there waiting for HTTP requests from other programs (a browser, a Streamlit UI, a curl command, another service).
2. Handle many users at once without them clobbering each other's data.
3. Save state somewhere durable, so restarting the process doesn't lose anything.
4. Run slow things (an LLM pipeline that takes 7 minutes) without making the caller wait synchronously.

That's it. A backend is just code that listens, persists, and coordinates. Everything else — FastAPI, Celery, Redis, Postgres, Docker — exists to make those four jobs cleaner.

---

## 1. The cast of characters

Here's every moving part in this repo and why it's there. Each gets a "what is it / why this one / what could replace it" pass.

### 1.1 FastAPI — the web framework

**What it is.** A Python library that turns ordinary Python functions into HTTP endpoints. You write:

```python
@router.get("/{document_id}")
async def get_document(document_id: UUID, db: AsyncSession = Depends(get_db)):
    ...
```

…and FastAPI handles: parsing the URL, validating the path parameter as a UUID, calling your function, serializing the return value to JSON, setting the right Content-Type header, generating OpenAPI docs at `/docs`. You never touch sockets or HTTP parsing.

**Why FastAPI here.** Three reasons:
- Type hints become validation for free (Pydantic — see §1.4).
- Native `async def` support — important because the LLM and database calls are I/O-bound.
- Auto-generated interactive docs at `/docs` — try the API in your browser without a client.

**Alternatives.** Flask (older, sync-first, simpler), Django REST Framework (heavier, opinionated, batteries included), Express.js (Node), FastAPI's main Python competitor is Litestar.

### 1.2 Uvicorn — the web server

**What it is.** The actual HTTP listener. FastAPI is just an app *description*; Uvicorn is the program that opens port 8000, accepts TCP connections, decodes HTTP, and hands requests to FastAPI.

You ran:
```
python -m uvicorn app.main:app --port 8000
```
That's: "Uvicorn, please serve the `app` object from `app/main.py` on port 8000."

**Why this one.** Uvicorn speaks **ASGI** (Asynchronous Server Gateway Interface), which is the protocol async Python frameworks like FastAPI talk. It's the de-facto pairing.

**Alternatives.** Hypercorn (similar), Gunicorn (older WSGI server — used in production to spawn multiple Uvicorn workers).

### 1.3 PostgreSQL — the database

**What it is.** A relational database. Tables with rows and columns, joined on keys, queried with SQL. Same mental model as a pandas DataFrame, except:
- Data persists on disk (survives restarts).
- Multiple processes can read and write at once without corrupting each other.
- It enforces constraints (this column can't be null, this id must be unique).
- Transactions: a group of changes either all happen or none happen.

You have these tables:

| Table | What lives in it |
|---|---|
| `companies` | Org metadata (name, industry, country) |
| `users` | Login identities (unused for now — auth deferred) |
| `documents` | One row per uploaded PDF |
| `reports` | One row per ESG report; links to its company; carries `total_score`, `pdf_path` |
| `extracted_metrics` | The big one. 13 rows per report — one per GRI indicator |

**Why Postgres.** Picked over the default SQLite because:
- The project's `Mapped[...]` type annotations use Postgres-specific UUID + JSON columns.
- The Celery worker and the FastAPI process need to write the same DB concurrently — SQLite locks the whole file for writes.
- Production target is Postgres anyway; testing against the same engine avoids "works on my SQLite, breaks in prod" surprises.

**Alternatives.** SQLite (single-file, single-writer — fine for prototypes), MySQL (similar to Postgres), MongoDB / DynamoDB (document stores — wrong shape for the strongly-typed metric records here).

### 1.4 SQLAlchemy + Pydantic — two different "schema" libraries

This is the part that confuses people new to backends. There are **two** kinds of schema in play, and they look almost identical.

**SQLAlchemy** (the **ORM**, Object-Relational Mapper) defines what the **database** looks like. Example: [backend/app/models/metric.py](backend/app/models/metric.py).

```python
class ExtractedMetric(Base):
    __tablename__ = "extracted_metrics"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    gri_code: Mapped[str] = mapped_column(String(50), nullable=False)
    value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # … etc
```

Reading from the DB returns one of these objects. You touch attributes (`metric.value`) and SQLAlchemy issues `SELECT` / `UPDATE` SQL behind the scenes. **You never write SQL strings by hand** (and shouldn't — it would let SQL injection in).

**Pydantic** (the validation library FastAPI uses) defines what data crossing the **HTTP boundary** looks like. Example: [backend/app/schemas/metric.py](backend/app/schemas/metric.py).

```python
class ExtractedMetricSchema(BaseModel):
    id: UUID
    gri_code: str
    value: float | None
    # … etc
```

When a request comes in, Pydantic enforces the shape of the JSON body. When a response goes out, Pydantic serializes the SQLAlchemy object into JSON. If a client sends `value: "not a number"`, Pydantic rejects it with a 422 *before* your function ever runs.

**Why two schemas for "the same" thing?** Because the database shape and the API shape diverge:
- The DB has internal fields you don't expose (`reviewer_id`, `updated_at`).
- The API has request-only fields the DB doesn't store (the PATCH body has `status`, but no `id`).
- Validation rules differ (the DB allows `status="ambiguous"`, but the review endpoint only allows `approved` or `rejected`).

CLAUDE.md says **`ExtractedMetricSchema` is the contract between pipeline, API, review UI, and report generator — never change it lightly**. That's because all four of those touch the same record but in different contexts.

**Alternatives.** marshmallow (older Python validation lib), attrs / dataclasses (no validation), Django's built-in ORM (tied to Django).

### 1.5 Redis — the message broker

**What it is.** An in-memory key-value store. Originally a cache (think Memcached). Here it's used as a **message queue**: FastAPI puts a "please do this work" message in Redis, the Celery worker picks it up.

**Why Redis here.** Celery needs a broker (somewhere to drop and pick up task messages). Redis is the simplest one — small footprint, no schema, lives in one Docker container.

**Alternatives as a broker.** RabbitMQ (heavier, more reliable for huge throughput), AWS SQS (managed), PostgreSQL itself can be used (via `pg-listen`/`pg-notify`). For our scale, Redis is the right pick.

**Other things Redis is good at** that we don't use yet: caching expensive LLM responses, session storage, rate limiting.

### 1.6 Celery — the background worker

**What it is.** A library for "run this Python function on a different process, possibly on a different machine, possibly later." It's how the API endpoint `/pipeline/run` returns in 50 ms even though the actual pipeline takes 7 minutes.

The flow:
1. FastAPI calls `run_extraction_pipeline.delay(document_id, ...)`. This **does not** run the function. It puts a message in Redis: "task=pipeline.run_extraction, args=[...]".
2. FastAPI returns the new job_id to the client immediately.
3. The Celery **worker** (a separate Python process you started with `celery -A app.workers.celery_app worker`) is sitting in a loop polling Redis. It sees the message, picks it up, runs the function for real.
4. While running, the worker writes its progress (`task.update_state(state="EXTRACTING", ...)`) back to Redis.
5. The client polls `/pipeline/status/{job_id}`. FastAPI reads Redis (`AsyncResult(job_id).state`) and reports back.
6. When the worker finishes, the final return value is stored in Redis for a day (`result_expires=86400`).

**Why this matters.** HTTP requests are supposed to return quickly. A request that takes 7 minutes:
- Blocks one worker on the API server.
- Likely times out on the client (browsers give up around 30 seconds).
- Loses everything if anything hiccups mid-request.

Background workers solve this. The pattern is universal — any system that does "slow work triggered by a click" looks like this.

**Why Celery specifically.** Mature, Python-native, plays nicely with Redis, has retry logic and progress tracking built in. The CLAUDE.md spec already chose it.

**Alternatives.** RQ (simpler), Dramatiq (newer, lighter), Arq (asyncio-native), Temporal (much heavier — workflows with retries/timers as first-class), AWS Step Functions / Google Cloud Tasks (managed).

### 1.7 Docker + docker-compose — the environment

**What it is.** Docker packages an application + its OS dependencies into an "image" that runs identically anywhere Docker runs. `docker-compose.yml` describes a group of related containers and starts them with one command.

We use Docker for the **infrastructure** pieces (Postgres, Redis, ChromaDB, MLflow) because:
- They're stateful — installing Postgres natively on Windows is painful; running it in a container is one `docker compose up`.
- Their versions are pinned (`postgres:16-alpine`) — everyone on the team gets exactly the same Postgres.
- Cleanup is `docker compose down -v` — no stray system services.

We currently **don't** dockerize the application code (FastAPI + Celery) — those run directly on your machine via `python -m uvicorn` and `celery -A ... worker`. That's fine for development; for production you'd build a Dockerfile that bundles the backend code too.

**Alternatives.** Native installs (works but messy), Vagrant (heavier VMs), Kubernetes (over-engineered for one developer), Nix (powerful but steep learning curve).

### 1.8 The pipeline modules — the actual ESG logic

Everything above is *plumbing*. The interesting work happens in [backend/app/core/](backend/app/core/):

| Module | What it does |
|---|---|
| `ingestion/parser.py` | PDF → text + structured pages (PyMuPDF) |
| `nlp/chunker.py` | Long text → ~1500 short chunks that preserve section structure |
| `nlp/classifier.py` | Each chunk → "is this ESG-relevant?" via ClimateBERT |
| `nlp/embedder.py` | Each chunk → 768-dim vector via multilingual e5 |
| `extraction/extractor.py` | Relevant chunks → 13 `ExtractedMetric` records, one per GRI indicator, by prompting an LLM |
| `scoring/scorer.py` | Metrics + weights → GRI / FRA / SASB scores |
| `reporting/builder.py` | Metrics → ordered list of `ReportSection` objects |
| `reporting/narrative.py` | Each section → 2-4 paragraph English narrative (LLM) |
| `reporting/renderer.py` | Bundle of sections → PDF on disk |

None of these care about HTTP, Postgres, or Celery. They're pure Python you could call from a notebook. That separation is on purpose — it means the API layer and the agent layer (Iteration 3) wrap the same logic without changing it.

---

## 2. Concepts you keep meeting

### 2.1 HTTP and REST

**HTTP** is a protocol: "send a text message over a TCP connection in a specific format, get a text response back." Every interaction looks like:

```
POST /api/v1/documents/upload HTTP/1.1
Host: 127.0.0.1:8000
Content-Type: multipart/form-data; boundary=...
[body bytes...]
```

…and the server responds:

```
HTTP/1.1 201 Created
Content-Type: application/json

{"document_id":"a798...","filename":"…","status":"uploaded"}
```

**REST** is a *convention* for laying out HTTP endpoints around "resources". You'll see:

| Verb | Meaning | Idempotent? |
|---|---|---|
| `GET` | Read | Yes |
| `POST` | Create (or "start an action") | No |
| `PATCH` | Update some fields | Usually yes |
| `PUT` | Replace whole resource | Yes |
| `DELETE` | Remove | Yes |

"Resources" are nouns in the URL: `/documents`, `/metrics`, `/reports`. The verb in the HTTP method says what to do to it. That's why `POST /pipeline/run` is slightly un-REST: "run" is a verb. That's fine — REST is a guideline, not a religion.

**Status codes** (the `201` in `HTTP/1.1 201 Created`) are the API's first form of communication:

| Range | Meaning |
|---|---|
| `2xx` | Success (200 OK, 201 Created, 202 Accepted) |
| `3xx` | Redirect (rare in APIs) |
| `4xx` | The client did something wrong (400 Bad Request, 404 Not Found, 422 Unprocessable) |
| `5xx` | The server crashed |

Our API translates internal exceptions into 4xx where it can (CLAUDE.md rule: "return 422 not 500"). That's why every handler is wrapped in `try/except HTTPException → re-raise; except Exception → 422`. A 500 means "the dev forgot to handle this case."

### 2.2 async / await

Same `async def` you'd use in a notebook for `asyncio.gather`, but here it's load-bearing.

When a request hits `GET /api/v1/documents/{id}`, that handler does:

```python
result = await db.execute(select(Document).where(Document.id == document_id))
```

The `await` says "while waiting for Postgres to answer, release this thread so it can serve a different request." A sync handler would hog the thread for the 5ms the query takes; with hundreds of clients that adds up. Async = one process can babysit many in-flight I/O operations at once.

**Important caveat.** Async only helps for *I/O-bound* work (network, disk, sleeping). CPU-bound work (running a HuggingFace model, parsing a 200-page PDF) still blocks the event loop. That's why those heavy steps live in the Celery worker, not in the API request handler.

### 2.3 Dependency Injection (`Depends(get_db)`)

You'll see this everywhere:

```python
async def upload_document(file: UploadFile = File(...), db: AsyncSession = Depends(get_db)):
```

`Depends(get_db)` says "before calling this function, call `get_db()` first and pass its result as the `db` argument." `get_db` is:

```python
async def get_db():
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
```

So every request automatically gets a fresh DB session that **auto-commits** on success and **auto-rolls-back** on exception. Your handler doesn't have to remember. This pattern (DI + scoped resources) is what makes web frameworks productive.

### 2.4 Transactions and rollback

A transaction is a group of DB changes that either all succeed or all fail. The `get_db` dependency above wraps each request in one. Concretely:

```
POST /pipeline/run does:
  1. SELECT the document
  2. INSERT a new Report
  3. UPDATE the document with the new report_id
  4. enqueue the Celery task
```

If step 3 fails, step 2 is rolled back — no orphan `Report` row. This is the kind of consistency a DataFrame gives you for free in memory but you have to ask for explicitly in databases.

### 2.5 Multipart upload (`UploadFile`)

JSON is text. PDFs are binary. You can't stuff a 21 MB PDF into a JSON body. So file uploads use **multipart/form-data**, a format that lets the client send named parts of mixed types in one request.

FastAPI parses this for you:

```python
async def upload_document(file: UploadFile = File(...), company_id: Optional[UUID] = Form(default=None)):
```

`UploadFile` is a stream-like object. `await file.read()` slurps the bytes. We then write them to disk under `data/uploads/{company_id}/{random-hash}.pdf`.

**Why a random hash?** To avoid collisions if two users upload `report.pdf`. The DB tracks `filename` (original) and `file_path` (where it landed) separately.

### 2.6 Why store the file on disk *and* a row in the DB?

PDFs are big, binary blobs. Databases technically can store them (BLOB columns) but:
- Backups blow up.
- Streaming a 50 MB row through Postgres is much slower than streaming a file.
- You can't easily share a "filesystem path" between Celery and FastAPI if it's in the DB.

Standard pattern: **file on disk, metadata in DB**. The DB row holds `file_path` and `file_type`; the file lives at that path. If the file goes missing, the row goes stale and you catch it with a "404: file missing on disk" check (which our `/reports/{id}/pdf` does).

### 2.7 Job IDs and polling

A Celery `delay(...)` call returns an `AsyncResult` with a unique `id` (a UUID). The API hands that back as `job_id`. The client polls `/pipeline/status/{job_id}` every few seconds. The handler does:

```python
async_result = AsyncResult(job_id, app=celery_app)
state = async_result.state  # "PENDING" | "STARTED" | "EXTRACTING" | "SUCCESS" | "FAILURE"
info = async_result.info    # whatever the task stashed via update_state
```

The worker writes its progress to Redis with `task.update_state(state="EXTRACTING", meta={"status": "…"})`. The API reads it back. **The API and the worker never talk to each other directly** — Redis is the only meeting point. This decoupling means you can restart either without affecting the other.

A more sophisticated setup would use **WebSockets** or **Server-Sent Events** so the server can push updates instead of being polled. Polling is fine for jobs that take minutes.

### 2.8 Foreign keys

`extracted_metrics.report_id` is a foreign key to `reports.id`. Postgres enforces it: you can't insert a metric pointing to a nonexistent report. The `ondelete="CASCADE"` modifier says "if the parent report is deleted, delete the metrics too." This is the equivalent of relational integrity you'd manually enforce in pandas with `assert df.report_id.isin(reports.id).all()` — except the DB does it on every write.

### 2.9 Migrations (and why we're not using them yet)

In production you don't drop and recreate tables. You write **migrations** — small scripts like "add column X, rename column Y" that Alembic (the SQLAlchemy migration tool) applies in order.

Right now we use `Base.metadata.create_all` on startup — it just creates whatever tables don't exist yet, and **ignores changes** to existing tables. That's why this session needed to make `uploaded_by` nullable in the model: if you'd already had a populated DB, the change wouldn't have taken effect, because `create_all` doesn't ALTER. Iteration 2+ should add Alembic.

### 2.10 Sync vs async Celery

You'll notice the Celery task is `def`, not `async def`:

```python
@celery_app.task
def run_extraction_pipeline(self, document_id, ...):
    result = asyncio.run(_run_pipeline_async(...))
```

Celery's worker runtime is sync (one task = one process). But our pipeline code is `async def` (because it awaits LLM calls). We bridge with `asyncio.run(...)`. That's not ideal — newer libraries like Arq are async-native — but it works fine for this scale.

---

## 3. How a request actually flows

Let's trace a real end-to-end run. I'll use the actual job IDs from your terminal session.

### Step 0 — services are running

```
[Docker]
  esg_postgres:5432       (the database)
  esg_redis:6379          (the message broker)
  esg_chromadb:8001       (vector store — for Iteration 2)
  esg_mlflow:5001         (experiment tracking — for Iteration 2)

[Host machine]
  uvicorn  app.main:app   on :8000   (the API)
  celery   --pool=solo                (the worker)
```

### Step 1 — upload a PDF

```
curl -X POST http://127.0.0.1:8000/api/v1/documents/upload -F "file=@ADCB.pdf"
```

What happens inside:

1. Uvicorn accepts the TCP connection, parses HTTP headers, recognizes multipart body.
2. FastAPI matches the route to `upload_document()` in `api/documents.py`.
3. Pydantic validates: `file` must be present.
4. `Depends(get_db)` opens a transaction.
5. `_get_or_create_default_company` reads / inserts a `companies` row.
6. `file.read()` slurps 21 MB of bytes.
7. We check file extension is `.pdf` and size ≤ 50 MB.
8. We write the bytes to `data/uploads/{company_id}/{hash}.pdf`.
9. We `db.add(Document(...))` — this stages the row.
10. `db.flush()` — Postgres assigns the `id` UUID; the row is in the transaction but not committed.
11. FastAPI serializes the response via Pydantic.
12. `get_db` commits the transaction.
13. Uvicorn writes the HTTP response. Status 201 reaches the client.

Total time: a few hundred ms (most of it is writing 21 MB to disk).

### Step 2 — run the pipeline

```
curl -X POST http://127.0.0.1:8000/api/v1/pipeline/run -d '{"document_id":"a798…"}'
```

1. FastAPI looks up the document.
2. Auto-creates a `Report` row (because none was linked yet).
3. Links `document.report_id = report.id`.
4. Calls `run_extraction_pipeline.delay(document_id=..., company_id=..., report_id=...)`. This is the magic line: it serializes the args to JSON and puts a message in Redis under the key `celery`. **No work has happened yet.**
5. `delay()` returns an `AsyncResult` immediately; its `.id` is a new UUID.
6. We return `{"job_id": "6d6840a3-…", "status": "queued"}` with HTTP 202.

Round-trip: ~30 ms. Meanwhile, in the worker:

1. The worker has been blocking on `BRPOP celery` (a Redis "pop from list, block until something appears" command).
2. Redis returns the message.
3. The worker deserializes the args and calls `run_extraction_pipeline(...)`.
4. Inside the task, `asyncio.run(_run_pipeline_async(...))` runs the M1→M4 chain:
   - **M1 ingestion** — `ingest_document(file_path)` parses the PDF.
   - `task.update_state(state="CHUNKING")` — Redis is updated.
   - **M2 chunking** — `chunk_document(...)` produces 1479 chunks.
   - **M2 classification** — `classify_chunks(...)` runs ClimateBERT on each chunk. This takes the longest.
   - **M3 extraction** — `extract_metrics(...)` calls the LLM 13 times (one per indicator). Each call goes through `ModelRouter.ainvoke_with_fallback` so it retries on the free model if the primary returns HTTP 402.
   - **M4 scoring** — `score_report(...)` computes GRI/FRA/SASB.
   - The worker INSERTs 13 `extracted_metrics` rows.
   - The worker UPDATEs the `reports` row with `total_score`, `gri_score`, etc.
   - The worker UPDATEs the `documents` row to `status='processed'`.
5. Final return value goes into Redis. State becomes `SUCCESS`.

Meanwhile, the client is polling:

```
curl http://127.0.0.1:8000/api/v1/pipeline/status/6d6840a3-...
```

Each poll reads `AsyncResult(...).state` from Redis and translates it (`EXTRACTING → "extracting", progress 70`). When it sees `SUCCESS`, it stops.

### Step 3 — review a metric

```
curl -X PATCH http://127.0.0.1:8000/api/v1/metrics/de6b8fb4-... -d '{"status":"approved","value":1050.5}'
```

1. FastAPI parses the path UUID and JSON body.
2. Pydantic validates: `status` must be a valid `MetricStatus` enum. Send `"bogus"` and you get 422 before the function runs.
3. The handler enforces a second rule (in code, not the schema): `status` must be `approved` or `rejected` — the other values are pipeline-internal.
4. Load the row, mutate it, set `reviewed_at = now()`, flush, commit.

This is the **human-in-the-loop** step. The pipeline gave you the LLM's best guess; the reviewer accepts or corrects. In Iteration 4, every correction would be embedded into ChromaDB so the next extraction sees similar examples in the prompt. For now, it just updates the row.

### Step 4 — generate the report

```
curl -X POST http://127.0.0.1:8000/api/v1/reports/generate -d '{"document_id":"a798…"}'
```

1. Lookup the document, find its report.
2. Count `approved` metrics — must be ≥1 or we return 400.
3. Enqueue `report.generate` Celery task.
4. Return job_id immediately.

Worker side, the task:
1. Loads the report, company, and all 13 metric rows.
2. Builds a `CompanyProfile`.
3. Calls `score_report(metrics)` again (cheap; pure-Python).
4. Calls `build_report_sections(...)` — groups metrics by GRI topic into ordered sections.
5. Calls `generate_narratives(sections)` — fires 9 LLM calls in parallel via `asyncio.gather`. Each section gets 2-4 paragraphs of factual narrative. If the LLM fails, a deterministic fallback narrative is used so the PDF always builds.
6. Calls `render_pdf(bundle, output_path)`:
   - Tries WeasyPrint first (best CSS, needs GTK3 on Windows — not installed here, so it fails fast).
   - Falls back to PyMuPDF `Story` (pure-Python, less polished CSS but always works).
   - Worst case: writes the raw HTML.
7. UPDATEs the report row with `pdf_path` and `status='published'`.

### Step 5 — download

```
curl http://127.0.0.1:8000/api/v1/reports/{id}/pdf -o report.pdf
```

1. FastAPI loads the report row.
2. Checks `pdf_path` is set and the file exists.
3. Returns `FileResponse(...)` — Uvicorn streams the file bytes back with `Content-Type: application/pdf`.

End of journey. From upload to PDF: about 7 minutes wall-clock on the ADCB PDF (the LLM extraction dominates).

---

## 4. Where things live

Mental map for navigating the repo:

```
backend/app/
├── main.py                      ← FastAPI app + route wiring
├── config.py                    ← env var → typed settings
├── database.py                  ← engine, session factory, get_db dependency
│
├── api/                         ← HTTP handlers (one file per resource)
│   ├── documents.py
│   ├── pipeline.py
│   ├── metrics.py
│   └── reports.py
│
├── models/                      ← SQLAlchemy ORM — the DB shape
│   ├── company.py / user.py
│   ├── document.py / report.py
│   ├── metric.py
│   └── enums.py
│
├── schemas/                     ← Pydantic — the API shape
│   ├── document.py / metric.py / report.py
│   └── pipeline.py
│
├── core/                        ← Pure pipeline logic (no HTTP, no DB-aware imports)
│   ├── ingestion/ nlp/ extraction/ scoring/ reporting/
│   └── llm/router.py            ← single chokepoint for all LLM calls
│
└── workers/
    ├── celery_app.py            ← Celery instance (broker URL, serialization)
    └── tasks.py                 ← @celery_app.task functions
```

Rule of thumb:
- An endpoint should be a thin shell that validates input, calls into `core/` or enqueues a `tasks.py` task, and returns. **No business logic in `api/`.**
- `core/` should never import from `api/` or `workers/`. The dependency arrow goes one direction.

---

## 5. Why no authentication yet

CLAUDE.md says explicitly: "Do NOT add auth yet — that comes after the pipeline is verified end-to-end via API."

So the upload endpoint accepts anyone, creates a default company on first use, and `Document.uploaded_by` is nullable.

When auth lands, the change is mostly mechanical:
1. Add a JWT middleware that decodes `Authorization: Bearer <token>` into a User row.
2. Add `user: User = Depends(get_current_user)` to every protected handler.
3. Replace "default company" logic with `user.company_id`.
4. Flip the nullable columns back.

The endpoints themselves don't change shape. That's the upside of doing auth last on a small project — you avoid the upfront cost of building login flows you'll need to redo anyway when the real identity provider (Auth0, Cognito, etc.) gets picked.

---

## 6. Common alternatives and why they weren't picked

| Picked | Alternative considered | Why ours |
|---|---|---|
| FastAPI | Flask | Flask is sync-first; LLM I/O begs for async. FastAPI gives free OpenAPI docs and Pydantic validation. |
| FastAPI | Django REST Framework | DRF assumes Django's ORM and lifecycle — too much weight when we already have SQLAlchemy. |
| Postgres | SQLite | SQLite serializes all writes through a single lock; Celery + FastAPI writing concurrently would queue up. |
| Postgres | MongoDB | The `ExtractedMetric` schema is rigid and relational. Document stores shine when fields are unpredictable. |
| Redis | RabbitMQ | RabbitMQ is more robust at scale but heavier to operate. For a 1-worker dev setup, Redis is plenty. |
| Celery | RQ | RQ is simpler but lacks Celery's task state tracking and retry sophistication. |
| Celery | Doing it inline in FastAPI | The pipeline takes 7 minutes. Inline = client timeout + API worker tied up. |
| Docker for infra only | Docker for everything | The application code changes constantly; rebuilding an image per change slows iteration. We containerize stable infra (DB, broker) and run app code on the host. |
| Pydantic | dataclasses | dataclasses don't validate. A bad client could send `value: "ten"` and crash deep in the pipeline. |
| SQLAlchemy ORM | Raw SQL via psycopg | Raw SQL invites injection bugs and disconnects type checking. ORMs let your IDE catch mistakes. |

---

## 7. Things that look weird until you've seen them before

- **`from __future__ import annotations`** at the top of every file — defers evaluation of type hints, so circular imports between models don't break things.
- **`Mapped[Optional[str]]` instead of `Optional[Mapped[str]]`** — SQLAlchemy reads the annotation to build the column; `Mapped` must be the outermost wrapper.
- **`await session.flush()` vs `await session.commit()`** — `flush` sends pending SQL to the DB (so you can read back the auto-generated `id`) but stays in the transaction. `commit` finalizes. We mostly flush; `get_db` commits at the end.
- **`asyncio.run` inside a Celery task** — bridges sync worker → async pipeline code. One asyncio loop per task invocation.
- **`task_acks_late=True` in `celery_app.py`** — the worker tells Redis "I've finished this task" only *after* it succeeds. If the worker crashes mid-task, Redis re-queues. With `acks_late=False`, you'd lose tasks on crash. The cost is the worker can run the same task twice if it crashes and recovers, so tasks should be **idempotent** (safe to run twice).
- **`from_attributes=True` in Pydantic** — lets a Pydantic schema be built from a SQLAlchemy ORM object's attributes (rather than a dict). That's why response handlers can `return doc` and FastAPI knows how to serialize it.

---

## 8. Mental model in one paragraph

The **API process** (Uvicorn + FastAPI) is the front door. It accepts HTTP, talks to **Postgres** for state, and drops jobs into **Redis** for anything slow. The **Celery worker** is a separate process that picks jobs out of Redis, runs the heavy ML/LLM pipeline in `core/`, writes results back to Postgres, and reports progress back to Redis. The client never talks to the worker — only to the API. Postgres is the only durable state. Redis is the rendezvous. Everything else — Docker, Pydantic, SQLAlchemy, FastAPI itself — exists to make those three components (API, worker, DB) cleaner to write and safer to run.

---

## 9. Glossary

- **ASGI** — Async Server Gateway Interface. The protocol Uvicorn ↔ FastAPI speak.
- **Broker** — The intermediary (Redis here) that holds task messages.
- **Backend (in Celery context)** — Where task results are stored. We use Redis for this too.
- **CRUD** — Create / Read / Update / Delete. The four basic ops on a resource.
- **Endpoint / route** — A URL + HTTP-method combination handled by one function.
- **FK / Foreign Key** — A column whose value must match a primary key in another table.
- **Idempotent** — Safe to run multiple times with the same result. `PUT /x` should be idempotent; `POST /x` typically isn't.
- **JWT** — JSON Web Token. The standard format for "logged-in user" bearer tokens. Not used yet.
- **Migration** — A versioned script that alters the DB schema. Use Alembic eventually.
- **ORM** — Object-Relational Mapper. Lets you treat DB rows as Python objects (SQLAlchemy here).
- **Pydantic model** — A class that validates and serializes JSON-shaped data.
- **Schema** — Ambiguous! Could mean a DB table layout (SQLAlchemy) or an API contract (Pydantic). Context disambiguates.
- **Serialization** — Turning a Python object into JSON (or vice versa).
- **Task / job** — A unit of background work. Celery's currency.
- **Transaction** — A group of DB changes that succeed or fail together.
- **UUID** — A 128-bit random identifier. We use them everywhere instead of auto-increment integers — they're globally unique and safe to generate before hitting the DB.

---

Pin this in your editor. When something in the code feels mysterious, the answer is almost always: "it's plumbing for one of the four backend jobs — listen, persist, coordinate, run-slow-stuff-out-of-band." If it's not doing one of those, it probably belongs in `core/`, not in the backend layer at all.
