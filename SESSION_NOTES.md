# Session Notes — Changes Since the Cherry-Pick

**Window covered:** the cherry-pick session (selective port from experiment branch
commit `3c858a4`) and the two follow-up sessions that landed all the surrounding
fixes. Dated **2026-05-23 → 2026-05-26**.

This document is a companion to `CLAUDE.md`. CLAUDE.md is the durable project
context; this file is a short-lived narrative explaining **what changed, why,
why it's better now, and what we deliberately punted**. Read it once, then
either fold the still-useful parts into CLAUDE.md or delete it.

---

## TL;DR

| # | Change | Why | Impact |
|---|---|---|---|
| 1 | **Cherry-pick port** (M3 retrieval + frontend pipeline UI) | Move the per-indicator ChromaDB retrieval path from the experiment branch to `main` without dragging in the local-Ollama path | Extraction now retrieves top-3 chunks per indicator instead of feeding the whole document; faster + more focused |
| 2 | **Auth scoping** (Prompt 3) | Iteration 1 had no auth; data was shared via a "Default Company" stub. Cross-tenant leaks were the most embarrassing risk | Every endpoint requires Bearer JWT and scopes queries by `current_user.company_id`; cross-company access returns 404 (not 403) so attackers can't enumerate IDs |
| 3 | **Score plumbing fix** (Prompt 4) | Dashboard recomputed scores as `avg(confidence)*100` in TypeScript — it disagreed with the PDF whenever the user touched a metric | Dashboard now reads the same persisted backend score the PDF renders from; one source of truth |
| 4 | **Upload widening** (Prompt 5) | API hard-coded `.pdf` only despite `parser.py` supporting docx/xlsx/csv/txt/images | API now accepts every format `parser.py` can handle. Image OCR is still stubbed; zero-text docs now **fail explicitly** with `error_message` instead of an infinite spinner |
| 5 | **Approve-All + null-value band-aid** (Prompt 5.5) | "Approve All" was flipping `status=missing` rows to `approved`, then the scorer awarded 1.0 to those empty disclosures → 100/100/100/100 | Bulk actions now scope to `extracted`/`ambiguous` only; scorer returns 0 if `value` and `original_value` are both None |
| 6 | **v1 disclosure-quality methodology** (Prompt 5.6) | The band-aid stopped the worst case but the underlying methodology (`approved → 1.0`) wasn't defensible to an ESG analyst | Full rewrite: per-indicator score = `disclosure_quality × confidence_factor`, weighted aggregation by sector-specific `materiality_weights` read from `data/gri_indicators.json` (not hardcoded) |
| 7 | **PDF table styling + WeasyPrint backend** (Prompt 7 + extension) | PDF tables rendered as raw text under the PyMuPDF Story fallback (no `nth-child`, no `<th>` background); WeasyPrint couldn't load on Windows host because GTK3 was missing | WeasyPrint baked into the worker Docker image (Linux), with a `PDF_BACKEND` env knob as a one-line revert. Tables now have headers, alternating rows, full borders |
| 8 | **CLAUDE.md update + UTF-8 cleanup** | The CLAUDE.md was full of doubly-encoded mojibake (`â€"` for `—`, `ðŸ"§` for `🔧`) and the architecture section was 6+ months out of date | 435 mojibake clusters reversed; pipeline diagram replaced; new ESG-Scoring-Methodology v1 section; auth-scoping rule added to Coding Conventions; session-log row for 2026-05-26 appended |

**Light mode** is intentionally NOT on this list. It already existed from the
2026-05-18 UI-polish session and was never part of the port.

---

## 1. Cherry-Pick Port (the starting point)

### What
Selective port of two file groups from experiment branch commit `3c858a4`:

