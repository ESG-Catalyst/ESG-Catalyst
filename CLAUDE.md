# ESG Catalyst — Claude Code Context

## What This Project Is
AI-powered ESG reporting and scoring platform. Ingests Arabic and English company documents,
extracts ESG metrics using NLP + LLMs, scores against GRI/FRA/SASB frameworks, and generates
PDF reports with interactive dashboards.

Two user portals: Consultant Portal (manages multiple clients) and Company Portal (self-service).
Target: Egyptian banking sector (FRA-regulated NBFIs) first, then MENA expansion.

---

## Iteration Roadmap — Read This First

```
Iteration 0  ✅ DONE      Thin end-to-end pipeline: PDF in → report PDF out (proof of concept)
Iteration 1  🔧 NOW       Fix two blockers + rebuild API + wire Streamlit to API + MLflow
Iteration 2  📋 NEXT      Deepen each module independently — each owner enhances their files
Iteration 3  📋 PLANNED   LangGraph agents wrap the pipeline (no external changes)
Iteration 4  📋 PLANNED   Human-in-the-Loop review UI + correction feedback loop
```

**Do NOT skip iterations. Do NOT start Iteration 2 module work until Iteration 1 is confirmed end-to-end.**
**Do NOT build LangGraph until Iteration 2 is stable.**

---

## Current State — Iteration 1

### What exists (Iteration 0 — thin, proof-of-concept quality)
All modules exist and the pipeline runs end-to-end. Quality is minimal throughout.
- M1 Ingestion: works on clean digital PDFs only
- M2 NLP chain: logic correct — blocked by missing model downloads
- M3 Extraction: logic correct — blocked by exhausted OpenRouter credits
- M4 Scoring: GRI/FRA/SASB weights applied, benchmark tiers uncalibrated
- M5 Report generation: PDFs generate, narrative generic, formatting plain
- API: deleted (previous attempt broken — clean rebuild needed)
- Streamlit: runs via direct Python imports, not wired to API yet
- MLflow: in docker-compose, not wired to pipeline code

### Blocker 1 — HuggingFace models not downloaded
`embedder.py` requires `paraphrase-multilingual-e5-base` (~400MB).
`classifier.py` requires `climatebert/distilroberta-base-climate-detector` (~250MB).
Neither is cached. Pipeline fails at M2 on any fresh machine.

**Fix:** Create `scripts/download_models.py` — downloads and caches both models.
Safe to re-run (skips if cached). Add to new-machine setup steps.
Both files must load from cache — never re-download on every call.

### Blocker 2 — OpenRouter credits exhausted
`extractor.py` → `ModelRouter("extraction")` → HTTP 402 → zero metrics extracted.

**Fix:** Add free-tier fallback to `core/models/router.py`.
- Primary: `MODEL_EXTRACTION` from .env (unchanged)
- Fallback: `MODEL_EXTRACTION_FALLBACK` from .env — activates only on HTTP 402
- Log warning when fallback activates. If both fail, raise — never silently return empty.
- Add `MODEL_EXTRACTION_FALLBACK=openrouter/mistralai/mistral-7b-instruct:free` to `.env.example`

