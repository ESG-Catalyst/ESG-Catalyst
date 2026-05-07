# ESG Catalyst — Claude Code Context

## What This Project Is
AI-powered ESG reporting and scoring platform. Ingests Arabic and English company documents,
extracts ESG metrics using NLP + LLMs, scores against GRI/FRA/SASB frameworks, and generates
PDF reports with interactive dashboards.

Two user portals: Consultant Portal (manages multiple clients) and Company Portal (self-service).

## Current Phase: Phase 1 — Sequential Pipeline
NO LangGraph agents yet. The pipeline is a sequential Python module chain.
Phase 2 will wrap this pipeline in LangGraph agents — but Phase 1 must work cleanly first.

## Architecture

### Phase 1 (NOW — build this)
```
Upload → Ingestion → Chunker → Embedder → ChromaDB
                                              ↓
                                   Direct LLM calls via ModelRouter
                                              ↓
                                   Scoring (pure Python functions)
                                              ↓
                                   Report generator
                                              ↓
                                   FastAPI ←→ Streamlit UI
```

### Phase 2 (PLANNED — do NOT build yet)
Same pipeline but wrapped in LangGraph agents:
- IngestionAgent, ClassifierAgent, ExtractionAgent, ScoringAgent, ReportAgent
- Orchestrated by a Supervisor node
- Transition point: `backend/app/core/pipeline/` gets wrapped, FastAPI stays unchanged

## Project Structure
```
esg-catalyst/
├── CLAUDE.md                        ← You are here
├── .env                             ← Never commit this
├── .env.example                     ← Commit this (no real secrets)
├── docker-compose.yml
├── pyproject.toml                   ← All Python deps here
│
├── backend/
│   └── app/
│       ├── main.py                  ← FastAPI app entry point
│       ├── config.py                ← Pydantic Settings (reads .env)
│       ├── database.py              ← SQLAlchemy + async session
│       │
│       ├── models/                  ← SQLAlchemy ORM models (PostgreSQL)
│       │   ├── company.py
│       │   ├── user.py
│       │   ├── document.py
│       │   ├── metric.py            ← ExtractedMetric table
│       │   └── report.py
│       │
│       ├── schemas/                 ← Pydantic schemas (API request/response)
│       │   ├── company.py
│       │   ├── metric.py            ← ExtractedMetricSchema — source of truth
│       │   └── report.py
│       │
│       ├── api/                     ← FastAPI routers
│       │   ├── auth.py              ← /auth/register, /auth/login
│       │   ├── companies.py         ← /companies/
│       │   ├── documents.py         ← /documents/upload
│       │   ├── extraction.py        ← /extraction/run, /extraction/status
│       │   └── reports.py           ← /reports/generate, /reports/export
│       │
│       ├── core/
│       │   ├── pipeline/            ← THE PIPELINE (Phase 1 — sequential)
│       │   │   ├── ingestion.py     ← PDF/doc parsing, OCR
│       │   │   ├── chunker.py       ← Semantic chunking
│       │   │   ├── embedder.py      ← sentence-transformers embeddings
│       │   │   ├── classifier.py    ← ClimateBERT ESG relevance filter
│       │   │   ├── extractor.py     ← LLM calls per GRI indicator
│       │   │   └── scorer.py        ← GRI/FRA/SASB scoring logic
│       │   │
│       │   ├── models/              ← Model Abstraction Layer
│       │   │   └── router.py        ← ModelRouter class — swap LLMs via config
│       │   │
│       │   └── gri/                 ← GRI Knowledge Base
│       │       ├── indicators.py    ← GRI indicator definitions + prompts
│       │       └── frameworks.py    ← FRA/SASB mapping rules
│       │
│       └── workers/
│           └── tasks.py             ← Celery async tasks
│
├── frontend/
│   └── streamlit_app.py             ← Phase 1 UI (single file for now)
│
└── data/
    └── gri_indicators.json          ← GRI indicator library (seed data)
```

