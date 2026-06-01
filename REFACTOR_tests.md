# REFACTOR_tests.md — Agent E Test Coverage Report

## 1. New Test Files Added

All new files live in `tests/` alongside the existing `tests/test_scoring.py` and
`tests/test_placeholder.py`.  The same `sys.path.insert` import pattern from
`test_scoring.py` is used in every new file.

### `tests/test_validator.py`
Covers `backend/app/core/extraction/validator.py` — pure-function, no LLM, no DB.

| Class | What it tests | Functions |
|---|---|---|
| `TestNormalizeCurrency` | ISO-4217 pass-through; Arabic/English/MENA aliases; substring matching; None/empty → None; unknown → None | 23 |
| `TestParseMonetaryStandard` | EGP/USD/EUR/GBP magnitude words (k/m/mn/million/b/bn/billion/trillion); sign; plain number; currency-suffix; None/empty/non-string | 15 |
| `TestParseMonetaryArabic` | Arabic-Indic digits (٠-٩); Arabic decimal U+066B (٫); Arabic thousands U+066C (٬); combination with magnitude word; EGP prefix | 5 |
| `TestNormalizeEnergy` | All known energy units → GJ; unknown → None | 9 |
| `TestNormalizeWater` | Known water units → m3; unknown → None | 7 |
| `TestSafeFloat` / `TestSafeInt` | None, valid, invalid string | 8 |
| `TestClamp` | below lo, above hi, within, at boundary | 4 |

**Total: ~71 test functions**

---

### `tests/test_confidence.py`
Covers `backend/app/core/extraction/confidence.py` — pure-function.

| Class | What it tests | Functions |
|---|---|---|
| `TestAdjustConfidenceBaseline` | No flags returns base unchanged | 3 |
| `TestAdjustConfidenceIndividualFlags` | Each of 5 penalty flags individually at base=1.0 | 5 |
| `TestAdjustConfidenceCombined` | OCR+approximate combined; all-flags combined; combined never exceeds base | 3 |
| `TestAdjustConfidenceClamping` | Never < 0; base > 1.0 clamped to 1.0 | 2 |
| `TestHasApproximateLanguage` | 11 positive cases (parametrized); 4 negative; empty string; case-insensitive | 18 |

**Total: ~31 test functions**

---

### `tests/test_indicators.py`
Covers `backend/app/core/gri/indicators.py` — reads `data/gri_indicators.json`; no LLM, no DB, no torch.

| Class | What it tests | Notes |
|---|---|---|
| `TestCatalogLoading` | Exactly 46 indicators; returns list of dicts; lru_cache (same object returned twice) | 3 |
| `TestMandatoryFields` | Parametrized over all 46: mandatory fields present, pillar valid, code non-empty, prompt non-empty | 46×4 = 184 |
| `TestGetIndicator` | Known code; known FRA code; unknown → KeyError; case-sensitive | 4 |
| `TestGetIndicatorCodes` | 46 codes; sorted; no duplicates; GRI 2-1 present; FRA-36 present | 5 |
| `TestGetIndicatorsByPillar` | All 3 pillars non-empty; each pillar contains only its pillar; union equals all; unknown → empty | 7 |
| `TestGetIndicatorsByFramework` | GRI ≥24; SASB-FN-CF ≥7; SASB-FN-MF ≥5; SASB-FN-IN ≥9; FRA ≥1; membership correct; unknown → empty | 7 |
| `TestGetIndicatorsForSector` | All 4 known sectors non-empty; banking/insurance count in range; membership respected; unknown sector returns universal indicators | 6 |
| `TestGetIndicatorsByMetricType` | quantitative/qualitative/monetary; monetary ≥10; membership correct; unknown → empty | 4 |
| `TestGetExtractionPrompt` | Returns string for known code; KeyError for unknown | 2 |

**Total: ~222 test functions** (most are parametrized per-indicator)

---

### `tests/test_v1_scorer.py`
Covers the v1 disclosure-quality methodology in `backend/app/core/scoring/scorer.py`.
No DB, no LLM, no torch.  Uses `SimpleNamespace` metric stubs.