### Session log
| Date | What was done | What's next |
|------|---------------|-------------|
| 2026-05-10 | M1→M5 confirmed end-to-end. PDFs generate. API deleted. Two blockers found. | Fix blockers, rebuild API |
| 2026-05-10 | Blocker 1 resolved. download_models.py created. .env model ID fixed. M2 chain tested end-to-end (1479 chunks, 721 relevant, E/S/G classified). | Blocker 2 (ModelRouter fallback), API rebuild |
| 2026-05-10 | Blocker 2 resolved. ModelRouter.ainvoke_with_fallback() fires on HTTP 402 / "insufficient credits" / "key limit exceeded"; logs "Primary model unavailable, using free fallback". MODEL_EXTRACTION updated to claude-sonnet-4.5 (old ID returned 404); MODEL_EXTRACTION_FALLBACK=openai/gpt-oss-20b:free. M3 verified on M2 relevant chunks (831 of 1479): GRI 305-1 extracted 960 tCO2e @ confidence 1.0 with evidence citation. Other 3 indicators still missing due to 60K char truncation + free-model capability — Iteration 2 work. | API rebuild, M3 Iteration 2 (indicator-aware chunk selection, prompt quality) |
| 2026-05-10 | M5 quality pass. Full M1→M5 run on ADCB PDF produced 6-page PDF in `data/generated_reports/`. Fixed narrative.py (deterministic fallback no longer leaks raw 403/JSON error text; treats `original_value`-only metrics as disclosed; uses router credit-fallback path). Fixed renderer.py (robust status rendering via helper, color status pills, evidence excerpts under metrics, PyMuPDF `Story` added as 2nd PDF backend so PDFs render even without GTK3/WeasyPrint). Added `scripts/run_full_pipeline.py` end-to-end driver (DB-bypassing). Out-of-scope M4 issues found: gap_analysis returns 0 gaps despite 9 missing indicators; G pillar score = 0 even though FRA-36 was extracted; no `report` task fallback configured in ModelRouter. | Fix M4 gap_analysis + add MODEL_REPORT_FALLBACK, then rebuild API |
| 2026-05-11 | Iteration 1 API rebuild. Deleted old `api/auth.py`, `api/companies.py`, `core/auth.py`; rewrote `documents.py`, `pipeline.py`, `metrics.py`, `reports.py`, `main.py` under `/api/v1/...` with no auth and `try/except → 422` on unexpected errors. Added `report.generate` Celery task (M5 driver: builder → narrative → renderer → persist `pdf_path`). Made `Document.uploaded_by` and `Report.created_by` nullable; added `DocumentStatus.uploaded`. Upload auto-creates a "Default Company" row; `/pipeline/run` auto-creates the `Report` row and links `Document.report_id`. Full end-to-end smoke against Postgres + Redis (dockerized) with host-run Celery solo worker: ADCB PDF uploaded → 13 metrics extracted (3 found, 10 missing — same M4 behavior flagged in previous session) → 1 metric approved via PATCH → published PDF (253 KB, magic bytes `%PDF-1.7`) streamed back from `/reports/{id}/pdf`. All four stages curl-confirmed; counter-cases (404 / 400 / 422) verified. | Iteration 2 module deepening (M3 indicator-aware chunking + prompt quality, M4 gap_analysis fix, add `MODEL_REPORT_FALLBACK`, wire Streamlit to the new API, MLflow tracking). Auth deferred until pipeline-via-API is exercised on more documents. |
| 2026-05-11 | Recreated `frontend/streamlit_app.py` (deleted in commit 6bb6568) as a minimal single-file app wired entirely through HTTP to `/api/v1/...` — no `core.pipeline.*` imports. Five linear flows + session state: upload → pipeline run with 2s status polling + `st.progress`, metrics table (gri_code/value/unit/confidence/status) with per-row approve/reject PATCH, report generate with status polling, PDF download via `st.download_button`. `API_BASE_URL = "http://localhost:8000"` at top. Added `streamlit>=1.36.0` + `requests>=2.32.0` to `requirements.txt` and installed streamlit into venv. Contract smoke-test against the running API confirmed response shapes match the app's reads: upload (201 → `{document_id, filename, status}`), pipeline status with unknown job (200 → `{job_id, stage:"queued", progress:0, error:null}`), metrics/report 404 detail bodies. Full upload→PDF flow not run end-to-end (requires Celery worker + LLM credits + models). | User to run `streamlit run frontend/streamlit_app.py` against the live worker stack for an end-to-end check; then move on to Iteration 2 backlogs (M3 prompt quality, M4 gap_analysis, MLflow wiring). |