## The Single Most Important Data Schema
Every extracted value must produce an ExtractedMetric. This is the contract
between the pipeline, API, review UI, and report generator. NEVER deviate from this.
```python
class ExtractedMetricSchema(BaseModel):
    id: UUID
    company_id: UUID
    report_id: UUID
    gri_code: str                    # e.g. "GRI 302-1"
    fra_code: Optional[str]          # e.g. "FRA-36-SCOPE1"
    sasb_code: Optional[str]         # e.g. "FN-CB-430a.1"
    label: str                       # "Energy consumption within org"
    value: Optional[float]
    unit: Optional[str]              # normalized: "GJ", "tCO2e", "m3"
    original_value: Optional[str]    # raw value as found in doc
    original_unit: Optional[str]     # raw unit as found in doc
    confidence: float                # 0.0 – 1.0
    status: MetricStatus             # extracted|ambiguous|missing|rejected|approved
    source_file: Optional[str]
    source_page: Optional[int]
    evidence_chunk: Optional[str]    # the text passage used for extraction
    extraction_method: str           # "llm" | "questionnaire" | "manual"
    reviewer_id: Optional[UUID]
    reviewed_at: Optional[datetime]
    note: Optional[str]
    created_at: datetime
    updated_at: datetime
```

## GRI Indicators in Scope (Phase 1 — Banking Sector)
Build extraction prompts for these 13 indicators first:

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

## Tech Stack (do not deviate without asking)
- **Backend:** FastAPI + Python 3.11
- **Database:** PostgreSQL (via SQLAlchemy 2.0 async)
- **Vector store:** ChromaDB (two collections: `document_chunks`, `corrections_store`)
- **Task queue:** Celery + Redis
- **Embeddings:** sentence-transformers `paraphrase-multilingual-e5-base` (Arabic + English)
- **ESG classifier:** ClimateBERT (`climatebert/distilroberta-base-climate-detector`)
- **Document parsing:** PyMuPDF (digital PDFs) + Unstructured.io (scanned/complex)
- **OCR:** Tesseract with Arabic (`ara`) + English (`eng`) models
- **LLM access:** LangChain + OpenRouter API (model abstraction layer)
- **Frontend:** Streamlit (Phase 1), React+TypeScript (Phase 2)
- **Experiment tracking:** MLflow (extraction accuracy per GRI indicator per prompt)
- **Containerization:** Docker + Docker Compose

## Model Abstraction Layer — Critical Design
ALL LLM calls go through ModelRouter. Never call OpenRouter/OpenAI directly.
```python
# backend/app/core/models/router.py
class ModelRouter:
    def get_model(self, task: str) -> BaseChatModel:
        model_id = settings.models[task]  # reads from config
        return self._load(model_id)

# config maps:
# extraction  → "openrouter/anthropic/claude-3.5-sonnet"
# scoring     → "openrouter/meta-llama/llama-3.1-70b-instruct"
# report      → "openrouter/anthropic/claude-3.5-sonnet"
```

Swapping a model = change one line in .env. Zero code changes elsewhere.

## Environment Variables (.env)
```
# Database
DATABASE_URL=postgresql+asyncpg://postgres:password@localhost:5432/esg_catalyst

# Redis
REDIS_URL=redis://localhost:6379/0

# LLM (OpenRouter)
OPENROUTER_API_KEY=sk-or-...
MODEL_EXTRACTION=openrouter/anthropic/claude-3.5-sonnet
MODEL_SCORING=openrouter/meta-llama/llama-3.1-70b-instruct
MODEL_REPORT=openrouter/anthropic/claude-3.5-sonnet

# Vector Store
CHROMA_HOST=localhost
CHROMA_PORT=8001

# Embeddings (local model, no API key needed)
EMBEDDING_MODEL=paraphrase-multilingual-e5-base

# Auth
SECRET_KEY=your-secret-key-here
ACCESS_TOKEN_EXPIRE_MINUTES=30

# MLflow
MLFLOW_TRACKING_URI=http://localhost:5001

# App
ENVIRONMENT=development
MAX_UPLOAD_SIZE_MB=50
CONFIDENCE_THRESHOLD=0.80
```

## Coding Conventions
- Python 3.11+ features OK (match statements, tomllib, etc.)
- Async everywhere in FastAPI — use `async def` for all route handlers
- SQLAlchemy 2.0 style only — `select()` not legacy `query()`
- All Pydantic models use `model_validator` not `validator` (v2 style)
- Type hints on every function signature — no bare `Any` without a comment
- Docstrings on all public functions in `core/` — Google style
- Never hardcode GRI indicator definitions in Python — they live in `data/gri_indicators.json`
- Never hardcode model names in Python — they come from `settings.models`
- Error handling: never swallow exceptions silently in the pipeline. Log and re-raise.
- Confidence scores: when in doubt, return lower confidence. Never overstate certainty.

## What NOT to Build in Phase 1
- LangGraph / agent orchestration (Phase 2)
- React frontend (Streamlit only for now)
- Fine-tuning pipeline (post-investment)
- CDP/CSRD framework support (v2)
- Multi-language output (Arabic reports) — Arabic INPUT only for now
- Real-time ERP integrations
- Investor portal