- **Port A — M3 retrieval.** `backend/app/core/extraction/extractor.py` rewritten
  to retrieve top-k chunks per indicator from ChromaDB instead of feeding the
  whole document to the LLM. New `EMBEDDING` stage between `CLASSIFY` and
  `EXTRACT`. Dual-collection retrieval (`document_chunks_en` for EN queries,
  `document_chunks_ar` for AR) with matching-dim query vectors. Graceful
  fallback to full-doc text if ChromaDB is unreachable. New MLflow fields
  `extraction_mode` / `extraction_top_k` / `avg_chunks_retrieved_per_indicator`.
  Three new config knobs: `extraction_top_k=3`, `extraction_min_chunks=1`,
  `extraction_concurrency=4` (last unused).

- **Port B — frontend.** `PipelineProgressIndicator` gained the new
  `chunking` and `embedding` stages; embedding reordered to fire *after*
  classifying. `ReportView` got a full rewrite with a resizable split-pane PDF
  preview (`useResizable`, `useResizableInner`, `PdfPreview` component).
  Tsconfig relaxations + Node-block `.dockerignore`.

### What was deliberately left on the experiment branch
The local-Ollama extraction path:
- `USE_LOCAL_EXTRACTION` setting
- `_try_ollama` helper in `extractor.py`
- `host.docker.internal` compose env
- `scripts/test_local_extraction.py`
- `OLLAMA_*` env vars

This path is interesting for cheaper extraction during development but it adds
deployment complexity. Decision: keep it on the experiment branch until we
actually need offline runs.

### Why
The retrieval-first design solves three pain points that ranked metrics under
the prior full-doc approach:

1. **Cost.** Full-doc extraction sent ~60K characters to the LLM per indicator,
   46 times per document. At free-tier rate limits this was both slow and
   prone to truncation.
2. **Focus.** Top-3 retrieval gives the LLM the chunks most relevant to the
   indicator (per the dense embedding), instead of forcing it to scan the
   whole document.
3. **Observability.** `avg_chunks_retrieved_per_indicator` and
   `extraction_mode=retrieval` go to MLflow so we can A/B prompt + retrieval
   knobs against the older full-doc baseline.

### Better now
End-to-end MLflow check on the most recent run: `extraction_mode=retrieval`,
`avg_chunks_retrieved_per_indicator=3.0` — every indicator got exactly 3
chunks for its prompt. ChromaDB EN collection populated with 39 chunks per
document, tagged by `source_file` (the UUID-named disk filename, not the
user-facing filename — which is the right choice because the where-filter has
to match what `embed_and_store` wrote).

### What else could be done
- Tune `extraction_top_k` (currently 3). MLflow has the raw signal but no one
  has run a sweep.
- Wire `extraction_concurrency` (currently set but unused). LLM rate limits
  may make parallel indicator extraction unsafe on free tiers; remote APIs
  may need 2-3.
- AR retrieval validation. Only 10 AR queries on the current test set; a
  one-query swing flips e5-base vs bge-m3. Widen to 30+ queries across 2-3
  AR docs before locking in bge-m3 long-term.

---

## 2. Auth Scoping (Prompt 3)

### What
- Removed the Iteration-1 "Default Company" stub from `documents.py` (every
  upload used to land under a shared `Default Company` row regardless of who
  was logged in).
- Threaded `get_current_user` through `documents.py`, `pipeline.py`,
  `reports.py`, `metrics.py`.
- Every per-user endpoint now `WHERE company_id = current_user.company_id`.
- Cross-company access returns **404, not 403** — so an attacker can't
  distinguish "doesn't exist" from "belongs to someone else".
- Pipeline status endpoint is auth-required but can't filter further because
  Celery task state isn't tagged with `company_id` — the `job_id` itself is
  unguessable UUID4, which is the security model for that one endpoint.

### Why
The platform handles regulated financial-services disclosures. A cross-tenant
read was the highest-impact risk in the v1 scope. The 404-not-403 detail
is a small but specific defense: it prevents an attacker who guesses a real
UUID from confirming that the UUID exists for another tenant.