| 2026-05-11 | M6 Celery worker bug fix surfaced by the new Streamlit app's first real upload→PDF run. Every pipeline task after the first failed with `AttributeError: 'NoneType' object has no attribute 'send'` inside asyncpg `transport.write` — root cause: SQLAlchemy's cached pool held asyncpg transports bound to the previous `asyncio.run()` event loop's proactor (closed between Celery solo-pool tasks); on the next task, `pool_pre_ping=True` validated those stale connections on the dead loop. First attempt (`await get_engine().dispose()` at the top of `_run_pipeline_async` / `_generate_report_async` / `_mark_*_failed` in `workers/tasks.py`) was insufficient because pre-ping still ran on stale connections returned from the pool. Final fix: switched `database.py` to `poolclass=NullPool` (one config line, removed the now-redundant dispose calls). Verified by running two back-to-back pipelines on the same worker process — both completed (ingestion → classifying → extracting → complete, 3 metrics each); before the fix only run #1 ever survived. Also noticed: uvicorn + celery must be launched from the project root with `PYTHONPATH=backend` so pydantic-settings finds `./.env` — running from `backend/` silently falls back to SQLite and reads an empty DB. | Iteration 2 backlogs: M3 prompt quality + indicator-aware chunk selection (still only 3/13 metrics extracted), M4 gap_analysis fix, add `MODEL_REPORT_FALLBACK`, MLflow wiring. Auth deferred until the API is exercised against more documents. |

*Append a row here after every session.*

---

## Architecture

### Sequential Pipeline (Iteration 0 — all modules exist)
```
Upload → Ingestion (PyMuPDF + Unstructured.io + Tesseract OCR)
       → Chunker (semantic, preserves tables + section headers)
       → Embedder (paraphrase-multilingual-e5-base — Arabic + English)
       → ChromaDB (document_chunks collection)
       → ClimateBERT (ESG relevance classifier)
       → Extractor (LLM per GRI indicator via ModelRouter → ExtractedMetric)
       → Scorer (GRI 50% + FRA 30% + SASB 20%, gap analysis)
       → Report Builder → Narrative Generator → PDF Renderer (WeasyPrint)
       → FastAPI + Celery ←→ Streamlit UI
```

### Iteration 1 — API rebuild
```
POST /api/v1/documents/upload          → save file + create Document record
POST /api/v1/pipeline/run              → trigger M1→M4 Celery task → {job_id}
GET  /api/v1/pipeline/status/{job_id}  → {stage, progress 0–100, error}
GET  /api/v1/metrics/{document_id}     → list of ExtractedMetricSchema
PATCH /api/v1/metrics/{metric_id}      → approve / reject / edit value+unit
POST /api/v1/reports/generate          → trigger M5 Celery task (requires ≥1 approved metric)
GET  /api/v1/reports/{id}/pdf          → stream PDF (404 if not ready)
```
No auth in first pass — add after all endpoints are curl-confirmed working.
Routes call pipeline via Celery tasks only — never import core modules directly in routes.

### Iteration 3 — LangGraph (Do NOT build yet)
```
Same pipeline — each module becomes a LangGraph node, functions unchanged.
backend/app/core/agents/
    graph.py        ← StateGraph definition
    supervisor.py   ← conditional routing (retry, branch on confidence)
    nodes/          ← one file per module, wraps existing functions
workers/tasks.py: swap run_sequential_pipeline() → run_agent_graph()
Everything else: unchanged.
```

### Iteration 4 — Human-in-the-Loop (Do NOT build yet)
```
Review Queue (Streamlit page → React later):
    Metrics with confidence < 0.80 → consultant review
    Approve / edit / reject per metric → Correction record (PostgreSQL)
    Corrections embedded → ChromaDB corrections_store
    PromptBuilder injects top-3 similar corrections as few-shot examples
MLflow tracks accuracy per GRI indicator per prompt version.
```

---

