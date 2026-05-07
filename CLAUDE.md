# ESG Catalyst — Claude Code Context

## What This Project Is

ESG Catalyst is an AI-powered ESG (Environmental, Social, and Governance) reporting and
scoring platform built as a senior data science graduation project. It demonstrates applied
NLP, document understanding, LLM-based extraction, and automated scoring at production quality.

Companies upload their documents. The platform extracts ESG metrics, scores them against
international frameworks, generates a gap analysis, and produces a formatted ESG report.

**This is a data science showcase with a real product interface — not a prototype.**

---

## Important: Existing Codebase

There is already code in this repository from an earlier build session.
Before building anything new, Claude Code must:

1. Read all existing files and understand what is there
2. Keep anything that is correct and matches this CLAUDE.md
3. Replace anything that contradicts this CLAUDE.md (wrong patterns, wrong structure)
4. Delete anything that is no longer needed
5. Never duplicate existing functionality

Do not start from scratch blindly. Audit first, then build.

---

## Graduation Scope — What Gets Built

This is the complete product for graduation. Nothing is deferred except the items
listed under Future Work at the end of this file.

```
┌─────────────────────────────────────────────────────────────────────┐
│                        ESG CATALYST PLATFORM                        │
│                                                                     │
│  ┌─────────────┐     ┌──────────────────────────────────────────┐  │
│  │  React Web  │────▶│              FastAPI Backend              │  │
│  │  Frontend   │◀────│                                          │  │
│  └─────────────┘     │  ┌────────────────────────────────────┐  │  │
│                       │  │        AI Pipeline (Core DS Work)  │  │  │
│                       │  │                                    │  │  │
│                       │  │  Ingestion → NLP → Extraction      │  │  │
│                       │  │      → Scoring → Report Gen        │  │  │
│                       │  └────────────────────────────────────┘  │  │
│                       │                                          │  │
│                       │  PostgreSQL  │  ChromaDB  │  Redis       │  │
│                       └──────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Team Module Split

Each module is independently buildable. Clear interfaces between them.
One or two team members own each module.

| Module | Directory | What it does |
|--------|-----------|--------------|
| **M1 Ingestion** | `backend/app/core/ingestion/` | Parse any document format, OCR, extract raw text |
| **M2 NLP Processing** | `backend/app/core/nlp/` | Chunk, embed, classify ESG relevance |
| **M3 Extraction** | `backend/app/core/extraction/` | LLM-based metric extraction + confidence scoring |
| **M4 Scoring** | `backend/app/core/scoring/` | GRI/SASB/TCFD scoring, gap analysis, materiality |
| **M5 Report Generation** | `backend/app/core/reporting/` | Build structured report, generate narrative, render PDF |
| **M6 API** | `backend/app/api/` | FastAPI routes, auth, job queue, data models |
| **M7 Frontend** | `frontend/` | React web application |

Each module exposes a clean Python interface. No module imports from another module's internals.
All communication between modules goes through the defined input/output schemas in `backend/app/schemas/`.

---

## Project Structure

```
esg-catalyst/
├── CLAUDE.md
├── .env                          ← never commit
├── .env.example
├── docker-compose.yml            ← postgres, redis, chromadb, mlflow
├── pyproject.toml
├── requirements.txt
│
├── backend/
│   └── app/
│       ├── main.py               ← FastAPI entry point
│       ├── config.py             ← Pydantic Settings from .env
│       ├── database.py           ← SQLAlchemy async engine + session
│       │
│       ├── models/               ← SQLAlchemy ORM (database tables)
│       │   ├── base.py
│       │   ├── company.py
│       │   ├── user.py
│       │   ├── document.py
│       │   ├── metric.py
│       │   └── report.py
│       │
│       ├── schemas/              ← Pydantic v2 (API contracts + pipeline contracts)
│       │   ├── company.py
│       │   ├── document.py
│       │   ├── metric.py         ← ExtractedMetric — central contract
│       │   ├── report.py
│       │   └── pipeline.py       ← PipelineInput, PipelineOutput, PipelineState
│       │
│       ├── api/                  ← FastAPI routers
│       │   ├── auth.py           ← /auth/register, /auth/login, /auth/refresh
│       │   ├── companies.py      ← /companies/
│       │   ├── documents.py      ← /documents/upload, /documents/{id}
│       │   ├── pipeline.py       ← /pipeline/run, /pipeline/status/{job_id}
│       │   ├── metrics.py        ← /metrics/{report_id}, /metrics/{id}/review
│       │   └── reports.py        ← /reports/generate, /reports/{id}, /reports/{id}/pdf
│       │
│       ├── core/
│       │   │
│       │   ├── ingestion/        ← M1: Document parsing
│       │   │   ├── __init__.py
│       │   │   ├── parser.py     ← route by file type to correct parser
│       │   │   ├── pdf_parser.py ← PyMuPDF (digital) + Unstructured (scanned)
│       │   │   ├── ocr.py        ← Tesseract Arabic+English for image PDFs
│       │   │   └── table_extractor.py ← preserve table structure from PDFs
│       │   │
│       │   ├── nlp/              ← M2: Text processing
│       │   │   ├── __init__.py
│       │   │   ├── chunker.py    ← semantic chunking (NOT fixed-size)
│       │   │   ├── embedder.py   ← multilingual sentence embeddings
│       │   │   └── classifier.py ← ClimateBERT ESG relevance filter
│       │   │
│       │   ├── extraction/       ← M3: Metric extraction (core DS work)
│       │   │   ├── __init__.py
│       │   │   ├── extractor.py  ← orchestrates per-indicator extraction
│       │   │   ├── prompts.py    ← extraction prompt templates per indicator
│       │   │   ├── validator.py  ← validate + normalize extracted values
│       │   │   └── confidence.py ← confidence scoring logic
│       │   │
│       │   ├── scoring/          ← M4: ESG scoring (core DS work)
│       │   │   ├── __init__.py
│       │   │   ├── scorer.py     ← orchestrates full scoring
│       │   │   ├── gri_scorer.py ← GRI completeness scoring
│       │   │   ├── sasb_scorer.py← SASB sector-specific scoring
│       │   │   ├── tcfd_scorer.py← TCFD pillar scoring
│       │   │   ├── gap_analysis.py ← missing disclosures + recommendations
│       │   │   └── materiality.py  ← materiality assessment per sector
│       │   │
│       │   ├── reporting/        ← M5: Report generation
│       │   │   ├── __init__.py
│       │   │   ├── builder.py    ← structure metrics into report sections
│       │   │   ├── narrative.py  ← LLM-generated narrative per section
│       │   │   └── renderer.py   ← PDF rendering (WeasyPrint)
│       │   │
│       │   └── llm/              ← Shared LLM access (used by M3 + M5)
│       │       ├── __init__.py
│       │       └── router.py     ← ModelRouter — ALL LLM calls go here
│       │
│       └── workers/
│           ├── celery_app.py     ← Celery + Redis config
│           └── tasks.py          ← async pipeline tasks
│
├── frontend/                     ← M7: React web application
│   ├── package.json
│   ├── src/
│   │   ├── main.tsx
│   │   ├── App.tsx
│   │   ├── pages/
│   │   │   ├── Landing.tsx       ← product homepage
│   │   │   ├── Dashboard.tsx     ← company overview + past reports
│   │   │   ├── Upload.tsx        ← document upload + pipeline trigger
│   │   │   ├── Results.tsx       ← extraction results + review queue
│   │   │   ├── Report.tsx        ← report viewer + PDF download
│   │   │   └── Auth.tsx          ← login / register
│   │   ├── components/
│   │   │   ├── MetricCard.tsx    ← single metric with confidence + evidence
│   │   │   ├── ScoreDashboard.tsx← E/S/G scores + gap heatmap
│   │   │   ├── DocumentUpload.tsx← drag-and-drop uploader
│   │   │   ├── PipelineStatus.tsx← live job progress
│   │   │   └── GapAnalysis.tsx   ← missing metrics + recommendations
│   │   └── api/
│   │       └── client.ts         ← typed API calls to FastAPI
│   └── public/
│
└── data/
    ├── gri_indicators.json       ← GRI indicator definitions (seed data)
    ├── sasb_standards.json       ← SASB sector materiality maps
    └── emission_factors.json     ← emission conversion factors
