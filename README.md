<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white" alt="Python" />
  <img src="https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=white" alt="React" />
  <img src="https://img.shields.io/badge/TypeScript-5.6-3178C6?logo=typescript&logoColor=white" alt="TypeScript" />
  <img src="https://img.shields.io/badge/FastAPI-0.110-009688?logo=fastapi&logoColor=white" alt="FastAPI" />
  <img src="https://img.shields.io/badge/PostgreSQL-16-4169E1?logo=postgresql&logoColor=white" alt="PostgreSQL" />
  <img src="https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white" alt="Docker" />
  <img src="https://img.shields.io/badge/MLflow-Tracked-0194E2?logo=mlflow&logoColor=white" alt="MLflow" />
</p>

# ESG Catalyst

**An AI-powered ESG reporting and scoring platform** that ingests bilingual (Arabic & English) corporate documents, extracts ESG metrics using a multi-model NLP pipeline + LLMs, scores them against **GRI / SASB / FRA** frameworks, and generates compliance-ready PDF reports — all through an interactive React dashboard.

> **Target Market:** Egyptian financial institutions (FRA-regulated NBFIs), expanding to MENA.  
> **Two Portals:** Consultant workspace (multi-client management) & Company portal (self-service).

---

## What This Solves

ESG compliance in the MENA financial sector is a manual, months-long process involving consultants reading hundreds of pages across Arabic and English documents. **ESG Catalyst automates the entire pipeline** — from raw document to scored, branded PDF report — in under 30 minutes per document.

---

## Key Features

| Feature | Details |
|---------|---------|
| **Multi-Format Ingestion** | PDF, DOCX, XLSX, CSV, TXT — with Arabic BiDi/reshaping for RTL text extraction |
| **7-Stage ML Pipeline** | Ingest → Chunk → Classify → Embed → Extract → Score → Report |
| **3-Model ESG Classifier** | Ensemble of ClimateBERT + FinBERT-ESG + ESG-BERT (2-of-3 voting) with +62% recall over single-model baseline |
| **Bilingual Embeddings** | Language-routed: `multilingual-e5-base` for English, `BAAI/bge-m3` for Arabic — validated on 20-query bilingual test set |
| **46-Indicator Catalog** | GRI Financial Services, SASB FN-CF/MF/IN, and FRA KPIs with per-indicator extraction prompts |
| **Disclosure-Quality Scoring** | 6-tier quality ladder × confidence factor × sector-specific materiality weights |
| **4-Sector Support** | Banking, Insurance, Consumer Finance, Mortgage Finance — add a sector with a JSON edit |
| **PDF Report Generation** | WeasyPrint primary + PyMuPDF fallback — branded, table-formatted, GRI Content Index included |
| **Full Auth & Multi-Tenancy** | JWT-based auth, per-company data isolation, cross-tenant access returns 404 (not 403) |
| **Bilingual UI** | Full English/Arabic i18n with RTL layout support |
| **MLflow Experiment Tracking** | Per-extraction run metrics: confidence by indicator, model usage, retrieval stats |

---

## Architecture

```
                           ┌─────────────────────────┐
                           │     React Frontend       │
                           │  TypeScript · Vite · RTL │
                           └────────────┬────────────┘
                                        │ REST API
                           ┌────────────▼────────────┐
                           │    FastAPI (async)        │
                           │  JWT Auth · Pydantic v2   │
                           └──────┬──────────┬────────┘
                                  │          │
                    ┌─────────────▼──┐  ┌────▼──────────┐
                    │   PostgreSQL   │  │     Redis      │
                    │  (persistent)  │  │   (broker)     │
                    └────────────────┘  └────┬──────────┘
                                             │
                           ┌─────────────────▼────────────────┐
                           │       Celery Worker               │
                           │                                   │
                           │  ┌─── M1: Ingestion ────────────┐ │
                           │  │  PyMuPDF · python-docx ·     │ │
                           │  │  openpyxl · Arabic reshaper  │ │
                           │  └──────────────────────────────┘ │
                           │  ┌─── M2: NLP ──────────────────┐ │
                           │  │  Sentence-window chunker      │ │
                           │  │  3-model ESG classifier       │ │
                           │  │  Bilingual embedder → ChromaDB│ │
                           │  └──────────────────────────────┘ │
                           │  ┌─── M3: Extraction ───────────┐ │
                           │  │  Per-indicator retrieval      │ │
                           │  │  LLM extraction (OpenRouter)  │ │
                           │  │  Monetary/currency parsing    │ │
                           │  └──────────────────────────────┘ │
                           │  ┌─── M4: Scoring ──────────────┐ │
                           │  │  GRI · SASB · FRA · TCFD     │ │
                           │  │  Sector-driven materiality    │ │
                           │  │  Gap analysis                 │ │
                           │  └──────────────────────────────┘ │
                           │  ┌─── M5: Reporting ────────────┐ │
                           │  │  Section builder              │ │
                           │  │  LLM narrative generation     │ │
                           │  │  WeasyPrint PDF renderer      │ │
                           │  └──────────────────────────────┘ │
                           │                                   │
                           │  MLflow ◄── experiment tracking   │
                           └───────────────────────────────────┘
```