## Project Structure
```
esg-catalyst/
├── CLAUDE.md
├── .env                             ← Never commit
├── .env.example
├── docker-compose.yml               ✅
├── pyproject.toml                   ✅
├── requirements.txt                 ✅
│
├── scripts/
│   └── download_models.py           ⬜ CREATE — Blocker 1 fix, run on every new machine
│
├── data/
│   ├── gri_indicators.json          ✅
│   ├── uploads/                     ✅ PDFs stored here per company_id
│   └── generated_reports/           ✅ M5 output
│
├── backend/
│   └── app/
│       ├── main.py                  ✅
│       ├── config.py                ✅
│       ├── database.py              ✅
│       │
│       ├── models/                  ← SQLAlchemy ORM
│       │   ├── company.py           ✅
│       │   ├── user.py              ✅
│       │   ├── document.py          ✅
│       │   ├── metric.py            ✅ Mapped[Optional[X]] confirmed
│       │   └── report.py            ✅ Mapped[Optional[X]] confirmed
│       │
│       ├── schemas/                 ← Pydantic v2 — source of truth for all data contracts
│       │   ├── company.py           ✅
│       │   ├── metric.py            ✅ ExtractedMetricSchema — never change without team discussion
│       │   └── report.py            ✅
│       │
│       ├── api/                     ← DELETED — rebuild in Iteration 1
│       │   ├── documents.py         ⬜
│       │   ├── pipeline.py          ⬜
│       │   ├── metrics.py           ⬜
│       │   └── reports.py           ⬜
│       │
│       ├── core/
│       │   ├── pipeline/            ← M1–M4 — iter0, do not refactor during Iteration 1
│       │   │   ├── ingestion.py     ✅
│       │   │   ├── chunker.py       ✅
│       │   │   ├── embedder.py      ✅ blocked by Blocker 1
│       │   │   ├── classifier.py    ✅ blocked by Blocker 1
│       │   │   ├── extractor.py     ✅ blocked by Blocker 2
│       │   │   └── scorer.py        ✅
│       │   │
│       │   ├── report/              ← M5 — iter0, confirmed working
│       │   │   ├── builder.py       ✅
│       │   │   ├── narrative.py     ✅
│       │   │   └── renderer.py      ✅
│       │   │
│       │   ├── models/
│       │   │   └── router.py        ⚠️ needs free-tier fallback — Blocker 2 fix
│       │   │
│       │   ├── gri/
│       │   │   ├── indicators.py    ✅
│       │   │   └── frameworks.py    ✅
│       │   │
│       │   └── agents/              ← DO NOT CREATE — Iteration 3 only
│       │
│       └── workers/
│           └── tasks.py             ✅ Celery orchestration
│
├── frontend/
│   └── streamlit_app.py             ✅ iter0 — direct imports, not wired to API yet
│
└── mlflow/                          ⬜ not wired to pipeline yet
```

---

## The Single Most Important Data Schema
Every extracted value must produce an `ExtractedMetric`.
This is the contract between pipeline, API, review UI, and report generator.
**Never change this schema without a full team discussion.**

```python
class ExtractedMetricSchema(BaseModel):
    id: UUID
    company_id: UUID
    report_id: UUID
    gri_code: str                    # "GRI 302-1"
    fra_code: Optional[str]          # "FRA-36-SCOPE1"
    sasb_code: Optional[str]         # "FN-CB-430a.1"
    label: str
    value: Optional[float]
    unit: Optional[str]              # normalized: "GJ", "tCO2e", "m3"
    original_value: Optional[str]
    original_unit: Optional[str]
    confidence: float                # 0.0 – 1.0
    status: MetricStatus             # extracted|ambiguous|missing|rejected|approved
    source_file: Optional[str]
    source_page: Optional[int]
    evidence_chunk: Optional[str]
    extraction_method: str           # "llm" | "questionnaire" | "manual"
    reviewer_id: Optional[UUID]
    reviewed_at: Optional[datetime]
    note: Optional[str]
    created_at: datetime
    updated_at: datetime
```

---

## GRI Indicators in Scope (Banking Sector — v1)

| Code | Name | Primary Source | Difficulty |
|------|------|---------------|------------|
| GRI 2-1 | Organizational details | Annual report | Easy |
| GRI 2-9 | Governance structure | Board report | Medium |
| GRI 302-1 | Energy consumption | Electricity + gas bills | Hard (Arabic) |
| GRI 302-3 | Energy intensity | Utility bills + revenue | Medium |
| GRI 303-5 | Water consumption | Water bills | Hard (Arabic) |
| GRI 305-1 | Direct GHG (Scope 1) | Fuel receipts | Hard |
| GRI 305-2 | Indirect GHG (Scope 2) | Electricity bills | Medium |
| GRI 305-4 | GHG intensity | Scope 1+2 + revenue | Medium |
| GRI 401-1 | New hires + turnover | HR export | Easy |
| GRI 403-9 | Work injuries | Safety logs | Medium |
| GRI 405-1 | Board diversity | Board report | Easy |
| GRI 418-1 | Privacy complaints | Compliance report | Medium |
| FRA-36 | Total Scope 1+2 | Fuel + electricity | Hard |

