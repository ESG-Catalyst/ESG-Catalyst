# ESG Catalyst

AI-powered ESG reporting and scoring platform. Ingests Arabic and English
company documents, extracts ESG metrics via NLP + LLMs, scores against
GRI / FRA / SASB frameworks, and generates PDF reports with an interactive
dashboard.

Two user portals: Consultant (manages multiple clients) and Company
(self-service). Target sector: Egyptian banking (FRA-regulated NBFIs)
first, then MENA expansion.

For architectural depth see [`CLAUDE.md`](CLAUDE.md). For the narrative
behind recent changes see [`SESSION_NOTES.md`](SESSION_NOTES.md).

---

## Tech stack

- **Backend:** FastAPI + Celery + SQLAlchemy 2.0 (Postgres), Python 3.11
- **Pipeline:** PyMuPDF / python-docx / openpyxl ingestion → sentence-window
  chunker → 3-voter ESG classifier ensemble (ClimateBERT + finbert-esg +
  nbroad/ESG-BERT) → per-language embeddings (e5-base EN / bge-m3 AR) →
  ChromaDB → per-indicator LLM extraction → v1 disclosure-quality scorer →
  WeasyPrint PDF
- **Frontend:** React + TypeScript + Vite + TanStack Query + Zustand
- **Infra:** Docker Compose orchestrates Postgres, Redis, ChromaDB, MLflow,
  api, worker, frontend, and two browser admins (Adminer for Postgres,
  a Streamlit ChromaDB browser)

---

## Run everything from scratch

These steps take a fresh machine to a working stack. Allow ~30 minutes
end-to-end the first time (most of it is model downloads on the first
pipeline run).

### 1. Prerequisites

| Tool | Version | Why |
|---|---|---|
| Docker Desktop | latest | Postgres, Redis, ChromaDB, MLflow, api + worker + frontend all run in containers |
| Python | 3.11+ | Migration scripts + the optional pre-download helper |
| Git | any | Cloning |
| Node.js | 20+ | Only needed if you want to run the frontend outside Docker. The Compose stack runs Vite inside its own container, so for most workflows Node on the host is optional. |

On Windows, install Docker Desktop with WSL2 backend. On macOS / Linux,
either Docker Desktop or `docker` + `docker-compose` work.

### 2. Clone + branch

```bash
git clone https://github.com/ESG-Catalyst/ESG-Catalyst.git
cd ESG-Catalyst
git checkout main
```

### 3. Configure secrets

Copy the example env file:

```bash
cp .env.example .env
```

Then open `.env` and set at minimum:

- `OPENROUTER_API_KEY=sk-or-...` — get from <https://openrouter.ai>
- `GROQ_API_KEY=gsk_...` — get from <https://console.groq.com>. Free tier
  is enough for scoring + report narrative.
- `SECRET_KEY=...` — JWT signing secret. For dev, any random string is
  fine; for any shared environment, generate one with
  `python -c "import secrets; print(secrets.token_urlsafe(32))"`.

Optional knobs you'll probably leave at default:

- `PDF_BACKEND=auto` — `auto` (WeasyPrint primary, PyMuPDF Story fallback)
  is the default. Set to `pymupdf` as a one-line revert if WeasyPrint ever
  regresses; set to `weasyprint` to fail loudly instead of falling back.
- `CHUNK_STRATEGY=sentence_window` — the chunker default. `block_merge` is
  the legacy alternative.
- `MODEL_EXTRACTION` / `MODEL_REPORT` / `MODEL_SCORING` — LLM router
  endpoints. Defaults work; swap to your own if you have a contract.

### 4. (Optional) pre-download HuggingFace models

The worker downloads the embedder + classifier weights on first run
(~1.5–2 GB total: e5-base, bge-m3, ClimateBERT, finbert-esg, ESG-BERT).
If you want to do that before starting the stack — e.g. you're on a slow
connection and want a progress bar — run:

```bash
python scripts/download_models.py
```