```

---

## The Central Data Contract

Every piece of data the pipeline extracts must become an ExtractedMetric.
This is the single contract between all modules. Never deviate.

```python
# backend/app/schemas/metric.py

class MetricStatus(str, Enum):
    EXTRACTED  = "extracted"   # pipeline extracted, awaiting review
    AMBIGUOUS  = "ambiguous"   # could map to multiple indicators
    MISSING    = "missing"     # indicator required but not found
    APPROVED   = "approved"    # human confirmed
    REJECTED   = "rejected"    # human rejected
    EDITED     = "edited"      # human corrected the value

class ExtractedMetric(BaseModel):
    id:                UUID
    company_id:        UUID
    report_id:         UUID

    # Framework mapping
    gri_code:          str
    sasb_code:         Optional[str]
    tcfd_pillar:       Optional[str]
    label:             str

    # The value
    value:             Optional[float]
    unit:              Optional[str]     # normalized: "GJ", "tCO2e", "m3"
    original_value:    Optional[str]
    original_unit:     Optional[str]

    # Trust layer — non-negotiable
    confidence:        float             # 0.0 to 1.0
    status:            MetricStatus
    source_file:       Optional[str]
    source_page:       Optional[int]
    evidence_chunk:    Optional[str]     # exact text passage used

    # How it was obtained
    extraction_method: str               # "llm" | "questionnaire" | "manual"

    # Review trail
    reviewer_id:       Optional[UUID]
    reviewed_at:       Optional[datetime]
    note:              Optional[str]

    created_at:        datetime
    updated_at:        datetime