---

## Team Ownership

Each person works only in their listed files.
Cross-module changes require team discussion first.

| Module | Files | Iteration 2 focus |
|--------|-------|-------------------|
| M1 Ingestion | `ingestion.py`, `chunker.py` | Scanned PDF + Arabic OCR + table extraction |
| M2 NLP | `embedder.py`, `classifier.py`, `scripts/download_models.py` | Model caching + threshold tuning |
| M3 Extraction | `extractor.py`, `core/models/router.py` | Prompt engineering + confidence calibration |
| M4 Scoring | `scorer.py`, `core/gri/` | Benchmark calibration + gap analysis depth |
| M5 Report | `core/report/` | Narrative quality + PDF formatting + GRI Content Index |
| M6 API | `api/`, `workers/tasks.py` | Iteration 1 rebuild + MLflow wiring |

---

## Iteration 2 — Module Enhancement Backlogs

Start only after Iteration 1 is confirmed end-to-end. Each owner works their backlog independently.

### M1 — Ingestion + Chunker
```
[ ] Scanned PDF handling — trigger Tesseract when PyMuPDF returns empty text
[ ] Arabic OCR — verify Tesseract ara model, test on Arabic utility bills
[ ] Table extraction — Unstructured.io table mode, preserve structure in chunks
[ ] Section header tagging — tag each chunk with parent section heading
[ ] Multi-file ingestion — accept zip of PDFs for one company
[ ] Chunk size tuning — benchmark vs extraction accuracy
[ ] Language detection — tag each chunk "ar" or "en"
```

### M2 — Embedder + Classifier
```
[ ] Fix Blocker 1 (download_models.py) — prerequisite for everything below
[ ] Validate embedding quality — similarity search on known ESG vs non-ESG pairs
[ ] Tune ClimateBERT threshold — test on 20+ labeled chunks, find optimal cutoff
[ ] Log classification stats — N processed, N passed, N filtered per run
[ ] Arabic recall — test retrieval specifically on Arabic chunks
[ ] ChromaDB restart safety — handle "collection already exists" gracefully
```

### M3 — Extractor + ModelRouter
```
[ ] Fix Blocker 2 (fallback in router.py) — prerequisite for everything below
[ ] Indicator-specific prompts — replace generic stubs for all 13 GRI codes
    Each prompt: what it measures, expected units, Egyptian bank patterns, 2-3 examples
[ ] Confidence calibration — run on 10 known PDFs, compare to ground truth
[ ] Retry on malformed JSON — one retry with stricter prompt before failing
[ ] Rate limit handling — exponential backoff on HTTP 429
[ ] Token usage logging — prompt + completion tokens per call
```

### M4 — Scorer
```
[ ] Benchmark tier calibration — research Egyptian NBFI ESG baselines, set realistic tiers
[ ] FRA-36 mapping — verify against actual FRA carbon reporting circular
[ ] Gap analysis depth — add: why it matters, difficulty to close, data source needed
[ ] Partial credit — consider 50% weight for "ambiguous" status metrics
```

### M5 — Report Generation
```
[ ] Narrative quality — per section: what metric shows, YoY if available, compliance status, recommendation
[ ] Cover page — company name, ESG Catalyst branding, report date, report ID
[ ] Score summary box — E/S/G breakdown + overall tier on page 2
[ ] Evidence citations — source_file + source_page footnote per metric value
[ ] Gap analysis table — color-coded by severity (red/amber/green)
[ ] GRI Content Index — required table: all indicators, status, page reference
[ ] Appendix — raw metrics table including rejected, with confidence scores
[ ] Report versioning — increment version on regeneration
```