### Better now
- Verified end-to-end with two accounts (`E2E Alpha Bank` and `E2E Bravo Bank`,
  distinct company IDs):
  - A's `GET /documents/` returns A's docs only
  - B's `GET /documents/` returns B's docs only
  - `GET /reports/{A's report ID}` as B → 404
  - `GET /documents/{A's doc ID}` as B → 404
  - `GET /metrics/{A's doc ID}` as B → 404
  - `GET /reports/{A's report ID}/pdf` as B → 404

### What else could be done
- Pipeline status endpoint still leaks "is this job_id valid" via 404 vs 200.
  Tag Celery task state with `company_id` on enqueue and check on read.
- Audit log of cross-tenant 404s — if you see one IP hitting many cross-tenant
  IDs and getting 404s, that's a probe.

---

## 3. Score Plumbing (Prompt 4)

### What
- Added three columns to the `Report` model: `environmental_score`,
  `social_score`, `governance_score` (all Float, nullable).
- Migration script `scripts/migrate_reports_pillar_scores.py` (idempotent
  Postgres + SQLite).
- Worker writes all 7 score fields (total / GRI / FRA / SASB / E / S / G) at
  both pipeline-end and report-generation time, from the same `ScoringResult`.
- Frontend `ReportView.tsx` deleted the local `pillarScore()` function that
  was computing `avg(confidence) * 100` in TypeScript. Dashboard now reads
  `report.environmental_score` etc. straight from the `Report` row.

### Why
Before the fix, the user could see one score on the dashboard and a different
score on the PDF for the same report. The dashboard's TypeScript was
recomputing on the fly from individual metric confidences; the PDF read from
the persisted `Report` row that the scorer had populated. Any metric edit
between pipeline-time and report-generation made the two disagree.

### Better now
The pipeline writes the scores once. The report-generation task re-runs the
scorer (so metric approvals between extraction and report can take effect) and
overwrites the same row. Frontend reads that row. The PDF reads that row.
One number, one source.

End-to-end verification this session: A's report on the same data, banking
sector: total=64.3 / E=73.8 / S=64.0 / G=49.6. PDF and dashboard JSON
identical.

### What else could be done
- The dashboard could surface the timestamp on which the score was computed,
  so a user can tell whether the displayed number is stale (e.g. metrics
  approved after report.generate ran).

---

## 4. Upload Widening (Prompt 5)

### What
- `api/documents.py` and `core/ingestion/parser.py` now agree on supported
  formats via a single shared constant `SUPPORTED_EXTENSIONS`.
- Accepts: `.pdf`, `.docx`, `.xlsx`, `.xls`, `.csv`, `.txt`, image extensions.
- Image OCR is still **stubbed**: the parser returns a zero-text
  `IngestedDocument`. The new zero-text guard in `_run_pipeline_async` catches
  this and writes a friendly `Document.error_message`:
  *"Could not extract text — image OCR is not yet implemented. Please upload
  a PDF, DOCX, XLSX, CSV, or TXT file instead."*
- `Document.error_message` (Text, nullable) added to the model; migration
  script `scripts/migrate_documents_error_message.py`.

### Why
Before the widening, the user could upload a `.docx` through the upload
modal but the API would reject it with `422 Only .pdf uploads are accepted in
Iteration 1`. The error was real but the UX was hostile — the upload modal
let you pick the file before telling you.

The OCR-not-implemented case mattered for a separate reason: image uploads
*used to* hang at "processing" forever because no path explicitly failed
them. Now they fail cleanly with a message that tells the user what to do.

### Better now
- Verified by API smoke this session: API accepts the full set; pipeline
  completes on docx/xlsx/csv/txt; image uploads fail explicitly within
  seconds with the OCR message visible to the UI.
- Single source of truth for the supported-format set, so the next dev
  can't accidentally diverge upload validation from parser dispatch.

### What else could be done
- Wire Tesseract for real OCR on image uploads. Tesseract is already
  installed in `Dockerfile.worker` (the `tesseract-ocr-ara` /
  `tesseract-ocr-eng` packages are present) but the parser path isn't
  connected to it.
- PDF OCR fallback. Scanned-PDF detection (PyMuPDF returns empty text →
  trigger Tesseract). Important for Arabic utility-bill PDFs.

