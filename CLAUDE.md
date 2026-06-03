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

| 2026-05-11 | M3 MLflow wiring + full app-tier dockerization. (1) Created `backend/app/core/tracking/mlflow_tracker.py` with fail-safe helpers wrapping every MLflow call in try/except + structlog warning so a dead tracking server can't break the pipeline. Wired into `extractor.py`: per-run logs document_id/report_id/company_id/source_file/model_name/n_chunks_processed/n_indicators_attempted as params; n_metrics_extracted/avg_confidence/n_high_confidence (>0.80)/n_low_confidence plus one `confidence.<GRI_code>` metric per indicator; `raw_llm_responses.json` artifact for prompt-debug. `_extract_single` now returns `(metric, raw_response)` — plumbing only, extraction logic untouched. (2) Dockerized api + worker + streamlit. Initial pass with one shared `requirements.txt` produced api 10.2GB, worker 10.3GB, build cache 19GB (42GB total). Refactored to split requirements (`requirements-base.txt` shared, `requirements-ml.txt` worker-only with `torch` from `pytorch.org/whl/cpu`, `requirements-ui.txt` streamlit-only) — required decoupling api from `app.workers.tasks` imports: switched `api/pipeline.py` + `api/reports.py` from `task_fn.delay(...)` to `celery_app.send_task(name, kwargs=...)` so the API container never pulls torch/transformers/mlflow/pymupdf into its import graph. Final sizes: api 917MB (−91%), worker 3.67GB (−64% via CPU torch wheel), streamlit uses `python:3.11-slim` inline with `pip install -r requirements-ui.txt` from a bind mount + named `pip_cache` volume. Compose adds service-name hostname overrides via `environment:` blocks so `.env` keeps localhost for host dev. Named volumes: `hf_cache` (HF weights persist across rebuilds) + `pip_cache`. `frontend/streamlit_app.py` reads `API_BASE_URL` from env. Verified end-to-end through containers twice (10GB and slim builds): ADCB upload → pipeline → MLflow logging at `http://mlflow:5000` → metric approval → PDF generation (250KB, `%PDF-1.7`). Final docker disk: 8.1GB (was 42GB at peak, ~34GB reclaimed). | Iteration 2 backlogs unchanged: M3 prompt quality + indicator-aware chunk selection (still 2-3/13), M4 gap_analysis fix, `MODEL_REPORT_FALLBACK`. Auth still deferred. Use the now-stable MLflow baseline to A/B prompt-quality changes per GRI indicator. |

| 2026-05-12 | Iteration 2 M3 - finance-sector GRI + SASB extraction expansion. (1) data/gri_indicators.json expanded 13 to 46 indicators using GRI Financial Services Sector Standards (Banking + Insurance Exposure Drafts, May 2025) and SASB FN-CF / FN-MF / FN-IN v2023-12+ (IFRS Foundation) as authoritative source - source files live under ESG_Catalyst_Wiki/raw/assets/Standards for metrics/. Each indicator now declares framework (GRI / SASB-FN-CF / SASB-FN-MF / SASB-FN-IN / FRA), metric_type (quantitative / monetary / rate / qualitative / activity), sector_standard_ref (e.g., XX.1.7 or FN-IN-410c.1), applicable_sectors, and expected_breakdown. All extraction prompts rewritten from the standards text - no more generic stubs. Coverage by framework: GRI 24, SASB-FN-CF 7, SASB-FN-MF 5, SASB-FN-IN 9, FRA 1. Coverage by sector: banking 25, insurance 30, consumer_finance 7, mortgage_finance 5. FN-CB and FN-IB SASB standards not in the wiki - only the existing FN-CB-230a.1 cross-reference retained; full FN-CB / FN-IB / FN-AC ingestion deferred until source docs are added. (2) Schema extended (CLAUDE.md previously flagged this as needing team discussion - additions are strictly nullable + backward-compatible so existing rows still load): 6 new fields on ExtractedMetricSchema / ExtractedMetricCreate / ExtractedMetric ORM - framework (MetricFramework enum), metric_type (MetricType enum), sector_standard_ref, currency, reporting_period_start/end, breakdown (JSON). New MetricFramework + MetricType enums in models/enums.py. (3) Project uses Base.metadata.create_all (no Alembic) - for fresh DBs the columns appear automatically. For existing Postgres DBs with rows to keep, added scripts/migrate_extracted_metrics_iter2.py - idempotent ALTER TABLE that checks information_schema before each ADD COLUMN; supports Postgres and SQLite. (4) core/gri/indicators.py gained get_indicators_by_framework(), get_indicators_for_sector(), get_indicators_by_metric_type() helpers - backward-compatible with original get_all_indicators() consumers. (5) core/extraction/prompts.py rewritten: system prompt expanded with currency, breakdown, reporting_period_start/end JSON keys; build_user_prompt() injects per-framework + per-metric-type guidance blocks so monetary metrics get currency-extraction instructions, qualitative metrics get summary-style instructions, activity metrics get scale-of-operations instructions. (6) core/extraction/validator.py gained normalize_currency() (ISO-4217 + Arabic/English aliases) and parse_monetary() (handles EGP 1.2 billion, USD 540 mn, $2500, Arabic-Indic digits, Arabic decimal U+066B / thousands U+066C separators). (7) core/extraction/extractor.py now coerces framework / metric_type enums per indicator, parses currency + breakdown from the LLM response, falls back to parse_monetary(original_value) if the LLM did not structure currency, parses reporting-period ISO dates, and propagates sector_standard_ref to the persisted metric. Smoke-tested all imports + helpers: 46 indicators load, 15 monetary metrics, prompt rendering verified, monetary parsing round-trips four MENA + US examples correctly. End-to-end LLM run on a real document NOT yet executed - that is next session work, ideally A/B against the existing MLflow baseline so confidence regression per indicator is visible. M4 gap_analysis fix and MODEL_REPORT_FALLBACK still open from prior sessions. Auth still deferred. | Run full pipeline against ADCB (or a fresh PDF) with the 46-indicator catalog; expect higher LLM cost and longer extraction; compare MLflow confidence-by-indicator vs the old 13-indicator baseline; tighten prompts where confidence < 0.6; run the Postgres migration script on dev DB; then M4 gap_analysis. |