## Phase 2 Transition Plan (do not build, just know this)
When Phase 1 pipeline works and is tested:
1. Create `backend/app/core/agents/` directory
2. Each pipeline module (`ingestion.py`, `extractor.py`, etc.) becomes a LangGraph node
3. Add `backend/app/core/agents/graph.py` — the LangGraph StateGraph definition
4. Add `backend/app/core/agents/supervisor.py` — orchestrates the node graph
5. FastAPI workers/tasks.py swaps `run_sequential_pipeline()` for `run_agent_graph()`
6. Nothing in `api/`, `models/`, `schemas/`, or Streamlit changes

The clean pipeline → agent transition is ONLY possible if Phase 1 has clean interfaces
between each pipeline module. Each function in `core/pipeline/` must have typed inputs
and outputs. No shared mutable state between pipeline steps.

## Feedback Loop (Correction Store — Phase 1.5)
Already architectured. When consultant corrects an extraction:
1. `Correction` record written to PostgreSQL
2. Embedded chunk + correction stored in ChromaDB `corrections_store` collection
3. `extractor.py` queries corrections_store before every LLM call
4. Top 3 similar past corrections injected as few-shot examples into prompt
5. MLflow logs accuracy delta before/after corrections

## Running the Project
```bash
# Start all services
docker-compose up -d

# Run backend (dev)
cd backend && uvicorn app.main:app --reload --port 8000

# Run Celery worker
cd backend && celery -A app.workers.tasks worker --loglevel=info

# Run Streamlit
cd frontend && streamlit run streamlit_app.py

# Run MLflow
mlflow ui --port 5001
```

## API Base URLs (dev)
- FastAPI: http://localhost:8000
- API docs: http://localhost:8000/docs
- Streamlit: http://localhost:8501
- ChromaDB: http://localhost:8001
- MLflow: http://localhost:5001

## Current Status
Phase 1 implementation COMPLETE (all 9 steps done). Moving to Windows laptop next.

### Completed steps:
1. ✅ docker-compose.yml + config.py + database.py (infrastructure)
2. ✅ SQLAlchemy models + Pydantic schemas (data contracts)
3. ✅ FastAPI skeleton → all routes now fully implemented (not 501)
4. ✅ Ingestion pipeline: ingestion.py + chunker.py + embedder.py + classifier.py
5. ✅ Extraction pipeline: extractor.py (LLM via ModelRouter, JSON parse, few-shot stub)
6. ✅ Scoring logic: scorer.py (GRI 50% + FRA 30% + SASB 20%, gap analysis)
7. ✅ Celery async tasks: workers/tasks.py — full pipeline orchestration with progress states
8. ✅ Streamlit UI: frontend/streamlit_app.py — upload → extract → results → export
9. ✅ Auth + multi-tenancy: JWT (access + refresh tokens), roles, company_id scoping on all routes

### Known blocker (fix on Windows):
- ORM model files (`metric.py`, `report.py`) still use `Mapped[X | None]` syntax.
  SQLAlchemy evaluates `Mapped[]` at runtime — Python 3.9 rejects `X | None` even with
  `from __future__ import annotations`. Replace ALL `X | None` inside `Mapped[...]` with
  `Optional[X]` in: `models/metric.py`, `models/report.py`.
  Files that are already correct: `models/user.py`, `models/document.py`, `models/company.py`.

### Running locally (SQLite dev mode):
- `config.py` defaults to `sqlite+aiosqlite:///./esg_catalyst.db` (no Postgres needed locally).
- `main.py` creates all tables on startup via `Base.metadata.create_all`.
- Override `DATABASE_URL` env var to switch back to Postgres.

### Next steps for Windows laptop:
1. Fix ORM `Mapped[X | None]` → `Mapped[Optional[X]]` in metric.py + report.py
2. Install from requirements.txt (`pip install -r requirements.txt`)
3. Install ML models: `pip install sentence-transformers transformers torch` (heavy — ~2GB)
4. Start services: `docker-compose up -d` (Postgres, Redis, ChromaDB, MLflow)
5. Run backend: `cd backend && uvicorn app.main:app --reload --port 8000`
6. Run Celery: `cd backend && celery -A app.workers.celery_app worker --loglevel=info`
7. Run Streamlit: `cd frontend && streamlit run streamlit_app.py`

## Team
6-person data science team, graduating June 2026.
Partners: Takeed (ESG certification client access), Datalentech (technical support).
Target: Egyptian banking sector first, then MENA expansion.