---

## Model Abstraction Layer
ALL LLM calls go through `ModelRouter`. Never call OpenRouter directly.

```python
# core/models/router.py
class ModelRouter:
    def get_model(self, task: str) -> BaseChatModel:
        model_id = settings.models[task]   # from .env — never hardcoded
        return self._load(model_id)
```

Model swap = one line in `.env`. Zero code changes.
Enables: OpenRouter → AWS Bedrock → self-hosted post-investment.

---

## Report Generation — Phase 2 Spec (COMPLETE — do not rebuild)

**Trigger:** metrics with status = "approved" exist for a document.

```python
ReportSection(
    title: str,         # "Energy"
    gri_topic: str,     # "GRI 302"
    metrics: list[ExtractedMetric],
    narrative: str      # filled by narrative.py
)
```

PDF sections: cover, company profile, methodology, GRI content index,
topic disclosures, gap analysis, appendix.
Branding: teal `#0D7A7A` headers, company name on cover.

---

## Environment Variables (.env)
```
# Database
DATABASE_URL=postgresql+asyncpg://postgres:password@localhost:5432/esg_catalyst

# Redis
REDIS_URL=redis://localhost:6379/0

# LLM
OPENROUTER_API_KEY=sk-or-...
MODEL_EXTRACTION=openrouter/anthropic/claude-3.5-sonnet
MODEL_EXTRACTION_FALLBACK=openrouter/mistralai/mistral-7b-instruct:free
MODEL_SCORING=openrouter/meta-llama/llama-3.1-70b-instruct
MODEL_REPORT=openrouter/anthropic/claude-3.5-sonnet

# Vector Store
CHROMA_HOST=localhost
CHROMA_PORT=8001

# Embeddings — run scripts/download_models.py once on each machine
EMBEDDING_MODEL=paraphrase-multilingual-e5-base
CLIMATEBERT_MODEL=climatebert/distilroberta-base-climate-detector

# Auth
SECRET_KEY=change-in-production
ACCESS_TOKEN_EXPIRE_MINUTES=30

# MLflow
MLFLOW_TRACKING_URI=http://localhost:5001

# App
ENVIRONMENT=development
MAX_UPLOAD_SIZE_MB=50
CONFIDENCE_THRESHOLD=0.80
```

---

## Coding Conventions
- Python 3.11+
- Async everywhere in FastAPI — `async def` for all route handlers
- SQLAlchemy 2.0 style — `select()` not legacy `query()`
- Pydantic v2 — `model_validator` not `validator`
- `Mapped[Optional[X]]` not `Mapped[X | None]` — Python 3.9 compat
- Type hints on every function — no bare `Any` without a comment
- Docstrings on all public functions in `core/` — Google style
- Never hardcode GRI indicators — they live in `data/gri_indicators.json`
- Never hardcode model names — they come from `settings.models`
- Never swallow exceptions silently — log and re-raise
- Confidence: when uncertain, score lower. Never overstate.
- Narrative: factual only — describe what metrics show, never extrapolate

---

## Running the Project

```bash
# New machine setup
python scripts/download_models.py   # one-time, ~650MB
pip install -r requirements.txt
docker-compose up -d

# Daily dev
cd backend && uvicorn app.main:app --reload --port 8000
cd backend && celery -A app.workers.celery_app worker --loglevel=info
cd frontend && streamlit run streamlit_app.py
mlflow ui --port 5001
```

| Service | URL |
|---------|-----|
| FastAPI | http://localhost:8000 |
| API docs | http://localhost:8000/docs |
| Streamlit | http://localhost:8501 |
| ChromaDB | http://localhost:8001 |
| MLflow | http://localhost:5001 |

---

## What NOT to Build Until Told
- LangGraph / agents — Iteration 3
- React frontend — Iteration 4+
- Auth in API — after all endpoints curl-confirmed
- Correction feedback loop — Iteration 4
- Fine-tuning — post-investment
- CDP/CSRD/TCFD — v2
- Arabic report output — Arabic input only in v1
- ERP integrations — v2
- Investor portal — v2