| 2026-05-14 | Iteration 2 M2 — classifier replaced with arch-B ensemble (C1–C3 experiments). (1) C1 bias audit (`scripts/experiments/classification_baseline.py`, MLflow run `baseline-climatebert`): ClimateBERT alone passed 170/479 Beltone chunks at threshold 0.3 with avg E score 0.977 but avg S score only 0.803 — dropped textbook S/G content (whistleblowing, OHS, internal audit) at scores 0.04–0.09. (2) C2 shootout of 4 candidate single models (`classification_shootout.py`, `ground_truth_60.json` auto-seeded from pure-E/S/G keyword chunks): finbert-esg-9-categories won precision_overall=0.983 on the 60-chunk GT, n_passed=420, but min-pillar coverage only 21.4%. nbroad/ESG-BERT runner-up at 0.967 / 8.4% min-pillar. EnvironmentalBERT collapsed to E-only; FinBERT-sentiment correctly returned 0/0/0/0 as a no-ESG-signal control. Two definitional fixes upstream of the comparison: nbroad/ESG-BERT labels are snake_case (`Business_Model_Resilience`, …), and a chunk "passes" only when `sum(P over ESG-mapped labels) > threshold` (using argmax confidence let confident "Non-ESG" predictions slip through). (3) C3 multi-architecture (`classification_multi.py`): three architectures, decisions composed from cached scores, latency measured warmed on a 50-chunk sample. arch-A (ClimateBERT gate → finbert-esg pillar) and arch-C (finbert-sent → CB → finbert-esg) both collapsed to the C1 170-chunk set and precision crashed to 0.567 — the ClimateBERT gate already filters out most GT S/G content. arch-B (ClimateBERT + finbert-esg + nbroad/ESG-BERT, 2-of-3 ensemble) achieved n_passed=396, pillar E/S/G = 28.3/38.4/33.3, precision 0.967 — only 1.6pp below finbert-esg solo but min-pillar coverage +32% relative. Latency 992 ms/chunk warmed, ~1 GB RAM resident across the 3 models. (4) Integration: rewrote `backend/app/core/nlp/classifier.py` end-to-end. `ClassifiedChunk` gained `esg_relevant` (canonical, mirrors legacy `is_relevant`), `topic: Optional[str]` (finbert-esg category, else esgbert topic), `votes_for: int`, `ensemble: bool`; `pillar` is now `Optional[str]` (was the string "none"). Existing fields kept for back-compat — `tasks.py` and tests already pass `threshold=0.3, use_climate_model=True` and read only `.chunk`/`.is_relevant`, so no caller updates were required. `CONFIDENCE_THRESHOLD=0.80` in `.env` left alone — it gates M3 extraction confidence, not the M2 classifier (verified via grep across `extractor.py`, `confidence.py`, `scorer.py`, `gap_analysis.py`). Decision record at `ESG_Catalyst_Wiki/wiki/decisions/classification-architecture.md`. (5) Integration smoke: full M1→M2 on `en_beltone_report_summary.pdf` produced 479 chunks, 396 passed (E 28.28% / S 38.64% / G 33.08%), 738s total classify time on CPU — same numbers the C3 cached-decision pass predicted. Vote distribution: 12 chunks with 0 votes, 71 with 1, 273 with 2, 123 with 3. Saved to `scripts/experiments/results/integration_smoke.json`. MLflow experiment `m2-classification-experiments` contains baseline + 4 shootout + 3 arch runs. `chunker.py` and `embedder.py` NOT touched (user gate). | M2 threshold/ablation sweep (0.25 / 0.4 to see where pillar balance flips), Arabic-doc validation (`ar-adib-esg-report-2022_ar.pdf`), then return to Iteration 2 M3 — extraction A/B vs the new 46-indicator catalog using the arch-B-filtered chunks; M4 gap_analysis fix and MODEL_REPORT_FALLBACK still open. |

| 2026-05-14 | M2 B1 + B2 — embedding-model shootout and bilingual production integration. (B1) `scripts/experiments/embedding_comparison.py` benchmarks five candidates against a 20-query test set (10 EN against Beltone Sustainability Report 2024, 10 AR against ADIB ESG Report 2022) under standard RAG recall (signature substrings must collectively appear in the union of top-k retrieved chunks). Per-query coverage pre-flight rejects test cases the chunker can't possibly answer; force-online opt-in env var (`EMBEDDING_COMPARISON_FORCE_ONLINE=1`) — default is HF offline mode so cached weights work when DNS is flaky. Final per-model numbers logged to MLflow experiment `m2-embedding-experiments`: e5-base (EN R@5=0.80, AR R@5=0.80, 126s, 1.6GB); e5-large (0.70/0.80, 440s, 2.3GB); mpnet-multi (0.70/**0.30**, 63s, 0.7GB); bge-m3 (0.80/**0.90**, 696s, 2.6GB); arabertv2 (AR R@5=**0.00** — bare MLM encoder, no contrastive/retrieval fine-tuning so mean-pooled embeddings don't separate similar texts). Cross-language finding: mpnet collapses on Arabic, so the EN-only signal would have steered us wrong — bilingual evaluation is mandatory. (B2) `backend/app/core/nlp/embedder.py` rewritten for language-routed bilingual embedding: chunks auto-classified via a Unicode-range heuristic (≥10% chars in Arabic blocks ⇒ AR, else EN), routed to `settings.embedding_model_en` (default e5-base) or `settings.embedding_model_ar` (default bge-m3); lazy singleton per language plus `preload_models()` for worker startup. New public API `embed_chunks()` returns `EmbeddedChunk(chunk, embedding, language)`; `compute_embeddings` kept as back-compat alias. `embed_and_store()` now writes to per-language ChromaDB collections `document_chunks_en` (768d) and `document_chunks_ar` (1024d), both created with `metadata={"hnsw:space": "cosine"}` (L2 default would penalize on magnitude noise for normalized vectors). `embed_query(query, lang=…)` lets callers force a language or auto-detect from the query text — applies the E5 `query:` prefix automatically. Config split into `embedding_model_en` / `embedding_model_ar`, legacy `embedding_model` retained as EN-mirror alias. `.env.example` updated. `scripts/download_models.py` extended to pre-cache bge-m3 alongside e5-base. End-to-end ChromaDB retrieval verified via `scripts/experiments/embedder_chromadb_test.py` — runs the same 20-query B1 set but against live ChromaDB collections, reproduces the B1 numbers exactly (EN R@1=0.20 R@5=0.80; AR R@1=0.40 R@5=0.90; overall R@1=0.30 R@5=0.85), proving the cosine HNSW configuration matches in-memory dot-product results. ADIB document split 20 EN / 110 AR chunks across collections (bilingual document handled correctly). Note for fresh Postgres/Chroma envs: existing `document_chunks` collections created with L2 default must be deleted (one-time migration) — new collections are created on first write under the new names. | M3 prompt quality + indicator-aware chunk selection still open; M4 gap_analysis fix. Next M2 priority: enlarge the AR test set to 30+ queries across 2-3 AR docs before committing to bge-m3 long-term — a one-query swing on the current 10-query AR set flips the e5-base vs bge-m3 ranking. Also explore retrieval-finetuned Arabic SBERTs (e.g. `sentence-transformers/distiluse-base-multilingual-cased-v2`) as a lighter AR-side alternative to bge-m3's 2.6 GB footprint. |