| Class | What it tests |
|---|---|
| `TestKnownSectors` | `KNOWN_SECTORS` contains expected values; is a frozenset |
| `TestCompositeWeightConstants` | `_COMP_E + _COMP_S + _COMP_G == 1.0`; exact values 0.40/0.35/0.25 |
| `TestDisclosureQuality` | All 6 CLAUDE.md disclosure tiers via `_disclosure_quality`: None→0.0, missing/rejected→0.0, no-value-no-original→0.0, ambiguous→0.4, qualitative-only→0.6, quant-no-unit→0.7, quant+unit-no-citation→0.8, blank-evidence→0.8, fully-disclosed→1.0 |
| `TestConfidenceFactor` | All 4 confidence bands via `_confidence_factor`: None→0.5, approved→1.0, conf≥0.8→1.0, 0.5≤conf<0.8→0.7, conf<0.5→0.5 |
| `TestPerIndicatorScore` | `_per_indicator_score` = product of quality×confidence |
| `TestScoreReportUnknownSector` | Unknown sector doesn't raise; produces identical scores to banking |
| `TestScoreReportComposite` | Returns `ScoringResult` with all expected attributes; empty metrics→total=0; composite≈0.40·E+0.35·S+0.25·G; all scores 0–100; indicators_total ≥ 20 for banking; all 4 known sectors succeed (parametrized) |
| `TestScoreReportCoverage` | Zero metrics → coverage 0%; adding disclosed metric raises `indicators_found`; coverage_pct 0–100 |
| `TestBenchmarkTier` | Zero score→"Laggard"; tier value in known set |
| `TestScoreReportIndicatorFilter` | `indicator_codes` filter reduces `indicators_total` |

**Total: ~47 test functions**

---

### `tests/test_builder.py`
Covers `backend/app/core/reporting/builder.py` — no LLM, no DB, no torch.
Loads `data/gri_indicators.json` indirectly via `get_all_indicators()`.

| Class | What it tests |
|---|---|
| `TestTopicOf` | 12 parametrized GRI codes → correct topic prefix; unknown → "Other"; empty → "Other" |
| `TestBuildReportSectionsBasic` | Returns `ReportBundle`; company + score pass-through; sections is list |
| `TestBuildReportSectionsSingleMetric` | E/S/G pillar assignments; section title non-empty; metric in correct section metrics list |
| `TestBuildReportSectionsOrdering` | GRI 302 before GRI 405; FRA after GRI topics |
| `TestBuildReportSectionsMultiMetric` | Two 305-* metrics land in one GRI 305 section |
| `TestGriContentIndex` | All 46 indicators appear; dict has code/name/page/status; absent→"not reported"; present metric→actual status; codes match catalog |
| `TestBuilderConstants` | Every topic in `_TOPIC_ORDER` has a pillar entry; pillar values are E/S/G |

**Total: ~35 test functions**

---

## Summary counts

| File | Test functions (approx.) |
|---|---|
| `tests/test_validator.py` | 71 |
| `tests/test_confidence.py` | 31 |
| `tests/test_indicators.py` | 222 |
| `tests/test_v1_scorer.py` | 47 |
| `tests/test_builder.py` | 35 |
| **Grand total (new)** | **~406** |
| Existing `test_scoring.py` | ~60 |
| **Session grand total** | **~466** |

---

## 2. Coverage Gaps Still Open

### Heavy-dependency targets (skipped per guardrails)
These require torch / transformers / sentence-transformers — cannot be tested in fast
unit-test mode.

- `core/nlp/classifier.py` — `classify_chunks()` needs 3 HuggingFace models (~1 GB).
  Flag: needs an integration test fixture with mocked model loading.
- `core/nlp/embedder.py` — `embed_chunks()` / `embed_and_store()` needs e5-base and bge-m3.
  The language-detection heuristic (`_detect_language`) is a pure-string function that
  COULD be extracted and tested without models — recommend splitting it out.
- `core/nlp/chunker.py` — `chunk_document()` needs PyMuPDF (`fitz`).  The sentence-window
  logic itself is dependency-light; a unit test could inject a fake `IngestionResult`.

### Network / LLM targets (skipped per guardrails)
- `core/llm/router.py` — `ModelRouter.ainvoke_with_fallback()` makes HTTP calls.
  Could be unit-tested with `unittest.mock.patch` on `httpx.AsyncClient`.  Recommend.
- `core/extraction/extractor.py` — invokes the LLM.  Unit-testable with a mocked router.
- `core/extraction/prompts.py` — `build_user_prompt()` is pure-function.
  **Recommend** adding tests: it takes an indicator dict and returns a string; no LLM needed.

### DB / async targets (skipped per guardrails)
- `api/documents.py`, `api/metrics.py`, `api/reports.py`, `api/pipeline.py` — need async
  DB + Celery.  Use `pytest-asyncio` + `httpx.AsyncClient` with a test DB fixture.
- `workers/tasks.py` — Celery tasks; need a test broker or `task.apply()` mode.

### Currently untested pure-function areas
- `core/scoring/gap_analysis.py` — `generate_gap_analysis()` and `generate_improvement_roadmap()`
  are already tested in `test_scoring.py`.  `build_gap_analysis()` (legacy) is called by
  `score_report`; indirectly covered here but not directly.
- `core/scoring/gri_scorer.py` / `sasb_scorer.py` / `tcfd_scorer.py` / `fra_compliance.py` —
  partially covered by `test_scoring.py`; gaps remain in sector-specific edge cases.
- `core/reporting/narrative.py` — calls LLM; skip.
- `core/reporting/renderer.py` — needs WeasyPrint or PyMuPDF; skip for pure-unit tests.
- `core/ingestion/parser.py` — needs PyMuPDF + real PDF file; integration-only.