---

## Technical Highlights

### Data Science & ML
- **Classifier Ensemble Architecture** — Conducted a systematic 4-stage evaluation (C1–C4): bias audit of ClimateBERT → single-model shootout → multi-architecture comparison → production integration. The 3-voter ensemble recovered +87% S-pillar recall over the ClimateBERT baseline, with all decisions documented in a reproducible decision log.
- **Bilingual Embedding Strategy** — Language-routed embedding (e5-base EN / bge-m3 AR) selected via a 5-model shootout on a bilingual retrieval test set. Discovered that an English-only evaluation would have selected the wrong model (mpnet collapsed to 0.30 R@5 on Arabic).
- **Sentence-Window Chunking** — Replaced block-merge chunking after a 5-strategy comparison. Custom composite objective (`n_esg − 2·n_short − 5·n_long`) selected window=3, stride=1, max=1500 chars — yielding +62% ESG-relevant chunks with 1.3% truncation risk (down from 46.8% noise).
- **Disclosure-Quality Scoring** — 6-tier quality ladder (missing → ambiguous → qualitative → numeric → fully cited) × LLM confidence factor × sector-specific materiality weights from a data-driven catalog. Sector-swap produces materially different scores on identical metrics.

### Backend Engineering
- **Async-First Architecture** — FastAPI with SQLAlchemy 2.0 async sessions, Celery background workers with `asyncio.run` bridge, and `NullPool` to prevent asyncpg transport leaks across Celery solo-pool event loops.
- **LLM Resilience** — `ModelRouter` with automatic free-tier fallback on HTTP 402/429, per-task `max_tokens` caps to prevent credit over-reservation, and `LLMUnavailableError` propagation that marks documents as failed (not silently empty).
- **Multi-Tenant Security** — JWT auth with per-company data scoping. Cross-tenant access returns 404 (not 403) to prevent ID enumeration. Shared `require_company()` / `require_owned_record()` dependency injection eliminates 7 copies of scope-guard boilerplate.
- **498 Unit Tests** — Covering monetary parsing, confidence calibration, 46-indicator catalog validation, v1 scoring methodology, and report-section building. All dependency-light (no torch/network/DB).

### Frontend Engineering
- **React 19 + TypeScript** — Vite, TanStack Query for server state, Zustand for client state, Framer Motion for animations, Recharts for data visualization.
- **Full Bilingual Support** — Complete English/Arabic i18n with RTL layout, `dir`/`lang` attribute management, and mobile-responsive drawer navigation.
- **Pipeline Visualization** — Real-time progress tracking with chunk-grid visualizer, elapsed timers, stage-specific error handling, and credit-exhaustion recovery UX.

### Infrastructure
- **Docker Compose Orchestration** — 9-service stack: API, Worker, Frontend, PostgreSQL, Redis, ChromaDB, MLflow, Adminer, and a custom Streamlit ChromaDB browser.
- **Optimized Container Sizes** — Worker image reduced from 10.3 GB to 3.67 GB (−64%) via CPU-only PyTorch wheels and split requirements. API image 917 MB (−91% from shared image).
- **HuggingFace Model Caching** — Shared `hf_cache` Docker volume persists ~2 GB of model weights across rebuilds. `preload_models()` for warm worker startup.

---

## Tech Stack

| Layer | Technologies |
|-------|-------------|
| **Frontend** | React 19 · TypeScript 5.6 · Vite 6 · TailwindCSS 4 · TanStack Query · Zustand · Framer Motion · Recharts · Radix UI · i18next |
| **Backend** | Python 3.11 · FastAPI · Celery · SQLAlchemy 2.0 (async) · Pydantic v2 · bcrypt + JWT Auth |
| **NLP/ML** | PyTorch (CPU) · HuggingFace Transformers · ClimateBERT · FinBERT-ESG · ESG-BERT · multilingual-e5-base · BAAI/bge-m3 |
| **LLM** | OpenRouter (Claude Sonnet / GPT / Mistral) · LangChain · per-task max_tokens · automatic fallback |
| **Data** | PostgreSQL 16 · Redis · ChromaDB (cosine HNSW, dual-collection) · MLflow |
| **PDF** | WeasyPrint (primary) · PyMuPDF Story (fallback) · Jinja2 templates · Noto fonts |
| **DevOps** | Docker Compose · multi-stage builds · bind-mount dev · named volumes · health checks |
| **Testing** | pytest (498 tests) · bilingual retrieval test sets · ground-truth ESG classification sets |