```

---

## ESG Framework Knowledge

### GRI Standards (load from data/gri_indicators.json — never hardcode)

**Universal (required for all companies):**
- GRI 2: General disclosures — org profile, governance, strategy, stakeholders
- GRI 3: Material topics determination process

**Environmental 300 series:**
- GRI 302: Energy — consumption, intensity, reductions
- GRI 303: Water — withdrawal, consumption, discharge
- GRI 305: Emissions — Scope 1, Scope 2, Scope 3, intensity
- GRI 306: Waste — generation, diversion, disposal

**Social 400 series:**
- GRI 401: Employment — hires, turnover, parental leave
- GRI 403: Occupational health and safety — incidents, fatalities, near-misses
- GRI 404: Training and education — hours per employee, performance reviews
- GRI 405: Diversity — board composition, gender pay ratio
- GRI 406: Non-discrimination incidents and corrective actions
- GRI 418: Customer privacy — substantiated complaints, data breaches

**Governance:**
- Board independence percentage
- Audit committee existence and independence
- Ethics violations and anti-corruption measures

### SASB Materiality (load from data/sasb_standards.json)
Sector-specific topics that matter most for scoring:
banking, software, manufacturing, retail, oil_gas, utilities, pharma, food_beverage
If sector unknown: use default materiality map

### TCFD Pillars
- Governance: board oversight, management role
- Strategy: risks/opportunities identified, business impact, scenario resilience
- Risk Management: identification process, management process, integration
- Metrics & Targets: metrics used, Scope 1/2/3 emissions, targets + performance

### Emission Factors (load from data/emission_factors.json)
- electricity: 0.4409 kg CO2e per kWh
- natural gas: 2.0 kg CO2e per m3
- diesel: 2.68 kg CO2e per liter
- gasoline: 2.31 kg CO2e per liter

### Scoring Weights
- Environmental: 40% of composite score
- Social: 35% of composite score
- Governance: 25% of composite score

### Benchmark Tiers
- 85–100: Leader
- 70–84: Above average
- 50–69: Average
- 30–49: Below average
- 0–29: Laggard

---

## Module Specifications

### M1 — Ingestion

Input: raw file + metadata
Output: ParsedDocument — clean text, extracted tables, page count, detected language

Supported: PDF (digital), PDF (scanned), XLSX, CSV, PNG/JPG
Arabic support: detect RTL, preserve Arabic numerals and units
Table extraction: keep row-column relationships intact
OCR: Tesseract ara+eng language pack

### M2 — NLP Processing

Input: ParsedDocument
Output: list of Chunk objects stored in ChromaDB

Chunking: semantic — split at paragraph/section boundaries, never mid-sentence.
Keep table rows together. Keep footnotes with their reference.
Target: 300-500 tokens per chunk, 50 token overlap.

Embeddings: paraphrase-multilingual-e5-base (Arabic + English in same space)

ClimateBERT: climatebert/distilroberta-base-climate-detector
Classify each chunk as ESG-relevant or not.
Only ESG-relevant chunks proceed to extraction.

### M3 — Extraction

Input: ESG-relevant chunks + target GRI indicators
Output: list of ExtractedMetric

Per indicator flow:
1. Vector search ChromaDB for top-5 most relevant chunks
2. Build extraction prompt (system + indicator definition + evidence)
3. Call LLM via ModelRouter("extraction")
4. Parse JSON response
5. Normalize unit + validate value
6. Assign confidence score
7. Return ExtractedMetric

Prompt rule: extract only what is explicitly stated. Never infer, estimate, or hallucinate.
If value is absent: return null with confidence 0.

Confidence scoring:
- Start at 1.0, reduce for: indirect language, approximate values, single source,
  unit ambiguity, OCR-extracted text
- Threshold: < 0.80 → flag for human review

Unit normalization:
- Energy → GJ (accept kWh, MWh, TJ, toe)
- Emissions → tCO2e
- Water → m3 (accept liters, gallons, ML)
- Always store both normalized and original

### M4 — Scoring

Input: list of ExtractedMetric + company sector
Output: ESGScore with overall, E/S/G breakdown, completeness, benchmark, gaps, recommendations

GRI completeness: approved_count / required_for_sector
SASB score: weight metrics by SASB materiality score for this sector
TCFD score: % of TCFD disclosure elements present
Benchmark: compare composite vs industry average from sasb_standards.json

Gap analysis per missing indicator:
- Why it matters
- What document type would contain it
- Priority: high/medium/low based on materiality score

### M5 — Report Generation

Input: approved ExtractedMetrics + ESGScore + company profile
Output: PDF file

builder.py: group metrics by GRI topic → ordered ReportSection list
narrative.py: LLM drafts narrative per section — factual only, English only,
              reference specific values, note what is missing
renderer.py: WeasyPrint HTML-to-PDF

Report sections:
Cover, Executive Summary, Company Profile, Materiality Assessment,
Environmental, Social, Governance, GRI Content Index, Gap Analysis

---

## LLM Access — ModelRouter

ALL LLM calls go through core/llm/router.py. No exceptions.

```python
class ModelRouter:
    def get_model(self, task: str) -> BaseChatModel:
        # task: "extraction" | "scoring" | "report"
        model_id = settings.models[task]
        return self._load(model_id)