---

## 3. Bugs Flagged

### BUG-1 — `pyproject.toml` testpaths mismatch (non-blocking but incorrect)
**File:** `pyproject.toml`, line 119
**Issue:** `testpaths = ["backend/tests"]` but all tests live in `tests/` at the repo root.
`pytest` run from the repo root with default discovery will find `tests/` automatically, but
the explicit `testpaths` will cause `pytest` to look in the wrong place if invoked without `-v`
or with `--collect-only`.
**Recommendation:** Change to `testpaths = ["tests"]` or remove the line to rely on auto-discovery.
**Impact:** The orchestrator's `pytest -q` from the repo root will likely still work (pytest falls
back to current directory when the specified path doesn't exist), but this should be corrected.

### BUG-2 — Stray test files are scripts, not pytest tests (advisory)
`backend/test_extraction.py` and `backend/test_nlp.py` are `async def main()` scripts with
`asyncio.run(main())` under `if __name__ == "__main__"`.  They use real PDFs, real LLM calls,
and real HuggingFace models.  They are NOT pytest-collectible and will be silently skipped.
`data/ingestion_test_files/test_ingestion.py` defines a `main()` and uses `sys.exit()` —
also not pytest-collectible.  These files are advisory-only and should be moved to `scripts/`
or `scripts/experiments/` to avoid confusion.
**No xfail needed** — they don't fail under pytest, they're just invisible to it.

### BUG-3 — `tests/test_scoring.py` imports functions that may be legacy-only
`test_scoring.py` imports `score_binary`, `score_composite`, `score_metric`, `score_pillar`,
`score_qualitative`, `score_quantitative`, `score_q_plus_ql`, `score_to_grade`, `score_topic`
from `scorer.py`.  The module docstring marks `score_metric` through `score_document` as "v2
surface (NOT wired into the pipeline yet)".  These are importable and tested by the existing
suite — no issue for tests, but the split between v1 (production) and v2 (unwired) surfaces
is a naming risk for future developers.

### BUG-4 — `score_quantitative` with `value=0` and no benchmark returns `1.0`, not `0.8`
**File:** `backend/app/core/scoring/scorer.py`, lines 167–170
**CLAUDE.md spec (Stage 1):** "Zero (legitimately zero) → 0.8"
**Actual code:**
```python
if benchmark is None:
    if dir_str == MetricDirection.NEUTRAL.value:
        return 1.0  # any disclosure earns full score
    return 1.0 if v != 0 else 0.8
```
When `direction=NEUTRAL` (the default), `value=0` returns `1.0` instead of `0.8`.
The existing `test_scoring.py::TestScoreQuantitative::test_zero_no_benchmark_returns_1`
confirms this — it passes because it uses the NEUTRAL default.
This is only a discrepancy when `direction=NEUTRAL` — with `HIGHER_BETTER` or `LOWER_BETTER`
the zero-value-→-0.8 path is reachable.
**This is documented as known behavior in the existing test.** Not xfailed here because
the existing test already documents the actual behavior.

---

## 4. Recommended Next Test Priorities

1. **Fix `pyproject.toml` testpaths** (5-minute fix) — update to `testpaths = ["tests"]`.

2. **Move stray scripts to `scripts/experiments/`** — `backend/test_extraction.py`,
   `backend/test_nlp.py`, `data/ingestion_test_files/test_ingestion.py` are run-scripts, not
   tests.  Their presence in pytest-discoverable locations is misleading.

3. **Add `tests/test_prompts.py`** — `core/extraction/prompts.py` is pure-function
   (`build_user_prompt`, `build_system_prompt`).  No LLM needed.  Tests would verify:
   monetary-type indicators get currency extraction instructions; qualitative indicators get
   summary-style instructions; all 46 indicators produce non-empty prompts.

4. **Add `tests/test_chunker.py`** with a fake `IngestionResult` — sentence-window and
   block-merge strategies; section header assignment; `max_chars` enforcement.
   Only requires PyMuPDF NOT to be imported (the strategy logic is pure-string).

5. **Add `tests/test_router.py`** — mock `httpx.AsyncClient` to unit-test
   `ModelRouter.ainvoke_with_fallback()`: primary 200, primary 402→fallback 200,
   both fail→raise.  Uses `unittest.mock.AsyncMock`.

6. **Add integration tests under `tests/integration/`** — `conftest.py` with a SQLite
   in-memory DB + async session fixture.  Test `score_report` end-to-end with ORM metric
   objects (not SimpleNamespace stubs) to verify the gri_code→metric lookup works against
   real DB rows.

7. **Expand `test_indicators.py` parametrization** to verify that every indicator that
   appears in `materiality_weights` for a sector also appears in `get_indicators_for_sector()`
   for that sector — currently the two data structures are only spot-checked.