This populates the Docker `hf_cache` volume so the worker doesn't
re-download. Safe to skip; the worker will fetch on first pipeline run.

### 5. Bring the stack up

```bash
docker compose up -d --build
```

First build takes 5–10 minutes (the worker image bakes torch CPU + Tesseract
+ WeasyPrint's GTK3 runtime + Noto fonts). Subsequent builds are minutes
thanks to Docker layer caching.

Verify health:

```bash
docker compose ps
```

Expect `(healthy)` next to `esg_api`, `esg_postgres`, `esg_redis`, `esg_worker`.
The first worker startup is slow (it preloads the embedder + classifier
ensemble); allow 60–90 seconds before the healthcheck flips.

### 6. Fresh DB migrations

A fresh Postgres comes up empty. SQLAlchemy `Base.metadata.create_all`
creates the schema on api startup, so **no migration is needed for a
fresh DB**.

If you're joining a project that already has data, run the two idempotent
migration scripts (safe to re-run; they check `information_schema` before
each ADD COLUMN):

```bash
docker compose exec api python scripts/migrate_reports_pillar_scores.py
docker compose exec api python scripts/migrate_documents_error_message.py
```

### 7. Smoke-test it

Open the URLs in the table below. Quick path:

1. **<http://localhost:5173>** — register an account (any email; password
   ≥ 6 chars; pick "Bank" or any institution type).
2. **Set your sector to one of `banking` / `insurance` / `consumer_finance`
   / `mortgage_finance`** — the registration form defaults industry to
   `commercial_bank`, which the scorer logs an unknown-sector warning for
   and falls back to `banking`. To set it explicitly:
   ```bash
   docker compose exec postgres psql -U postgres -d esg_catalyst -c \
     "UPDATE companies SET industry='banking' WHERE name='Your Institution Name';"
   ```
3. Upload one of the curated test docs from
   `data/ingestion_test_files/curated/` (NBE PDF is the fastest — ~6 pages,
   ~10 min end-to-end on a laptop).
4. Click **Run Pipeline**. The Pipeline Progress page shows
   chunking → classifying → embedding → extracting stages.
5. When done, **Approve some metrics**, then **Generate Report**. PDF
   appears in the Disclosures tab and downloads via the API at
   `/api/v1/reports/{id}/pdf`.

If the report shows realistic scores (not all 100s) and the PDF tables
have proper borders + headers — you're good.

### 8. Local URLs

| Service | URL | Purpose |
|---|---|---|
| Frontend | <http://localhost:5173> | React UI |
| API | <http://localhost:8000> | FastAPI |
| API docs | <http://localhost:8000/docs> | Swagger / interactive |
| MLflow | <http://localhost:5001> | Experiment tracking (extraction runs land in `esg-extraction`) |
| ChromaDB | <http://localhost:8001> | Vector store HTTP |
| ChromaDB browser | <http://localhost:8502> | Streamlit UI to browse collections + run semantic queries |
| Adminer | <http://localhost:8080> | Postgres browser (server `postgres`, user `postgres`, pass `password`, db `esg_catalyst`) |
| Streamlit (legacy) | <http://localhost:8501> | Pre-React UI; rarely used now |

---

## Pulling someone else's changes

After someone pushes to `main`:

```bash
git pull origin main
docker compose build worker api      # rebuild if backend Python or Dockerfile changed
docker compose up -d worker api      # pick up the new images
# If their commit added DB migrations, run them once:
docker compose exec api python scripts/migrate_<...>.py
```

The frontend container uses Vite HMR with file polling so React changes
hot-reload without a rebuild — just refresh the browser tab.

---

## Daily dev loop

- **Backend edits** (Python): the worker has `./backend` bind-mounted, but
  Python doesn't auto-reload Celery tasks. After editing a `core/*` file:
  ```bash
  docker compose restart worker
  ```
- **Frontend edits**: Vite HMR picks them up immediately. Hard-refresh if
  state goes weird.