| 2026-05-14 | M2 A1 + A2 — chunker strategy shootout, tuning, and config-driven integration. (A1) `scripts/experiments/chunking_comparison.py` benchmarks 5 strategies on `en_beltone_report_summary.pdf` (64 pages, 176 K chars). Per-strategy stats: n_chunks, token avg/min/max/std, % chunks <50 tok (noise), % chunks >512 tok (LLM truncation risk), table preservation against 3 hand-selected Beltone tables (stakeholder engagement p7–8, materiality matrix p9, ESG risks p26), and ClimateBERT-only pass rate. Results: `current` block_merge 479ch/46.8% short/5.4% long/1-of-3 tables intact; `sentence_window` (w=3 s=1) 717ch/2.8% short/6.4% long/**3-of-3 tables intact**; `semantic` (E5 cosine<0.7) degenerated to 2 chunks of ~30 K tokens — E5 normalises so aggressively that 0.7 is well under the typical inter-sentence cos-sim (~0.85+) for ESG narrative text, so the doc never gets cut; would need threshold ~0.9 or a different sentence model; `section_aware` 51.2% short (Beltone uses many ALL-CAPS single-word headers like `E`, `S`, `G`, `INTERNAL POLICIES:`); LangChain `RecursiveCharacterTextSplitter` 126ch but **56.4% >512 tokens** — too aggressive. Winner: `sentence_window`. Result file: `scripts/experiments/results/chunking_comparison.json`. (A2) `scripts/experiments/chunking_tuning.py` ran 3 sentence_window variations scored with the **new arch-B 3-voter ensemble classifier** (not ClimateBERT-only). New `max_chars` knob added — A1's winner had max_tokens=2068 because long run-on table rows aren't sentence-terminated. Variations: `sw_w3_s1_cap1500` 695ch / 642 esg / 3.9% short / **1.3% long** ✅; `sw_w5_s2_cap1500` 368ch / 351 esg / 1.9% long / fewer total signals; `sw_w3_s1_cap2000` 679ch / 627 esg / 3.2% long. Composite score `n_esg − 2·n_short − 5·n_long` picked `sw_w3_s1_cap1500`. (Integration) `backend/app/core/nlp/chunker.py` extended with a strategy dispatcher — existing logic preserved as private `_chunk_block_merge()`, new `_chunk_sentence_window()` added with per-page sentence splitting + section-header back-scan from the page's top so `Chunk.section_header` survives. Public `chunk_document(doc)` signature unchanged; reads `settings.chunk_strategy` (default `"sentence_window"`, alt `"block_merge"`) with optional `strategy=` kwarg for A/B testing. (Config) `backend/app/config.py` gained `chunk_strategy`, `chunk_window_sentences=3`, `chunk_stride_sentences=1`, `chunk_max_chars=1500`, plus legacy `chunk_size_chars`/`chunk_overlap_chars` for block_merge — flip the strategy via `CHUNK_STRATEGY=block_merge` env var, no code change. (Apples-to-apples comparison) `scripts/experiments/chunker_integration_check.py` runs both strategies through the **same** ensemble classifier: OLD `block_merge` 479ch → 396 ESG (E 112 / S 153 / G 131); NEW `sentence_window` 695ch → 642 ESG (E 159 / S 286 / G 197). Deltas: **+216 chunks (+45%), +246 ESG-relevant (+62%); pillar gains E +47 / S +133 / G +66** — S almost doubles because block_merge was fragmenting employee/HR/training sections (which the section_aware regex tagged as one-line headers and dropped). Path note: CLAUDE.md lists chunker under `core/pipeline/chunker.py` but the file actually lives at `core/nlp/chunker.py` — used the real path, did not move the file. MLflow logging in tuning script skipped due to Windows cp1252 codec issue when MLflow prints the 🏃 emoji from the run banner (same as A1); JSON in `scripts/experiments/results/` is the authoritative artifact. | Re-run M3 extraction A/B on the new sentence_window chunks (expect higher S/G recall, watch for confidence drift now that chunks are smaller-but-more-numerous); validate `chunk_strategy` switch through Celery worker (env var passes via docker-compose); fix MLflow Windows console encoding so `m2-chunking-experiments` runs land in the UI; widen A1 to ADIB-AR PDF to confirm the Arabic sentence splitter doesn't degrade (current regex is `[A-Z؀-ۿ]` start-of-next-sentence — verified on ASCII, untested at scale on AR). M4 gap_analysis and `MODEL_REPORT_FALLBACK` still open from earlier sessions. |

| 2026-05-18 | M2 B2 follow-up — ChromaDB web browser + retrieval re-verification. (1) Re-ran `scripts/experiments/embedder_chromadb_test.py` against live ChromaDB (cosine HNSW, per-language collections): EN e5-base R@1=0.20 R@5=0.80, AR bge-m3 R@1=0.40 R@5=0.90, overall R@1=0.30 R@5=0.85 — **exact match** to the B1 in-memory cosine numbers; top-hit cosine distances all <0.5, confirming the `hnsw:space=cosine` collection config behaves identically to in-memory dot-product. Two MLflow runs logged under `m2-embedding-experiments` (`chromadb-en-multilingual-e5-base`, `chromadb-ar-bge-m3`). `document_chunks_en` = 499 vectors (Beltone 479 + ADIB-EN 20), `document_chunks_ar` = 110 vectors. (2) `retrieval_test_set.json` is now multi-document: a `documents` map (`beltone`→EN PDF, `adib`→AR PDF) + per-query `doc_key`, so EN queries retrieve against Beltone chunks and AR against ADIB. (3) ChromaDB web UI: `fengzhichao/chromadb-admin` (and the whole flanker-fork family) only speaks the legacy `/api/v1/collections` path, which **ChromaDB 1.0 removed — returns HTTP 410 Gone** (`/api/v2` is now tenant-scoped). Replaced it with a single-file Streamlit browser `frontend/chromadb_admin.py` that uses the official `chromadb` Python client (handles v2 tenant scoping natively): lists collections, paginates documents+metadata with a `where=` filter, runs semantic queries via the production `embed_query` (language-routable), and a get-by-id raw view. Wired as docker-compose service `chromadb_admin`. First pass used `python:3.11-slim` (browse-only — no embedder, so the Semantic-query tab was disabled inside the container). Final wiring rebased the service on the prebuilt **`esg-catalyst-worker:latest`** image (torch + sentence-transformers + chromadb already baked) so the production language-routed embedder is importable and the Semantic-query tab works in-container; only `streamlit` is pip-installed on top (cached in `pip_cache`). The worker image predates the B2 embedder rewrite, so `./backend` is bind-mounted read-only over the image's stale code; `hf_cache` named volume is shared with the worker (e5-base/bge-m3 weights reused — no re-download); host port **8502**→8502, `CHROMA_HOST=chromadb`/`CHROMA_PORT=8000` on the compose network; `entrypoint` overridden (worker image's default CMD is celery). Verified end-to-end inside the container: EN query → e5-base dim 768, correct "238 new hires" chunk in top-5 (matches B2 en-04); AR query → bge-m3 dim 1024, valid cosine distances from `document_chunks_ar`. Browser issues queries client-side, so standalone (host) runs should point the connection at `localhost:8001`. `chromadb_admin.py` backend-path detection tries `<repo>/backend`, `<script_dir>/backend`, `/app/backend` so it works both standalone and in-container. (Docker Desktop dropped its named pipe several times mid-session — environmental, recovered each time.) `embedder.py` / `chunker.py` not touched in this follow-up. | Open M2 item stands: widen the AR test set to 30+ queries across 2–3 AR docs before committing to bge-m3 long-term (1-query swing flips e5-base vs bge-m3 on the current 10-query AR set). M3 prompt quality + M4 gap_analysis still open. Note: `chromadb_admin` pins `esg-catalyst-worker:latest` + bind-mounts `./backend` — if the worker image is later rebuilt with current code the bind-mount can be dropped. |

| 2026-05-18 | Diagnostic + fix session (post team-merge to `main`). **Diagnostic:** the running `esg_api`/`esg_worker` images were pre-merge (22-col `ExtractedMetric`) while host `main` = 44-col, and the physical Postgres `extracted_metrics` table was never migrated (only `migrate_extracted_metrics_iter2.py` existed; the scoring migration referenced in `models/metric.py` was missing) — so full-ORM reads (incl. `GET /api/v1/metrics/{id}`, the frontend's endpoint) 500 under current code; the stack only looked green because the stale image matched the stale table. Also: CLAUDE.md Project Structure listed `core/pipeline|report|models` which never existed (real: `core/{ingestion,nlp,extraction,scoring,reporting,llm}`); `score_metrics`->`score_report`, `build_report`->`build_report_sections`; `ExtractedMetricSchema` lacked `pillar`/`topic`; ChromaDB literal `document_chunks` absent **by design** (`document_chunks_en` 499/768d, `document_chunks_ar` 110/1024d, cosine); `CLIMATEBERT_MODEL` absent from `.env` (non-blocking — classifier hardcodes the id); M4 on report `d9ef8955` G=20.0/gaps=39 → prior G=0/gaps=0 bugs **fixed**. **Fixes (lead-approved):** authored `scripts/migrate_extracted_metrics_scoring.py` — 15 scoring cols + new `topic` col, idempotent PG+SQLite, also widens the under-sized `pillar` col to VARCHAR(20) and creates the native PG enum types SQLAlchemy `Enum()` casts to on INSERT (iter2's VARCHAR-only approach was silently *write*-broken for enum cols — reads worked, writes raised `type "metricframework" does not exist`). Added `pillar`+`topic` to the `ExtractedMetric` ORM + `ExtractedMetricSchema` + `ExtractedMetricCreate`; wired `extraction/extractor.py` (`_coerce_pillar` from `indicator["pillar"]`, `_derive_topic` from the GRI code prefix, mirrors `reporting.builder._topic_of`) into both construction sites. Ran iter2 then scoring migration on live Postgres (`extracted_metrics` now 45 cols = ORM, 267 existing rows preserved); verified full ORM `select(ExtractedMetric)` + `score_report` + an enum INSERT/SELECT round-trip (rolled back) on current code; rebuilt `esg-catalyst-api` + `esg-catalyst-worker` from current source and recreated the containers (both now 45-col); `GET /api/v1/metrics/{doc}` → **200** with `pillar`/`topic` in the payload. CLAUDE.md Project Structure + canonical schema block corrected above. | Frontend can be built against current `main`. New extractions populate `pillar`/`topic`; the 267 legacy rows have them `NULL` (optional one-off backfill). Pre-existing unrelated M3 bug noticed (NOT fixed — M3-owned): `extractor.py` references `MetricType.monetary`, not a member of `enums.MetricType` — only fires for `metric_type=="monetary"` indicators in a real LLM run. M4 `gap_analysis` depth + `MODEL_REPORT_FALLBACK` unchanged this session. |

| 2026-05-18 (cont.) | Fixed the two residuals flagged in the row above. (1) **M3 `MetricType` merge collision** — `extractor.py` referenced `MetricType.monetary` (unconditional attribute access in `_extract_single`, so extraction crashed for *every* indicator under current code) and `MetricType(raw)` raised ValueError for the monetary/rate/activity shapes gri_indicators.json declares. Root cause: `enums.MetricType` is the scoring-function selector (BINARY/QUANTITATIVE/QUALITATIVE/Q_PLUS_QL) owned by M4; the M3 iter2 author wrote against an enum that also had monetary/rate/activity. Fix keeps the enum untouched (polluting it would break `scorer.score_metric` dispatch + `gap_analysis` templates) and instead aligns the extractor with the shape→type map already in `gri_scorer.py` / `sasb_scorer.py`: new `_METRIC_TYPE_MAP` (monetary/rate/activity→QUANTITATIVE), `_coerce_metric_type` rewritten to use it, and the monetary special-case now keys off the raw indicator shape string (`raw_metric_type == "monetary"`) since the coerced type collapses to QUANTITATIVE. Verified in-container: all shapes map correctly, no `MetricType.monetary` ref remains, enum still 4 members. (2) **Legacy pillar/topic backfill** — authored idempotent `scripts/backfill_metric_pillar_topic.py` (pillar from the GRI indicator catalogue, topic via the same `_derive_topic` the extractor uses); ran on live Postgres: 267/267 rows now have `pillar`, 240 have `topic`. The 27 still-NULL `topic` rows are SASB-coded — `_derive_topic` matches `GRI \d+|FRA` only, so NULL there is the same result live extraction produces (consistent by design, not a gap). Re-run = no-op (idempotent). Rebuilt + recreated `esg-catalyst-api`/`esg-catalyst-worker` from current source; `/api/v1/metrics/{doc}` → 200 with pillar 46/46 populated. | M3 extraction is now runnable end-to-end under current code. M4 `gap_analysis` depth + `MODEL_REPORT_FALLBACK` behaviour still untouched (out of scope this session). |

| 2026-05-18 (F-series) | React frontend integration + API wiring. **Step 1 (smoke test):** Node.js not installed on host machine — build cannot run; all fixes applied via static code analysis. **Step 2 (API shape mismatches):** Found 5 issues: (a) `GET /api/v1/documents/` missing — added `list_documents` to `documents.py`; (b) `GET /api/v1/reports/` missing — added `list_reports` to `reports.py`; (c) `DocumentRecord` frontend used `document_id`/`uploaded_at` but API returns `id`/`created_at` — added `toRecord()` mapper in `documents.ts`; (d) `ReportDTO` incomplete — updated to match full `ReportResponse` schema incl. scores, frameworks, `job_state`; (e) No auth endpoints existed — added `backend/app/api/auth.py` with `POST /auth/login` + `POST /auth/register` (bcrypt + HS256 JWT, creates Company row on register), wired into `main.py`. API + TS both use snake_case throughout — no camelCase interceptor needed. **Step 3 (error states):** Added global `ErrorBoundary` class component at `frontend/react/src/components/ErrorBoundary.tsx` — catches unexpected React errors, shows error card with retry/home actions, prints stack in DEV; wired into `App.tsx`. All pages already had skeleton loaders + empty states from prior sessions. **Step 4 (RTL):** Fixed `Sidebar.tsx` — position flips `left-0`/`right-0` in RTL; active nav indicator moves to inner edge via dynamic style key; collapse chevron reverses direction; nav labels now use i18n keys. Fixed `AppShell.tsx` — `marginLeft`/`marginRight` swap based on `language === 'ar'` from UIStore. **Step 5 (build):** Cannot run — Node.js not in PATH (same as prior sessions). No TypeScript errors in static analysis. **Step 6:** CLAUDE.md updated. Frontend complete: React app at `frontend/react/`; pages built: Landing, Auth, Dashboard, Upload, Pipeline, Results, Report, Consultant; all wired to real API endpoints; RTL/AR support implemented. | Install Node.js (`winget install OpenJS.NodeJS`) before `npm run dev`/`npm run build`. Auth store now persists `role` (default `'consultant'`); Login/Register pass `res.role` to `setAuth`. `auth.py` uses `passlib[bcrypt]` + `python-jose[cryptography]` — both in `requirements-base.txt`. |
*Append a row here after every session.*

| 2026-05-18 (UI-polish) | React frontend UX pass + Admin console + infrastructure. **(1) PipelineProgress:** Added ChunkGrid (80-square filling visualiser during classifying step), useElapsed hook + TimeEstimate per long step (classifying 900s, extracting 900s), classifyError() that maps HTTP 402/credit-exhausted/both-models-failed to friendly error cards with abort vs retry. **(2) Results:** Bulk Approve All / Reject All buttons; fixed E/S/G pillar filter chips (boxShadow ring + full label); fixed generateReport navigation to pass ?doc=documentId. **(3) ReportView:** Fixed stuck-at-drafting-narratives bug — refetchInterval and isGenerating both checked 'complete' but backend enum is 'published'; fixed both; added elapsed timer + 300s timeout warning. **(4) Sidebar:** Logo wrapped in Link to '/' for home nav; Reports tab renamed 'Disclosures'; TOOLS_NAV role-gated (Consultant: consultant|admin, Admin: admin only); profile shows emailInitials() + emailHandle() not UUID. **(5) Auth store:** Added email field + emailHandle/emailInitials helpers; Login + Register pass email to setAuth. **(6) Router role guards:** RoleGuard component added — direct URL nav to /consultant or /admin without correct role redirects to /dashboard. **(7) FrameworkCoverageBar:** Redesigned with color-coded badge, gradient progress bar, segment dot grid. **(8) State persistence:** New usePipelineStore (Zustand + localStorage, key esg-pipeline-ctx) persists jobId/documentId/documentName/reportId; Upload saves on start; PipelineProgress + Results both restore from store when URL param absent. **(9) Admin page:** Full user management table with search, role filter chips, stats bar, inline RoleSelector dropdown with optimistic PATCH, self-protection, embedded psql promotion instructions. **(10) Admin API:** GET /api/v1/admin/users + PATCH /api/v1/admin/users/{id}/role on admin_router; JWT _admin_user dependency enforces admin-only; registered in main.py. **(11) Infrastructure:** Added adminer service (port 8080, Dracula theme) for browser DB browsing; added chromadb_browser service (lightweight streamlit+chromadb, port 8502) as permanent ChromaDB UI; Vite usePolling:true added so Windows FS events propagate into container for HMR; API + worker images rebuilt and restarted. | Celery --max-tasks-per-child=1 still not added (carry-over). chromadb_admin pip-installs streamlit on cold start (~60s) — consider baking into dedicated image. |

| 2026-05-18 (E2E) | Full end-to-end validation across 3 runs. **RUN 1 (ADCB English, 141 pages):** pipeline start 10:57, ingested 10:57 (27s), classified 11:17 (20min, 1305/1386 ESG-relevant), complete 11:32 (15min extraction), total ~35min. Metrics: 2/46 extracted (GRI 2-1 conf=0.90, SASB-FN-CF-230a.1 conf=1.00). Approved via PATCH, report generated, PDF download confirmed 468KB `%PDF-1.7` via `/api/v1/reports/{id}/pdf`. WARN: primary model 403 → fallback (gpt-oss-20b:free) activated. **RUN 2 (FAB Arabic, 182 pages):** pipeline start 11:32, ingested 11:33 (85s), classified 12:44 (71min on CPU — 2016 chunks × 3-model ensemble), complete 12:58 (14min extraction), total ~86min. Metrics: 3/46 (GRI 2-1 ambiguous, GRI-FS-XX.0.1-LENDING conf=0.90, GRI-FS-XX.0.2-AUM conf=1.00). WARN: classifier 0 ESG-relevant → pipeline used full-document fallback. WARN: fallback model used. **RUN 3 (Stress test — 3 concurrent):** 3 uploads + pipeline triggers submitted simultaneously (ADCB, test_esg, Beltone). All 3 accepted: unique job_ids/report_ids returned, all 3 document rows in Postgres confirmed, queue depth 6 with no errors, no race conditions, no 500s. **Blocking failures:** None. **Acceptable warnings:** fallback model on all LLM calls (OpenRouter primary 403); MLflow "unreachable" in some runs. **Known systemic issue (not blocking today, fix next session):** Celery solo worker process dies after classifying large Arabic PDFs (~2000 chunks, ~70min CPU); container stays running but the worker process exits, leaving subsequent queue items stuck at `queued` — requires `docker restart esg_worker` to resume. Root cause: likely OOM or asyncio event-loop state after hours of CPU inference. **Fix (next M6 session):** add `--max-tasks-per-child=1` to Celery startup in docker-compose so worker process recycles after each task. **Auth routes:** `/api/v1/auth/register` and `/api/v1/auth/login` are in codebase but NOT in running image (image predates auth commit) — requires image rebuild. | Rebuild `esg-catalyst-api` + `esg-catalyst-worker` images from current `main`; add `--max-tasks-per-child=1` to Celery in docker-compose; then proceed to F7/Iteration 3 planning. |

| 2026-05-26 | Selective port of experiment commit 3c858a4 onto main: took two groups (M3 per-indicator ChromaDB retrieval + frontend pipeline-stage updates + ReportView split-pane PDF preview), intentionally left local Ollama path on experiment (USE_LOCAL_EXTRACTION, _try_ollama, host.docker.internal compose env, scripts/test_local_extraction.py, OLLAMA_* env vars). **Port A — M3 retrieval:** extractor.py rewritten; new EMBEDDING stage between CLASSIFY and EXTRACT; dual-collection retrieval with matching-dim query vectors; ChromaDB-unreachable fallback to full-doc text; new MLflow fields (extraction_mode, extraction_top_k, avg_chunks_retrieved_per_indicator); source_file=ingested.source_file distinction (UUID disk filename for the where-filter, not the user-facing filename); three new config knobs (extraction_top_k=3, extraction_min_chunks=1, extraction_concurrency=4 — last unused). **Port B — frontend:** PipelineProgressIndicator gained chunking/embedding stages; embedding reordered after classifying; ReportView full rewrite with resizable split-pane PDF preview (useResizable, useResizableInner, PdfPreview); tsconfig relaxations; .dockerignore Node block. Light mode toggle was NOT part of this work — it already existed from the 2026-05-18 UI-polish session. **Fixes landed alongside the port.** *Auth (Prompt 3):* Iteration-1 "Default Company" stub removed; get_current_user threaded through documents/pipeline/reports/metrics; cross-company → 404. Legacy rows under Default Company are orphaned for new accounts — recommend `docker compose down -v` for a clean dev DB. *Score plumbing (Prompt 4):* dashboard was recomputing scores as avg(confidence)*100 in ReportView.tsx; now reads same persisted backend scores as PDF. *Upload widening (Prompt 5):* documents.py + parser.py now agree on supported formats — pdf/docx/xlsx/xls/csv/txt/images. Image OCR still stubbed; zero-text documents now fail explicitly. *Approve-All + null-value guard (Prompt 5.5):* Approve/Reject All scoped to extracted/ambiguous only; _legacy_score_indicator returns 0.0 when value AND original_value are both None, regardless of status. *v1 disclosure-quality methodology (Prompt 5.6):* full scoring rewrite. Per-indicator score = disclosure_quality × confidence_factor; weighted aggregation by sector-specific materiality. **Critical design decision:** materiality_weights live in data/gri_indicators.json per indicator per sector, NOT hardcoded in scorer.py. Adding a new sector is a JSON edit + a one-line KNOWN_SECTORS update; no methodology code changes needed. Out-of-scope indicators (omitted from a sector's weight map) are excluded from that sector's denominator entirely — not counted as zero. v1 sectors: banking, insurance, consumer_finance, mortgage_finance. Unknown sectors log a warning and fall back to banking (loud fallback). See the new "ESG Scoring Methodology — v1" section above for the full rubric. *PDF tables (Prompt 7):* WeasyPrint CSS now styles tables with borders, padding, alternating rows. **Process notes.** Manual user testing surfaced the "all 100s" scoring bug — root cause was status→1.0 in _legacy_score_indicator combined with bulk-approve flipping missing metrics. The 5.5 band-aid stopped the most embarrassing case; 5.6 redesigned the methodology to be defensible to an ESG analyst. *Why sector-table over hardcoded weights:* original 5.6 sketch had banking-specific GRI prefix lists in code, which would have silently mis-scored any future sector. The sector-table-driven design isolates the methodology from the sector taxonomy. Per-indicator materiality JSON entries were derived mechanically from the existing applicable_sectors field (the 2026-05-12 iter2 work) plus the framework, then spot-checked. **What was NOT done (deliberately):** score_metric (scorer.py:237) still unwired — its own multi-day rewrite; per-metric disclosure-quality transparency in UI deferred to v2; peer benchmarks, controversies, YoY trend, assurance verification — all v2; image OCR still stubbed; ESG-advisor review of materiality_weights values — to be done before external pilot. **Verified end-to-end:** clean DB reset, two-account isolation, all upload formats tested, MLflow extraction_mode=retrieval confirmed, ChromaDB per-account, scoring no longer 100s, sector-swap test confirmed score shifts when company.industry changes (banking → insurance produced materially different SASB scores on the same metrics), unknown-sector guard fires fallback warning correctly. | Pending from prior sessions: Celery --max-tasks-per-child=1, AR retrieval set widening, M4 gap_analysis depth, MODEL_REPORT_FALLBACK tuning. New: ESG advisor review of materiality_weights before any external pilot; wire score_metric (v2 scoring path) in a future session. |

| 2026-06-02/03 | **Big session — parallel refactor + full UI/UX overhaul + dockerized live-run + live-testing fixes. All on `test-opus`; `main` never touched (stays at a4f4689).** **(1) Parallel refactor** via 5 worktree-isolated subagents (pipeline core / API / config / error-handling / tests), reconciled centrally: new `core/exceptions.py` hierarchy, shared `api/deps.py`, typed `Settings` with validators, ~406 new unit tests. Fixed **4 missing `encoding="utf-8"` JSON reads** (indicators / gri_scorer / materiality / sasb_scorer) that crash on a Windows host, the `pyproject` `testpaths` (was `backend/tests`, a non-existent dir), and wired FastAPI exception handlers. **498 backend tests pass.** Docs: `REFACTOR_REPORT.md` + 5 `REFACTOR_*.md`. **(2) Parallel UI/UX overhaul** via 5 worktree-isolated subagents (design tokens + 7 primitives / shell-nav-RTL / flow pages / account pages / i18n + audit): fixed the `dir`/`lang` RTL wiring (no more FOUC), added a mobile drawer, full en/ar i18n parity, a11y roles. **`tsc --noEmit` + `vite build` both green.** Docs: `UI_REPORT.md` + 5 `UI_*.md` (+ `UI_audit.md`). Two agents hit transient 529s on their summary message only; work was intact (proven by the build). **(3) Dockerized live run** — brought up the whole stack (postgres / redis / chromadb / mlflow / api / worker / frontend / adminer / streamlit); verified `/health`, every `/api/v1` route, the Vite→API proxy, worker `celery ready`, and auth register+login. **(4) Live-testing fixes:** **E/S/G filter** — `workers/tasks.py:316` hand-built the ORM row and silently dropped 9 fields the extractor set (pillar / topic / framework / metric_type / currency / sector_standard_ref / reporting_period_start+end / breakdown), so `pillar` was NULL and the review-page filter matched nothing; fixed the persist + backfilled 552 existing rows (E 192 / S 120 / G 240). **UTF-8 display** — API JSON lacked `charset=utf-8`, so a Windows browser mis-decoded clean em-dashes (`—`) as mojibake; data verified clean via raw hex `e28094` (not corruption), fixed with a `UTF8JSONResponse` default. **Results bottom bar** was `fixed inset-x-0` + hardcoded navy (clipped by the sidebar, dark in light mode) → `sticky` + theme token. **Metric Source** now shows the human filename, not the internal `source_file` UUID. **Humanized IDs** — report_id → "Source Document: {filename}", role `company_admin` → "Company Admin", pipeline job UUID → filename + short ref — via new `frontend/react/src/lib/format.ts`. Restored the **fail-safe broad `except`** in `table_extractor` + `mlflow_tracker` (code-review findings). **(5) Dockerization** — rebuilt `esg-catalyst-api` / `-worker` / `-frontend` images from final source; all containers healthy. | **OpenRouter 402** — account is low on credits so primary `claude-sonnet-4.5` 402s and falls back to free Mistral-7B (lower quality); top up at openrouter.ai/credits or set a free primary in `.env`. **Pipeline speed** — the 3-model arch-B classifier on CPU is the bottleneck (~1s/chunk); wire GPU or drop to 1 model (config-driven). **M4 bugs (flagged, not fixed)** — `gap_analysis` keys on `materiality_score` (field is `materiality_weights`) so every gap scores priority=medium; `compute_tcfd_score` references absent `tcfd_pillar`. **Cleanup** — fold Dashboard/Admin `timeAgo` into `lib/format`. Pushed to origin/test-opus. |

| 2026-06-03 (follow-up) | Fixed the four correctness bugs flagged in `REFACTOR_REPORT.md` §5. **M4 `gap_analysis`** — gap priority now derives from `materiality_weights` (max across sectors, 0.5–2.0 rubric: ≥1.5 high / ≥1.0 medium / else low) instead of the non-existent `materiality_score` key (every gap had defaulted to medium). **M4 `tcfd_scorer`** — `compute_tcfd_score` infers each metric's TCFD pillar from its GRI/FRA code via new `_tcfd_pillar_for_metric()` (emissions/energy → Metrics & Targets, governance → Governance); no `ExtractedMetric` schema change; dead `m.tcfd_pillar` reference removed. **M3 `extractor`** — re-raises `LLMUnavailableError` instead of swallowing it per-indicator, so a credit-exhausted run marks the document failed via the task handler instead of silently completing with 0 metrics (makes the error hierarchy effective end-to-end). **Deprecation** — `datetime.utcnow()` → `datetime.now(timezone.utc)` in `fra_compliance.py` + `scorer.py`. Note: `--max-tasks-per-child=1` was already present in `Dockerfile.worker`. 498 tests still pass; api + worker images rebuilt + pushed. | Tidy-ups only remain: move 3 stray test scripts to `scripts/`, wire `extraction_concurrency` or drop it, decompose `scorer.py`/`extractor.py`, and wire `score_metric` (v2 scoring path). |

---

## Architecture

### Sequential Pipeline (current state — 7 worker stages + a separate report task)
```
Upload → Ingestion (PDF / DOCX / XLSX / CSV / TXT / images-stubbed)
       → Chunker (sentence_window, max 1500 chars)
       → Classifier (arch-B 3-voter ensemble: ClimateBERT + finbert-esg + nbroad/ESG-BERT)
       → Embedder (per-language: e5-base EN / bge-m3 AR →
                   ChromaDB document_chunks_en / document_chunks_ar)
       → Extractor (per-indicator retrieval, top-k=3 from both language collections,
                    where=source_file)
       → Scorer (v1 disclosure-quality methodology; sector-table-driven materiality)
       → Persist
       ↦ (separate Celery task report.generate, triggered after metric approval)
              Report Builder → Narrative → PDF Renderer (WeasyPrint primary,
                                                         PyMuPDF Story fallback)
```

> **Note — 5 vs 7 stages.** `backend/app/workers/tasks.py`'s module docstring
> still describes the older 5-stage pipeline (ingest → chunk → classify →
> extract → score). The actual implementation runs **7 stages**: ingest →
> chunk → classify → **embed** → extract → score → **persist**. The embed
> stage was added by the 2026-05-26 retrieval port; persist was always there
> but was not called out. The function body matches the 7-stage flow — only
> the docstring is behind.

> **Report generation is a separate Celery task.** `report.generate` is
> queued by `POST /api/v1/reports/generate` after at least one metric is
> approved. It reads metrics from Postgres, re-runs `score_report` (so the
> dashboard and PDF stay in sync), builds sections, calls the narrative LLM,
> and renders the PDF. It does NOT re-run extraction.

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
**Auth landed 2026-05-23.** All endpoints require a Bearer token; data is
scoped to `current_user.company_id`. Cross-company access returns 404 (not
403) to avoid existence leaks. Routes call the pipeline via Celery tasks
only — never import core modules directly in routes.

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
│       ├── core/                    ← ACTUAL layout (the old pipeline/ report/
│       │   │                           models/ paths NEVER existed in code;
│       │   │                           corrected 2026-05-18 — see session log)
│       │   ├── ingestion/           ← M1: parser.py (ingest_document),
│       │   │                           pdf_parser.py, docx_parser.py, ocr.py,
│       │   │                           table_extractor.py
│       │   ├── nlp/                  ← M1/M2: chunker.py (chunk_document),
│       │   │                           embedder.py (embed_chunks),
│       │   │                           classifier.py (classify_chunks)
│       │   ├── extraction/           ← M3: extractor.py (extract_metrics),
│       │   │                           prompts.py, validator.py, confidence.py
│       │   ├── scoring/              ← M4: scorer.py (score_report /
│       │   │                           score_document — NOT score_metrics),
│       │   │                           gap_analysis.py, gri_scorer.py,
│       │   │                           sasb_scorer.py, fra_compliance.py,
│       │   │                           materiality.py, tcfd_scorer.py
│       │   ├── reporting/            ← M5: builder.py (build_report_sections
│       │   │                           — NOT build_report), narrative.py
│       │   │                           (generate_narratives), renderer.py
│       │   │                           (render_pdf)
│       │   ├── llm/
│       │   │   └── router.py        ✅ ModelRouter (free-tier fallback live)
│       │   ├── gri/
│       │   │   └── indicators.py    ✅ get_all_indicators (46 indicators)
│       │   ├── tracking/
│       │   │   └── mlflow_tracker.py ✅ fail-safe MLflow wrappers
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
    pillar: Optional[PillarType]     # "E"|"S"|"G" — team-approved 2026-05-18
    topic: Optional[str]             # GRI/FRA topic e.g. "GRI 305" — team-approved 2026-05-18
    created_at: datetime
    updated_at: datetime
```

> **Schema-change log.** 2026-05-18: `pillar` + `topic` added to
> `ExtractedMetricSchema`/`ExtractedMetricCreate` and the `ExtractedMetric` ORM
> (lead-approved during the diagnostic session). Strictly additive + nullable;
> legacy rows read these as `None`. The extractor now back-fills them from the
> GRI indicator (`pillar`) and the GRI code prefix (`topic`, mirrors
> `reporting.builder._topic_of`). Run **both** migration scripts on existing DBs:
> `migrate_extracted_metrics_iter2.py` then `migrate_extracted_metrics_scoring.py`
> (the latter also creates the native PG enum types SQLAlchemy casts to).
>
> **2026-05-23/26 — adjacent additive fields on neighboring schemas (not
> ExtractedMetric).** `Document.error_message` (Text, nullable) added so the
> pipeline can surface "OCR not implemented" and similar fail-fast reasons to
> the UI instead of leaving documents in an infinite spinner — see
> `scripts/migrate_documents_error_message.py`. `Report` gained three pillar
> score columns (`environmental_score`, `social_score`, `governance_score`),
> all Float + nullable, written by both the pipeline and report-generation
> tasks so the dashboard reads the same persisted numbers the PDF renders
> from — see `scripts/migrate_reports_pillar_scores.py`. Both additive and
> nullable; no read-side breakage on legacy rows.

---

## GRI Indicators in Scope (Banking Sector — v1)

> **Stale, kept for historical context.** The active catalog is **46
> indicators** in `data/gri_indicators.json` since the 2026-05-12 expansion
> (GRI Financial Services + SASB FN-CF / FN-MF / FN-IN + FRA). The catalog
> also carries a `materiality_weights` map per indicator per sector since
> 2026-05-26, which the scorer reads at aggregation time — see
> *ESG Scoring Methodology — v1* below.

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

## ESG Scoring Methodology — v1

### v1 stance
Disclosure-quality only, not performance scoring. v1 measures how completely
a company disclosed each in-scope indicator. It does **NOT** measure whether
the reported values are good or bad, whether they improved year-over-year,
how they compare to peers, or whether they were independently assured.

### Per-indicator formula
```
indicator_score = disclosure_quality × confidence_factor
```
At aggregation time, multiply by `materiality_weight` (sector-specific) for
the weighted average.

### disclosure_quality (the actual disclosure shape)
| Tier | Score | Trigger |
|---|---|---|
| Missing / rejected | 0.0 | `status=missing`, `status=rejected`, or both `value` and `original_value` are None |
| Ambiguous | 0.4 | `status=ambiguous` |
| Qualitative only | 0.6 | `original_value` present but `value` is None |
| Quantitative, no unit | 0.7 | `value` present, `unit` missing |
| Quantitative + unit, no citation | 0.8 | `value` + `unit` present, but `source_page` or `evidence_chunk` missing |
| Fully disclosed | 1.0 | `value` + `unit` + `source_page` + `evidence_chunk` all present |

### confidence_factor (LLM extraction uncertainty)
| Score | Trigger |
|---|---|
| 1.0 | `status=approved` (consultant override — trust the human) |
| 1.0 | `confidence >= 0.8` |
| 0.7 | `0.5 <= confidence < 0.8` |
| 0.5 | `confidence < 0.5` |

### materiality_weight (sector-table driven, NOT hardcoded)
Weights live in `data/gri_indicators.json` per indicator under
`"materiality_weights": { "<sector>": <float> }`. The scorer reads them; no
sector logic in code. Rubric for the weight values:

| Weight | Meaning |
|---|---|
| 2.0 | Material — SASB picked this topic for this industry, OR regulator (FRA) mandates it |
| 1.5 | Highly relevant — affects sector risk profile (e.g. emissions for a bank's lending book) |
| 1.0 | Standard disclosure expected at baseline |
| 0.5 | Tangentially relevant — scorable but de-emphasized |
| (omitted) | Not in scope — excluded from this sector's denominator entirely |

### Aggregation
Pillar / framework scores are weighted averages across in-scope indicators
only (omitted = excluded, **NOT counted as zero**). Composite
`total_score = 0.40·E + 0.35·S + 0.25·G`.

### v1 sector scope
`banking`, `insurance`, `consumer_finance`, `mortgage_finance`. These are the
only sectors the 46-indicator catalog covers. The `KNOWN_SECTORS` guard in
`scorer.py` logs a warning and falls back to `banking` for any unknown
sector — loud-fallback rather than silent-wrong-numbers.

### Adding a sector
1. Edit `data/gri_indicators.json` — add the sector to `materiality_weights`
   on every relevant indicator (omit indicators that don't apply to it).
2. Add the sector string to `KNOWN_SECTORS` in `scorer.py`.
3. That's it. No methodology code changes.

### Explicit v1 limitations
- No peer benchmarking (no proprietary dataset).
- No controversies / incidents feed.
- No YoY trend on multi-year uploads.
- No third-party assurance verification multiplier.
- Materiality weights are static; not company-size or geography aware.
- Confidence factor uses LLM extraction confidence as a proxy for disclosure
  clarity — a noisy signal.

### v2 backlog
- Wire `score_metric` (scorer.py:237) into the pipeline path. It already
  exists but is unwired; the current legacy aggregator is what runs.
- Add per-metric disclosure-quality transparency to the UI ("Why didn't this
  get full credit?" tooltip).
- Ingest a peer benchmark dataset (TBD — needs an ESG analyst on the team).
- Add a controversies feed.
- YoY trend on multi-year uploads.
- Have an ESG advisor with SASB-FSA credential review the
  `materiality_weights` values before any external pilot.

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

# M5 PDF backend. auto = WeasyPrint primary, PyMuPDF Story fallback.
# Set to "pymupdf" as a one-line revert if WeasyPrint regresses; set to
# "weasyprint" to fail loudly instead of silently falling back.
PDF_BACKEND=auto
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
- All per-user data access must scope by `current_user.company_id`;
  cross-company access returns 404 (not 403) to avoid existence leaks.

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