```

.env model config:
```
MODEL_EXTRACTION=openrouter/anthropic/claude-3.5-sonnet
MODEL_SCORING=openrouter/meta-llama/llama-3.1-70b-instruct
MODEL_REPORT=openrouter/anthropic/claude-3.5-sonnet
```

---

## API Routes

```
POST   /auth/register
POST   /auth/login
POST   /auth/refresh

POST   /companies/
GET    /companies/{id}
PATCH  /companies/{id}

POST   /documents/upload
GET    /documents/{id}
DELETE /documents/{id}

POST   /pipeline/run
GET    /pipeline/status/{job_id}

GET    /metrics/{report_id}
PATCH  /metrics/{id}
GET    /metrics/{report_id}/export

POST   /reports/generate
GET    /reports/{id}
GET    /reports/{id}/pdf
GET    /reports/
```

Pipeline job states:
queued → parsing → chunking → classifying → extracting → scoring → complete | failed

---

## Frontend Pages

/ — Landing page: product description, 3-step how-it-works, call to action
/auth — Login and register
/dashboard — Past reports list, score trend, quick stats, New Report button
/upload — Drag-and-drop upload, pipeline progress with live stage labels
/results/:id — Metric list (left) + evidence viewer (right), approve/edit/reject actions
/report/:id — Score circles (E/S/G), benchmark badge, gap heatmap, PDF download

Design: teal #0D7A7A primary, #0B2B3B dark, #E8A020 accent, Inter font, Tailwind CSS

---

## Environment Variables

```
DATABASE_URL=sqlite+aiosqlite:///./esg_catalyst.db
REDIS_URL=redis://localhost:6379/0
OPENROUTER_API_KEY=sk-or-REPLACE_ME
MODEL_EXTRACTION=openrouter/anthropic/claude-3.5-sonnet
MODEL_SCORING=openrouter/meta-llama/llama-3.1-70b-instruct
MODEL_REPORT=openrouter/anthropic/claude-3.5-sonnet
CHROMA_HOST=localhost
CHROMA_PORT=8001
EMBEDDING_MODEL=paraphrase-multilingual-e5-base
SECRET_KEY=dev-secret-key-replace-in-production
ACCESS_TOKEN_EXPIRE_MINUTES=60
MLFLOW_TRACKING_URI=http://localhost:5001
CONFIDENCE_THRESHOLD=0.80
MAX_UPLOAD_SIZE_MB=50
ENVIRONMENT=development
```

---

## Coding Standards

Python:
- Python 3.11+, async everywhere in FastAPI
- SQLAlchemy 2.0: select() only, never .query()
- Pydantic v2: model_validator not validator
- Mapped[Optional[X]] — never Mapped[X | None]
- Type hints on every function, Google docstrings on all core/ functions
- Never hardcode GRI/SASB data — always load from data/*.json
- Never hardcode model names — always from settings.models
- Log and re-raise in pipeline — never swallow exceptions silently

TypeScript/React:
- Functional components only
- Custom hooks for all API calls
- Typed responses — no any
- Loading and error states on every data-fetching component

---

## Known Issues to Fix First

1. ORM syntax: models/metric.py and models/report.py
   Replace all Mapped[X | None] with Mapped[Optional[X]]

2. Streamlit: delete frontend/streamlit_app.py if it exists
   Remove streamlit from requirements.txt and pyproject.toml
   The frontend is now React in frontend/

3. Module structure: if existing core/ layout differs from this CLAUDE.md,
   reorganize to match. Move files rather than rewrite where logic is correct.

---

## Build Order

Step 1  Audit existing code vs this CLAUDE.md. Fix ORM issues. Delete Streamlit.
        Reorganize directory structure if needed.
        Goal: uvicorn app.main:app --reload starts without errors.

Step 2  Verify or complete M1 ingestion — test on a real PDF.
        Output: ParsedDocument with clean text and extracted tables.

Step 3  Verify or complete M2 NLP — test on ParsedDocument from Step 2.
        Output: chunks in ChromaDB, ClimateBERT classifications visible.

Step 4  Verify or complete M3 extraction — test on chunks from Step 3.
        Output: list of ExtractedMetric objects with confidence scores.

Step 5  Verify or complete M4 scoring — test on metrics from Step 4.
        Output: ESGScore with E/S/G breakdown, benchmark tier, gap list.

Step 6  Build M5 report generation — not yet implemented.
        Output: downloadable PDF report from approved metrics.

Step 7  Verify or complete M6 API — all routes working, auth working,
        full pipeline triggerable via POST /pipeline/run.

Step 8  Build M7 React frontend — all pages, connected to real API.
        Output: working web application at localhost:5173.

Step 9  End-to-end test: upload PDF → pipeline runs → review metrics
        → generate report → download PDF. Fix any integration issues.

Step 10 MLflow integration: log extraction accuracy metrics per run.
        Demonstrate measurable model performance in graduation demo.

---

## MLflow — Accuracy Tracking (Graduation Demo Evidence)

```python
with mlflow.start_run(run_name=f"extraction_{report_id}"):
    mlflow.log_param("model", settings.models["extraction"])
    mlflow.log_metric("indicators_extracted", extracted_count)
    mlflow.log_metric("indicators_missing", missing_count)
    mlflow.log_metric("avg_confidence", avg_confidence)
    mlflow.log_metric("high_confidence_rate", high_conf_pct)
    mlflow.log_metric("gri_completeness", gri_completeness)
```

Track accuracy across different documents and models.
Use in the graduation presentation to show quantitative DS rigor.

---

## Running the Project

```bash
docker-compose up -d

# Backend
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# Celery worker
cd backend
celery -A app.workers.celery_app worker --loglevel=info

# Frontend
cd frontend
npm install
npm run dev

# MLflow
mlflow ui --port 5001
```

URLs: Frontend :5173 | API :8000 | Docs :8000/docs | ChromaDB :8001 | MLflow :5001

---

## Future Work (Post-Graduation)

**Technical roadmap:**
- LangGraph agent orchestration replacing the sequential pipeline
- Human-in-the-loop review interface with correction feedback loop
- Correction store (ChromaDB) + Prompt Builder for few-shot learning
- Fine-tuning pipeline on accumulated corrections (RL from human feedback)
- Arabic report output (Arabic input only for graduation)

**Business roadmap:**
- Multi-tenant SaaS with team collaboration
- White-label deployment for ESG certification partners
- MENA market expansion (Egypt → Saudi Arabia → UAE)
- ERP and HR system integrations
- Investor portfolio ESG scoring module
- Direct regulatory submission workflow