- **Pipeline status**: tail `docker logs esg_worker -f` and watch for
  `pipeline.classified`, `pipeline.embedded`, `indicator_extracted`,
  `pipeline.complete`.
- **DB inspection**: <http://localhost:8080> (Adminer) or
  `docker compose exec postgres psql -U postgres -d esg_catalyst`.
- **ChromaDB inspection**: <http://localhost:8502> (browse collections,
  filter by `where`, run semantic queries).
- **MLflow runs**: <http://localhost:5001>, experiment `esg-extraction`.

---

## Common gotchas

- **Worker is solo-pool.** Only one pipeline runs at a time per worker.
  Multiple uploads queue up. Intentional — M3 LLM extraction is the
  bottleneck, not parallelism.
- **First-run model download blocks pipeline start.** The worker preloads
  models lazily on first use. If your first pipeline seems stuck at
  `classifying` for 5 minutes, it's downloading — check
  `docker logs esg_worker -f`.
- **OpenRouter free tier rate-limits.** If LLM calls return HTTP 402 / 429,
  the `ModelRouter` falls back to the free model in `.env`
  (`MODEL_EXTRACTION_FALLBACK`). Look for
  `model_router.fallback_activated` in worker logs.
- **Auth tokens expire after 30 min** (default
  `ACCESS_TOKEN_EXPIRE_MINUTES`). If API calls start returning
  `401 Invalid token`, log out and back in.
- **Cross-tenant access returns 404, not 403.** This is intentional — it
  prevents an attacker from enumerating other tenants' IDs. Don't be
  surprised when "you don't own this" looks like "doesn't exist".
- **Industry must be one of the four known sectors** (`banking`,
  `insurance`, `consumer_finance`, `mortgage_finance`). Anything else
  logs a warning and falls back to `banking`. See
  [`CLAUDE.md`](CLAUDE.md) (section *ESG Scoring Methodology — v1*) for
  the rubric and the "Adding a sector" recipe.

---

## Project layout

See `## Project Structure` in [`CLAUDE.md`](CLAUDE.md). Quick orientation:

```
backend/app/
  api/          FastAPI routers (auth, documents, pipeline, metrics, reports, admin)
  core/
    ingestion/  M1 — parser dispatch (PDF/DOCX/XLSX/CSV/TXT/images)
    nlp/        M1/M2 — chunker, embedder, classifier
    extraction/ M3 — per-indicator retrieval + LLM extraction
    scoring/    M4 — v1 disclosure-quality scorer
    reporting/  M5 — builder + narrative + PDF renderer
    llm/        ModelRouter (extraction / scoring / report tasks)
    gri/        46-indicator catalog loader
    tracking/   MLflow fail-safe wrappers
  workers/      Celery tasks (run_extraction_pipeline, report.generate)
frontend/react/ Vite + React + TypeScript
data/           gri_indicators.json, uploads/, generated_reports/, curated test docs
scripts/        download_models.py, migrate_*.py, run_full_pipeline.py
```

---

## Where to look when things break

| Symptom | Where to look |
|---|---|
| Pipeline hangs at "classifying" | `docker logs esg_worker -f` — first-run model download or CPU saturated |
| Pipeline hangs at "extracting" | OpenRouter rate-limit — look for `model_router.fallback_activated` |
| Scores are 0 or weird | Check the metric `status` + `value` columns in `extracted_metrics`; the v1 scorer is described in [`CLAUDE.md`](CLAUDE.md) |
| Dashboard scores ≠ PDF scores | Shouldn't happen post-2026-05-23. If it does, the worker hasn't re-run `score_report` at report-generation time — restart worker |
| PDF tables render as raw text | `PDF_BACKEND=auto` and WeasyPrint failed to load — check worker logs for `renderer.weasyprint_unavailable` |
| Cross-tenant 404 you didn't expect | You're hitting a resource that belongs to another user's company — correct behavior |
| `Invalid token` everywhere | JWT expired (30 min). Log out + back in |

For anything else, the [`CLAUDE.md`](CLAUDE.md) session log has the full
narrative of every fix landed so far.