---

## Quick Start

### Prerequisites

| Tool | Version | Required For |
|------|---------|-------------|
| Docker Desktop | latest | Full stack (Postgres, Redis, ChromaDB, MLflow, API, Worker, Frontend) |
| Git | any | Cloning |

### Setup

```bash
# Clone and configure
git clone https://github.com/ESG-Catalyst/ESG-Catalyst.git
cd ESG-Catalyst
cp .env.example .env
# Edit .env: set OPENROUTER_API_KEY, GROQ_API_KEY, SECRET_KEY

# Launch the full stack
docker compose up -d --build

# Verify health (allow 60-90s for worker model preload)
docker compose ps
```

### First Run

1. Open **http://localhost:5173** — register an account
2. Upload a test document from `data/ingestion_test_files/curated/`
3. Click **Run Pipeline** — watch real-time progress through 7 stages
4. **Approve metrics** → **Generate Report** → Download PDF

### Service URLs

| Service | URL | Purpose |
|---------|-----|---------|
| Frontend | http://localhost:5173 | React dashboard |
| API Docs | http://localhost:8000/docs | Interactive Swagger |
| MLflow | http://localhost:5001 | Experiment tracking |
| Adminer | http://localhost:8080 | PostgreSQL browser |
| ChromaDB Browser | http://localhost:8502 | Vector store inspector |

---

## Project Structure

```
backend/app/
  api/            FastAPI routers (auth, documents, pipeline, metrics, reports, admin)
  core/
    ingestion/    M1 — parser dispatch (PDF/DOCX/XLSX/CSV/TXT), Arabic BiDi
    nlp/          M2 — sentence-window chunker, 3-model classifier, bilingual embedder
    extraction/   M3 — per-indicator ChromaDB retrieval + LLM extraction
    scoring/      M4 — v1 disclosure-quality scorer, gap analysis, TCFD
    reporting/    M5 — section builder + LLM narrative + WeasyPrint PDF
    llm/          ModelRouter with credit-fallback + max_tokens caps
    gri/          46-indicator catalog loader with sector materiality weights
    tracking/     MLflow fail-safe wrappers
    exceptions/   Typed error hierarchy (Ingestion/Extraction/LLM/Scoring/Report)
  workers/        Celery tasks (7-stage pipeline, report generation)

frontend/react/   React 19 + TypeScript + Vite + TailwindCSS
data/             gri_indicators.json, uploads/, generated_reports/, test fixtures
tests/            498 unit tests (validator, confidence, indicators, scorer, builder)
scripts/          download_models.py, migrate_*.py, experiments/
```

---

## ESG Scoring Methodology (v1)

```
indicator_score = disclosure_quality × confidence_factor
pillar_score    = Σ(indicator_score × materiality_weight) / Σ(materiality_weight)
total_score     = 0.40·E + 0.35·S + 0.25·G
```

| Disclosure Tier | Score | Trigger |
|----------------|-------|---------|
| Missing / Rejected | 0.0 | No disclosure found |
| Ambiguous | 0.4 | Uncertain extraction |
| Qualitative Only | 0.6 | Text present, no numeric value |
| Quantitative, No Unit | 0.7 | Value without unit |
| Quantitative + Unit | 0.8 | Value + unit, no source citation |
| Fully Disclosed | 1.0 | Value + unit + source page + evidence |

Materiality weights are **data-driven** — stored per-indicator per-sector in `data/gri_indicators.json`. Adding a new sector is a JSON edit + one-line code change.

---

## Experiment-Driven Development

Every architectural decision in the ML pipeline was made through controlled experiments with documented results:

| Experiment | Method | Key Finding |
|-----------|--------|-------------|
| Chunking (A1/A2) | 5-strategy shootout + tuning | Sentence-window w=3 s=1 cap=1500: +62% ESG recall, 1.3% truncation |
| Embedding (B1/B2) | 5-model bilingual retrieval test | English-only evaluation would have picked the wrong model |
| Classification (C1–C4) | Bias audit → shootout → ensemble | 3-voter ensemble: +87% S-pillar recall, 0.967 precision |

All experiments are reproducible via scripts in `scripts/experiments/` with results in `scripts/experiments/results/`.

---

## License

This project is proprietary software. All rights reserved.