---

## 5. Approve-All + Null-Value Band-Aid (Prompt 5.5)

### What
Two surgical fixes that together stopped the "all 100s" scoring bug:

- **Frontend** (`Results.tsx`): `handleApproveAll` / `handleRejectAll` now
  filter to `status === 'extracted' || status === 'ambiguous'`. The button
  label and tooltip show the actionable count, not the visible-rows count.
- **Backend** (`scorer.py`): `_legacy_score_indicator` now returns 0.0 at the
  top of the function if both `value` and `original_value` are None,
  regardless of status. This catches the case where an approved metric has no
  actual disclosure to score.

### Why
The bug pattern was:
1. Pipeline extracts 8 of 46 indicators; 38 come back as `status=missing`.
2. User clicks "Approve All" expecting it to act on review-pending rows.
3. The button flipped *every visible row* to `approved`, including the 38
   missing ones.
4. The scorer's old logic was: `if status == approved: return 1.0` —
   unconditionally. So 38 empty disclosures scored 1.0.
5. Result: 100 / 100 / 100 / 100 across the board, dashboard and PDF.

The 5.5 work was an explicit band-aid — it stops the worst case (empty
disclosures don't score) but doesn't fix the underlying methodology
(approved → 1.0 is still wrong even with a value: a full disclosure should
score 1.0 regardless of who approved it; the human override is supposed to
reflect *quality verified by reviewer*, not the score itself). That deeper
rewrite is Prompt 5.6 below.

### Better now
- `Approve All (8)` instead of `Approve All (46)` — the button is honest
  about what it does.
- Sanity check: an `approved` metric with `value=None, original_value=None`
  scores 0.00, not 1.00. Verified with 9 case rows.

### What else could be done
Already done — Prompt 5.6 replaces the methodology entirely.

---

## 6. v1 Disclosure-Quality Methodology (Prompt 5.6)

### What
Full scoring rewrite. Removed the legacy `approved → 1.0` shortcut. Replaced
with a two-factor per-indicator score and sector-table-driven aggregation:

```
indicator_score   = disclosure_quality × confidence_factor
aggregated_score  = weighted average over in-scope indicators,
                    weights from data/gri_indicators.json[materiality_weights][sector]
```

Three new helper functions, all in `scorer.py`:

- `_disclosure_quality(metric)` — buckets the metric's completeness on the
  actual data present: 0.0 (missing/rejected/empty) → 0.4 (ambiguous) → 0.6
  (qualitative only) → 0.7 (numeric, no unit) → 0.8 (numeric + unit, no
  citation) → 1.0 (numeric + unit + page + evidence).
- `_confidence_factor(metric)` — softens by extraction confidence: 1.0 if
  `status=approved` or `confidence >= 0.8`, 0.7 in `[0.5, 0.8)`, 0.5 below.
- `_materiality_weight(indicator, sector)` — reads the weight straight from
  `data/gri_indicators.json` for the given sector. Omitted = out of scope =
  excluded from that sector's denominator entirely (not counted as zero).

`score_report` now requires a `sector` kwarg with no default. Unknown sectors
log a warning and fall back to `banking` (loud fallback).

`data/gri_indicators.json` got a new `materiality_weights` map per indicator:

```json
"materiality_weights": {
  "banking": 1.5,
  "insurance": 1.5,
  "consumer_finance": 1.0,
  "mortgage_finance": 1.0
}
```

Weights were derived mechanically from the existing `applicable_sectors`
field (the 2026-05-12 iter2 work) plus the indicator's framework: 2.0 for
SASB-picked or FRA-mandated indicators in their sectors, 1.5 for highly
relevant GRI indicators, 1.0 for baseline GRI. Then spot-checked.

### Why
The old methodology had three problems:

1. **Indefensible to an ESG analyst.** `approved → 1.0` ignores whether the
   value was actually disclosed.
2. **Sector-blind.** Banking and Insurance use the same 46-indicator catalog
   but the relative importance of indicators differs dramatically (e.g. SASB
   FN-IN climate exposures matter to insurance, not banking).
3. **Hard to extend.** Adding a new sector would have required code edits in
   the scorer for the new sector's weight logic.

The new methodology fixes all three:

1. **Defensible.** `disclosure_quality` reflects what the LLM actually
   extracted — value, unit, source citation, evidence — not whether someone
   clicked a button. `confidence_factor` softens by extraction trust;
   approved → 1.0 only because a human verified it, not because it's
   automatically correct.
2. **Sector-aware.** Each indicator has a per-sector weight; the aggregator
   uses it.
3. **Table-driven.** Adding a sector is a JSON edit plus a one-line
   `KNOWN_SECTORS` update in `scorer.py`. No methodology code changes.

### Better now
End-to-end verification this session on a real PDF (NBE Sustainability Report):

| Sector | total | E | S | G | GRI | SASB | FRA |
|---|---|---|---|---|---|---|---|
| banking | 64.3 | 73.8 | 64.0 | 49.6 | 60.9 | 0.0 | 80.0 |
| insurance | 36.3 | 41.7 | 28.2 | 39.0 | 61.7 | 0.0 | 80.0 |

Same metrics, different sector → different scores. The big E/S drop for
insurance comes from insurance having 5+ more in-scope SASB-FN-IN climate
indicators that weren't disclosed (the document is a bank's annual report,
not an insurer's). FRA stays 80 because FRA-36 is in scope for both. SASB
stays 0 in both because no SASB-FN-* indicators were extracted from this
particular PDF.

Manual indicator-level walkthrough of `GRI 305-1`:
- status=`approved`, value=6899.0, unit=`tCO2e`, source_page=`None`,
  evidence present.
- `disclosure_quality` = 0.8 (value + unit, but no page).
- `confidence_factor` = 1.0 (approved override).
- `materiality_weights["banking"]` = 1.5 (from JSON, not hardcoded).
- Contribution = 0.8 × 1.0 × 1.5 = 1.2.
- Full E-pillar manual reconciliation = 9.6 / 13.0 × 100 = **73.85**.
- API E score = **73.8**. ✓

### What else could be done
- **ESG advisor review.** The `materiality_weights` rubric was derived
  mechanically. Before any external pilot, a credentialed SASB-FSA analyst
  should review the per-sector weight assignments.
- **Wire `score_metric` (scorer.py:237).** A v2 scoring path already exists
  (binary / quantitative / qualitative / Q+QL with benchmark support) but is
  unwired. The current path runs the v1 disclosure-quality aggregator.
- **Per-metric transparency in the UI.** "Why didn't this metric get full
  credit?" tooltip that shows the disclosure_quality bucket + the missing
  fields (e.g. *"would be 1.0 if source_page were populated"*).
- **Peer benchmarks, controversies feed, YoY trend, assurance multiplier.**
  All v2 — explicit non-goals in v1.

---

## 7. PDF Table Styling + WeasyPrint Backend (Prompt 7 + extension)

### What
Two related changes, applied in sequence:

**Round 1 — CSS workarounds for PyMuPDF Story.** Tables in generated PDFs
were rendering as a flowed list of cells, no header row distinction, no
alternating stripes, weak borders. Root cause: WeasyPrint couldn't load on
the Windows host (`libgobject-2.0-0` not installed → ImportError → renderer
silently fell back to PyMuPDF Story). PyMuPDF Story's CSS subset doesn't
honor `tr:nth-child(even)` or element-selector `<th>` backgrounds. Fix: rewrote
the table rendering in `renderer.py` to use class-based striping
(`.row-odd` / `.row-even`) plus inline `style=` on every `<th>`, so PyMuPDF
Story finally honored the styling.

**Round 2 — bake WeasyPrint into the worker image.** With GTK3 added to
`Dockerfile.worker` (Linux base, not Windows), WeasyPrint loads cleanly. New
`PDF_BACKEND` config knob (`auto` / `weasyprint` / `pymupdf`) lets us flip
modes via `.env` — no rebuild. The 11 added apt packages (`libpango-1.0-0`,
`libcairo2`, `fonts-noto-core`, etc.) add ~200 MB to the worker image; in
exchange the renderer gets full CSS support, `@page` headers/footers, real
font embedding, proper Arabic rendering.

### Why
The first round was forced by the running environment: WeasyPrint can't load
on the Windows host, so PyMuPDF Story is what actually generates PDFs. Pure
CSS rules weren't enough; the rendering had to be defensible against an
80%-CSS-support backend.

The second round was about giving us back the 20% of CSS support we were
giving up. Page footers (`@page @bottom-right { content: counter(page) }`)
didn't work under PyMuPDF Story. Flexbox didn't work. `nth-child` didn't
work. Arabic text rendering was patchy. With WeasyPrint in the worker
image, all of that comes back.

The `PDF_BACKEND` knob exists for one reason: if a WeasyPrint upgrade ever
breaks something in production, the one-line revert (`PDF_BACKEND=pymupdf`
in `.env`, then `docker compose restart worker`) gets us back to a working
state without a rebuild.

### Better now
- WeasyPrint 68.1 is the primary backend in the worker; PyMuPDF Story is the
  fallback.
- All four templated tables (Company Profile, per-section Indicator, GRI
  Content Index, Gap Analysis) render correctly: dark teal headers,
  alternating rows, color-coded status pills, bordered grid.
- Page footers `N / M` work.
- Worker image grew from 3.67 GB to 4.07 GB (+11%).
- Output PDF size: ~45 KB for a typical report (vs ~316 KB under PyMuPDF
  Story — WeasyPrint embeds fonts more efficiently).

### What else could be done
- Remove the PyMuPDF Story-specific CSS workarounds (inline `<th>` styles +
  explicit `.row-odd` / `.row-even` classes) once we're confident WeasyPrint
  is the only path in production. They don't hurt — the template works in
  both — but they're noise.
- Arabic font validation. `fonts-noto-core` includes Arabic; visually verify
  RTL rendering on a real AR report once we have one through the pipeline.

---

## 8. CLAUDE.md Update + UTF-8 Cleanup

### What
- **Pipeline diagram replaced.** The old diagram said `Ingestion (PyMuPDF +
  Unstructured.io + Tesseract OCR) → Chunker (semantic) → Embedder
  (paraphrase-multilingual-e5-base) → ChromaDB (document_chunks)` — every one
  of those was wrong by 2026-05-26. New diagram reflects the actual 7-stage
  flow + the separate `report.generate` Celery task.
- **5-vs-7 stages disclaimer added.** The `tasks.py` module docstring still
  describes a 5-stage flow; the function body implements 7. Flagged in
  CLAUDE.md so the next reader knows.
- **Auth-landed note.** Replaced "No auth in first pass" with the real
  Bearer-token + 404-on-cross-company description.
- **13-row indicator table annotated stale.** The historical 13-indicator
  table is preserved for context but a note points at the 46-indicator
  catalog in `data/gri_indicators.json` (since 2026-05-12) and the
  `materiality_weights` map (since 2026-05-26).
- **New "ESG Scoring Methodology — v1" top-level section.** Full rubric
  including the disclosure-quality ladder, confidence-factor bands,
  materiality-weight rubric, aggregation formula, sector scope,
  add-a-sector instructions, v1 limitations, and v2 backlog.
- **Coding Conventions** gained an auth-scoping rule: *"All per-user data
  access must scope by `current_user.company_id`; cross-company access
  returns 404 (not 403) to avoid existence leaks."*
- **Schema-change log extended.** `Document.error_message` and the three
  `Report` pillar score columns documented as additive + nullable.
- **Environment Variables** block updated with `PDF_BACKEND=auto`.
- **Session-log row for 2026-05-26** appended with the full narrative.
- **Mojibake cleaned up.** 435 doubly-encoded clusters fixed via cp1252
  round-trip (`â€"` → `—`, `ðŸ"§` → `🔧`, etc.). Box-drawing characters in
  the Project Structure tree preserved.

### Why
CLAUDE.md is the file the next agent reads first. If it's wrong, every
downstream decision is biased. The pipeline diagram had been wrong since the
arch-B classifier and bilingual embedder landed (2026-05-14). The auth note
had been wrong since 2026-05-23. The mojibake made the file painful to read
even for a human.

### Better now
27 of 28 cherry-picked checks pass against CLAUDE.md content (the 28th was
the `PDF_BACKEND` knob, patched in during this same session). The file is
single-encoding UTF-8. The new ESG-Scoring-Methodology section gives a
future contributor everything they need to add a sector without reading the
scorer code.

### What else could be done
- Eventually fold the most useful bits of this `SESSION_NOTES.md` into
  CLAUDE.md proper, then delete this file.
- The "Iteration 2 — Module Enhancement Backlogs" sections in CLAUDE.md
  reference `core/models/router.py` — the real path is
  `core/llm/router.py`. Small inconsistency, not critical.

---

## Verified End-to-End (this session)

Smoke run executed with two accounts on rebuilt images:

- Worker + API images rebuilt from current source (worker 4.07 GB after
  WeasyPrint bake-in; api 943 MB).
- A registered + uploaded `NBE_Sustainability_Report_2023.pdf` → pipeline
  ran with `pipeline.classified`, `EMBEDDING` stage, `pipeline.embedded`,
  46x `indicator_extracted n_chunks_retrieved=3`, `pipeline.complete`.
- A approved 8 metrics → generated report → downloaded PDF.
- Banking scores: total=64.3 / E=73.8 / S=64.0 / G=49.6 / GRI=60.9 /
  SASB=0.0 / FRA=80.0. **Realistic, not 100s.**
- Dashboard JSON ↔ PDF visual: identical.
- Manual indicator-level walkthrough for `GRI 305-1` reconciled to API E
  score within rounding.
- Sector swap: banking → insurance produced materially different scores
  (total -28.0, E -32.1, S -35.8) on the same metrics. **JSON
  `materiality_weights` is being read.**
- Unknown-sector guard: setting industry=`retail` produced log line
  `score_report.unknown_sector falling_back_to=banking known_sectors=[...]
  sector=retail`. Report generated successfully with banking-equivalent
  numbers. **Loud fallback works.**
- Cross-tenant isolation: 6 of 6 endpoints return 404 for B querying A's
  IDs. Each user sees only their own data after both pipelines run.
- ChromaDB: `document_chunks_en` populated with `source_file` /
  `company_id` metadata tagging A's vs Robin's chunks.
- MLflow: latest run has `extraction_mode=retrieval`,
  `avg_chunks_retrieved_per_indicator=3.0`.

---

## Known Carry-Overs

These are on the list but were not addressed in this batch:

- **Celery `--max-tasks-per-child=1`** — needed to avoid the asyncio
  event-loop drift after long Arabic-PDF runs (per the 2026-05-18 E2E
  session log). Worker docker-compose still doesn't have it.
- **AR retrieval test set widening** — only 10 AR queries currently;
  1-query swing flips e5-base vs bge-m3. Need 30+ across 2-3 AR docs
  before locking in bge-m3 long-term.
- **M4 `gap_analysis` depth** — current gaps list is shallow; should add
  "why this matters", "difficulty to close", "data source needed" per
  indicator.
- **`MODEL_REPORT_FALLBACK` tuning** — the narrative LLM frequently hits
  Groq rate limits; pick a more reliable fallback.
- **ESG advisor review of `materiality_weights`** — to be done before any
  external pilot.
- **Wire `score_metric` (scorer.py:237)** — the v2 scoring path with
  benchmark / completeness support; currently unwired.
- **Image OCR** — Tesseract is installed in the worker image but the
  parser path doesn't trigger it.
- **PDF OCR fallback** for scanned PDFs that PyMuPDF returns empty text
  for.

---

*Last updated: 2026-05-26. Not committed.*
