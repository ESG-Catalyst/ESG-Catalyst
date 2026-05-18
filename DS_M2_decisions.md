# M2 (NLP) — Data Science Decision Log

**Module:** M2 — Chunker · Embedder · Classifier
**Author:** Data Science
**Status:** living document — chunking, embedding & classification finalized. Embedding pending re-validation on the §1.5 chunker (§2.9); the fully composed sentence_window + arch-B + routed-embedding stack is not yet measured end-to-end as a unit (§3.10)
**Primary evaluation corpus:** `data/ingestion_test_files/en_beltone_report_summary.pdf`
(Beltone Sustainability Report 2024 — 64 pages, ~176.5 K characters, English, finance/NBFI sector)

> How to read this document: each sub-module follows the same template —
> **Problem → What we tried → How we tested it → Decision → Why → Results → Threats to validity → Open follow-ups.**
> Numbers are reproducible from the scripts and JSON artifacts referenced in each section.
> This is a *decision record*, not a tutorial: it documents what we chose and the evidence that justified it,
> including the options we rejected and why.

---

## 1. Chunking

### 1.1 Problem framing

Chunking sits between ingestion (M1) and everything downstream — embedding, ESG
classification, and LLM extraction (M3). It is the highest-leverage knob in M2 because
every downstream metric is computed *on chunks, not on the document*. A chunk that is
too small carries no context (the classifier and the extractor see a fragment); a chunk
that is too large is silently truncated at the model's token limit (ClimateBERT/E5 ≈ 512
tokens, the extraction LLM by prompt budget), so content past the cut is invisible to the
pipeline. A chunk that splits a table across a boundary destroys the row/column structure
that ESG metrics live in (GHG tables, board-diversity tables, materiality matrices).

So the chunker is not a formatting step — it defines the **unit of recall** for the
entire product. The objective is: maximize the amount of genuinely ESG-relevant content
that survives into a single, model-sized, structure-preserving chunk.

We split the work into two stages:

- **A1 — strategy shootout:** pick the right *family* of chunking algorithm.
- **A2 — tuning:** tune the winning family's hyper-parameters, then integrate it behind config.

### 1.2 Experimental setup

**Corpus.** One real in-domain document (Beltone 2024). A single document is a deliberate
choice for A1/A2: it removes between-document variance so strategy differences are not
confounded, and Beltone is representative of the target segment (Egyptian NBFI, English,
table-heavy, mixed narrative + bullet content). Generalization to Arabic and to other
issuers is explicitly deferred (see §1.8).

**Harness.** `scripts/experiments/chunking_comparison.py` (A1) and
`chunking_tuning.py` (A2). Both run the *real* M1 ingestion (`ingest_document`) once,
then feed the identical `IngestedDocument` to every strategy, so M1 is held constant and
only the chunker varies. Read-only — no pipeline file is touched during experimentation.

**Metrics and why each one.** A good chunker is not "uniform chunk size"; it is a
trade-off surface. We measured:

| Metric | What it proxies | Why it matters |
|---|---|---|
| `n_chunks` | retrieval granularity / cost | more chunks = finer recall but more embedding+classify compute |
| avg / min / max / std tokens (~3 chars/token) | size distribution | reveals fragmentation and fat tails a single mean hides |
| **% chunks < 50 tokens** | **noise rate** | sub-50-token chunks are page numbers, lone headers, footers — they dilute the index and waste classifier calls |
| **% chunks > 512 tokens** | **truncation risk** | anything past the encoder limit is *silently dropped* — invisible recall loss |
| Table preservation (3 known tables) | structure integrity | ESG numbers live in tables; a split table is a lost metric |
| ESG-pass count | end-task signal | the only metric that speaks to the actual product outcome |

**Table preservation probe.** Three tables were hand-identified from the Beltone PDF and
encoded as signature-string sets. A table counts as **intact** only if *one* chunk
contains *all* of its signature strings (vs. merely `found_anywhere`, i.e. present but
split across chunks):

1. `stakeholder_engagement_p7_8` — internal/external stakeholder matrix (pp. 7–8)
2. `materiality_matrix_p9` — 14-topic materiality matrix with H-H ratings (p. 9)
3. `esg_risks_opportunities_p26` — ESG areas vs efforts/risks/opportunities (p. 26)

This is a coarse but honest proxy: signature strings are deliberately spread across the
table so a mid-table split breaks the "intact" test.

**A1 ESG signal.** ClimateBERT-only `P(yes) ≥ 0.5` (the classifier of record *at the time
A1 ran*). This is an E-pillar-biased proxy and we knew it — see the validity note in §1.8.
A1's job was to choose a *family*, where the E-biased signal is still directionally fine.

**A2 ESG signal.** The post-C3 **3-voter ensemble classifier** (ClimateBERT + finbert-esg
+ nbroad/ESG-BERT, 2-of-3, threshold 0.3) — the production classifier. A2 is where the
ESG-pass number actually drives the decision, so it had to use the real classifier.

### 1.3 A1 — strategy shootout

Five strategies, same document, same metrics.
Artifact: `scripts/experiments/results/chunking_comparison.json`.

| Strategy | n | avg tok | %<50 | %>512 | tables intact | CB pass | %CB |
|---|---:|---:|---:|---:|:--:|---:|---:|
| `current` (block_merge, 2000/200) | 479 | 122.9 | **46.8%** | 5.4% | 1/3 | 161 | 33.6% |
| **`sentence_window` (w3, s1)** | 717 | 244.8 | **2.8%** | 6.4% | **3/3** | 314 | 43.8% |
| `semantic` (E5 cosine < 0.7) | 2 | 29 359 | 0.0% | **100%** | 3/3 | 2 | 100% |
| `section_aware` (≤512 tok) | 439 | 133.4 | **51.2%** | 0.2% | 1/3 | 132 | 30.1% |
| `recursive` (LangChain, 2000/200) | 126 | 490.0 | 0.8% | **56.4%** | 2/3 | 76 | 60.3% |

**Reading the table — strategy by strategy:**

- **`current` / block_merge (the incumbent).** Its regex block-merger fragments the
  document: **46.8% of chunks are sub-50-token noise** (page-number columns, lone ALL-CAPS
  headers). Only 1/3 tables survive intact, and the stakeholder table is not even
  `found_anywhere` — it was mangled by the parser/merge interaction. This is the baseline
  we are trying to beat, and it is clearly leaving recall on the table.

- **`sentence_window` (w=3, s=1).** Sliding 3-sentence window, stride 1. Lowest noise
  rate of any non-degenerate strategy (2.8%), **all 3 tables intact** (the overlapping
  window keeps a table's signature lines inside at least one chunk), and the highest
  ClimateBERT pass *count* of any reasonable strategy (314). Its weakness is a 6.4%
  long-tail (>512 tok) and a fat `max_tokens` of 2068 — caused by run-on table rows that
  contain no sentence terminator, so the sentence splitter never cuts them. That is a
  *fixable* weakness (it became the A2 objective).

- **`semantic` (E5, cosine < 0.7) — degenerate, instructive.** Collapsed the entire
  64-page document into **2 chunks of ~30 K tokens**. Root cause: `multilingual-e5-base`
  normalizes embeddings so aggressively that adjacent-sentence cosine similarity for
  continuous ESG narrative almost never falls below ~0.85, so a 0.7 cut point essentially
  never fires. The "100% tables intact / 100% CB pass" line is an artifact of having two
  monster chunks, not a real result. Lesson: a semantic splitter on E5 needs a threshold
  near ~0.9 or a different sentence encoder; 0.7 is the wrong operating point for this
  embedding family. Rejected for A2, but the finding is logged because it will recur if
  semantic chunking is revisited.

- **`section_aware`.** Worst noise rate (51.2%). Beltone's layout defeats the heuristic:
  the report uses many one-word ALL-CAPS "headers" (`E`, `S`, `G`, `INTERNAL POLICIES:`),
  each of which becomes its own micro-chunk. Good truncation profile (0.2% long) but the
  noise makes it unusable without an aggressive small-section merge pass we did not want
  to build speculatively.

- **`recursive` (LangChain `RecursiveCharacterTextSplitter`).** Cleanest low end (0.8%
  short) and best *rate* of CB pass (60.3%), but **56.4% of chunks exceed 512 tokens** —
  it packs aggressively to its 2000-char target, which means more than half of all chunks
  get silently truncated by every downstream encoder. High pass-*rate* on a small,
  truncation-heavy chunk set is a misleading number; the absolute pass *count* (76) is the
  lowest of all. Rejected.

**A1 decision: proceed with `sentence_window`.** It is the only strategy that is
simultaneously low-noise *and* structure-preserving (3/3 tables). Its one real flaw —
the >512-token long tail from un-terminated table rows — is a hyper-parameter problem,
not a family problem, which is exactly what A2 is for.

### 1.4 A2 — tuning the winner

We tuned three `sentence_window` variations, this time scored with the **production
ensemble classifier** (not ClimateBERT-only). We added one new knob, `max_chars`, a hard
character cap that sub-splits a window when a single run-on row blows past it — directly
targeting A1's only weakness.

Artifact: `scripts/experiments/results/chunking_tuning.json`.

| Variation | w | s | cap | n | %<50 | %>512 | ESG-relevant | %ESG | E / S / G |
|---|:--:|:--:|:--:|---:|---:|---:|---:|---:|:--:|
| **`sw_w3_s1_cap1500`** | 3 | 1 | 1500 | 695 | 3.9% | **1.3%** | **642** | 92.4% | 159 / 286 / 197 |
| `sw_w5_s2_cap1500` | 5 | 2 | 1500 | 368 | 2.7% | 1.9% | 351 | 95.4% | 91 / 159 / 101 |
| `sw_w3_s1_cap2000` | 3 | 1 | 2000 | 679 | 3.8% | 3.2% | 627 | 92.3% | 154 / 280 / 193 |

**Objective function.** We did not pick on a single column. The product wants *maximum
absolute ESG-relevant content* with *minimal noise and minimal truncation*, so we scored:

```
composite = n_esg_relevant − 2 · n_too_short − 5 · n_too_long
```

The asymmetric penalty is intentional and reflects cost-of-error: a too-short chunk is
*dilution* (cheap — the classifier usually rejects it anyway), but a too-long chunk is
*silent recall loss* (expensive — content is dropped with no signal). Hence 5× on long
vs 2× on short.

| Variation | composite |
|---|---:|
| **`sw_w3_s1_cap1500`** | **543.2** |
| `sw_w3_s1_cap2000` | 465.0 |
| `sw_w5_s2_cap1500` | 296.0 |

**Why not `sw_w5_s2_cap1500` despite its 95.4% pass *rate*?** Same trap as `recursive` in
A1: the wider window with stride 2 produces far fewer chunks (368), so the *rate* looks
great but the *absolute* ESG yield collapses — 351 relevant vs 642, and the S pillar
nearly halves (159 vs 286). The product is bottlenecked on *recall of ESG content*, not
on the percentage purity of a smaller set. Rate is the wrong target here; count is the
right one. This is why the composite uses counts, not rates.

**Why `cap=1500` over `cap=2000`?** Same window/stride, so ESG yield is essentially flat
(642 vs 627), but the tighter cap more than halves the truncation tail (1.3% vs 3.2%) at
no recall cost. Strictly dominant on the metric that represents silent loss.

### 1.5 Decision

> **Production chunking strategy: `sentence_window`, window = 3 sentences,
> stride = 1 sentence, hard cap = 1500 characters.**
> Selected by the composite objective `n_esg − 2·n_short − 5·n_long` on the
> production ensemble classifier, where it wins decisively (543.2 vs 465.0 vs 296.0)
> and is the only configuration with both a low noise floor (3.9%) and a near-zero
> truncation tail (1.3%) while preserving all three probe tables.

### 1.6 Production integration

Integrated without changing the public contract or refactoring the incumbent:

- **`backend/app/core/nlp/chunker.py`** — added a strategy dispatcher.
  `chunk_document(doc)` keeps its exact signature and return type
  (`list[Chunk]`). The original logic is preserved verbatim as the private
  `_chunk_block_merge()` so the incumbent remains byte-for-byte available for A/B and
  rollback. The new `_chunk_sentence_window()` does per-page sentence splitting with a
  section-header back-scan from the top of each page so `Chunk.section_header` metadata
  (relied on by retrieval and report rendering) is still populated.
- **`backend/app/config.py`** — `chunk_strategy` (default `"sentence_window"`, alt
  `"block_merge"`) plus the tuned knobs `chunk_window_sentences=3`,
  `chunk_stride_sentences=1`, `chunk_max_chars=1500`, with legacy
  `chunk_size_chars`/`chunk_overlap_chars` retained for `block_merge`.
- **Operability:** strategy is switchable via the `CHUNK_STRATEGY` env var with **zero
  code change** — this is a deliberate design choice so future A/B tests and a fast
  rollback path do not require a deploy. An explicit `strategy=` kwarg overrides config
  for the experiment scripts.

> *Repo-path note:* `CLAUDE.md` lists the chunker under `core/pipeline/chunker.py`; the
> file actually lives at `core/nlp/chunker.py`. We edited the real file and did **not**
> move it (moving it is out of scope and would break the classifier/embedder imports).

### 1.7 End-to-end impact (old vs new, same classifier)

The A1 and A2 ESG numbers used different classifiers, so they are **not** a fair
old-vs-new comparison. To isolate the chunker's contribution we ran both strategies
through the *identical* production ensemble classifier.
Harness: `scripts/experiments/chunker_integration_check.py`.
Artifact: `scripts/experiments/results/chunker_integration_check.json`.

| Metric | OLD `block_merge` | NEW `sentence_window` | Δ |
|---|---:|---:|---:|
| n_chunks | 479 | 695 | **+216 (+45%)** |
| ESG-relevant | 396 | 642 | **+246 (+62%)** |
| E pillar | 112 | 159 | +47 (+42%) |
| S pillar | 153 | 286 | **+133 (+87%)** |
| G pillar | 131 | 197 | +66 (+50%) |
| % ESG-relevant | 82.7% | 92.4% | +9.7 pp |

**Interpretation.** The chunker change alone recovers **+62% more ESG-relevant content**
from the same document. The gain is not uniform: the **S pillar nearly doubles (+87%)**.
That is the single most informative result in this section — it confirms the failure mode
diagnosed in A1. `block_merge` was fragmenting employee / HR / training / stakeholder
sections into one-line "header" chunks that fell below the noise floor and were dropped;
those sections are exactly where Social-pillar content concentrates. The new chunker
keeps that content in context-bearing windows, so the classifier can finally see it.
This is recovered recall, not relabeling.

### 1.8 Threats to validity (read before trusting these numbers elsewhere)

- **Single document, single language.** All A1/A2/integration numbers are Beltone-only,
  English. The deltas are large enough to be directionally safe, but the *magnitudes*
  will not transfer 1:1 to other issuers or to Arabic. Not yet validated on the Arabic
  corpus (`ar-adib-esg-report-2022_ar.pdf`).
- **Arabic sentence splitter is unproven at scale.** The next-sentence boundary regex is
  `[A-Z؀-ۿ]` (Latin capital *or* Arabic block start). It is verified on ASCII and
  reasoned-through for Arabic but not measured on a real Arabic document. Arabic lacks
  casing, so sentence segmentation there is structurally harder and is an open risk.
- **Table preservation is a 3-table proxy.** Three hand-picked tables, signature-string
  test. It is honest but coarse — it does not certify column/row alignment, only that the
  table did not get split. A 1/3 vs 3/3 difference is meaningful; treat "3/3" as
  "not catastrophically split", not "perfectly structured".
- **`n_esg_relevant` is classifier-defined recall, not ground truth.** We are optimizing
  the chunker against the ensemble classifier's judgment, not against human labels. If
  the classifier is biased, the chunker is being tuned to that bias. The +87% S-pillar
  gain is consistent with a real fragmentation fix (the dropped chunks were demonstrably
  HR/training content), which is why we trust it — but it is corroborating evidence, not
  proof.
- **The A1 semantic result is degenerate, not a ranking.** `semantic` "ranking #2" in the
  A1 JSON is an artifact of two 30K-token chunks trivially passing every test. It is not
  a real second place and must not be cited as one.
- **MLflow runs did not land.** Logging to `m2-chunking-experiments` failed on a Windows
  cp1252 console-encoding error when MLflow prints its run-banner emoji (`🏃`). The
  **JSON artifacts under `scripts/experiments/results/` are the authoritative record**;
  the MLflow UI is currently empty for this experiment. Fixing the console encoding so
  these runs are visible is an open task.

### 1.9 Open follow-ups (chunking)

- Re-run M3 extraction A/B on `sentence_window` chunks vs the 46-indicator catalog;
  watch for **confidence drift** — chunks are now smaller and more numerous, which can
  change extraction confidence even when recall improves.
- Validate `chunk_strategy` propagation through the Celery worker / docker-compose env.
- Widen A1/A2 to the Arabic ADIB report; specifically verify the Arabic sentence regex
  does not degrade segmentation at scale.
- Fix the MLflow Windows console-encoding issue so `m2-chunking-experiments` is visible
  in the UI (set `PYTHONIOENCODING=utf-8` or patch the logging path).
- Consider a small-section merge pass that could make `section_aware` competitive — not
  prioritized unless `sentence_window` underperforms on a future corpus.

---

## 2. Embedding

### 2.1 Problem framing

The embedder turns each chunk into the vector the retriever ranks on. It defines the
**unit of similarity** the same way the chunker defines the unit of recall: if the
embedding space does not put a query near the chunk that answers it, no amount of
downstream prompt engineering recovers that content — the extractor (M3) never sees it.

Two facts make this a real decision rather than a default:

1. **The corpus is bilingual.** Target issuers publish ESG reports in Arabic (ADIB,
   regional banks) and English (Beltone, MENA NBFIs). An embedding model that is strong
   in English and weak in Arabic produces a product that silently underperforms on half
   the market — and the failure is invisible unless Arabic is *explicitly* in the
   evaluation. This is the embedding analogue of the chunker's "silent truncation": loss
   with no signal.
2. **Model cost is highly asymmetric.** Candidate models span 4× in encode latency and
   ~4× in resident RAM. On a Celery worker that re-embeds every uploaded report, encode
   time is a per-document tax and RAM is a container-budget constraint. Recall is the
   objective, but cost is a hard secondary axis — exactly the kind of trade-off surface
   §1 treated chunking as, not a single-number maximization.

We split the work into two stages, mirroring §1:

- **B1 — model shootout:** pick the embedding model(s) on a bilingual retrieval test set.
- **B2 — production integration:** wire the winner(s) into `embedder.py` + ChromaDB and
  verify the live store reproduces the offline numbers.

### 2.2 Experimental setup

**Corpus.** Two real in-domain documents, one per language:
`en_beltone_report_summary.pdf` (Beltone Sustainability Report 2024 — English, the §1
corpus) and `ar-adib-esg-report-2022_ar.pdf` (Abu Dhabi Islamic Bank ESG 2022 — Arabic,
71 pages, ~136.6 K chars). Unlike §1, a single document is **not** sufficient here: the
entire point is cross-language behavior, and an English-only corpus cannot measure it.
Accepting between-issuer variance is a deliberate trade — see §2.8.

**Harness.** `scripts/experiments/embedding_comparison.py` (B1) and
`scripts/experiments/embedder_chromadb_test.py` (B2). Both run real M1 ingestion + the
M2 chunker once per document, then hold the chunk set fixed and vary only the embedding
model — same "hold everything upstream constant" discipline as §1.2. Read-only against
pipeline code during B1.

> **Chunker-version caveat (read this before §2.7).** Both embedding scripts produced
> **479 Beltone chunks at ~369 chars avg** — that is the `block_merge` incumbent
> (§1.3: 479 chunks, 122.9 avg tok ≈ 369 chars), **not** the `sentence_window` §1.5
> decision (695 chunks). The cross-reference contract "chunking held fixed at the §1.5
> decision" is therefore **not yet satisfied** for embedding. This is the single most
> important threat to validity in this section and is treated head-on in §2.8 rather
> than buried — the model *ranking* is expected to be robust to this, the *absolute*
> recall numbers are not.

**Retrieval test set.** `scripts/experiments/retrieval_test_set.json` — 20 hand-built
`(query, relevance_signature)` pairs: 10 English against Beltone, 10 Arabic against ADIB,
each tagged with a `doc_key` so a query is only ever scored against its own document's
chunks. The English set spans E/S/G (waste, energy, GHG, hires, suppliers, board
diversity, anti-corruption, risk); the Arabic set spans financial + E/S/G (Sharia-finance
portfolio, sustainability-finance commitment, capital adequacy, whistleblowing, AML,
Moody's rating, volunteering, training hours, complaint resolution, solar-plant finance).

**Recall metric and why this one.** A query's answer frequently spans 2–3 small chunks
(the §1 fragmentation finding applies here too). Standard top-k retrieval where the LLM
then reads *all* k chunks is well modelled by **collective signature coverage**: the
query scores a hit@k iff every substring in its `relevance_signature` appears somewhere
in the **union of the top-k retrieved chunks**, not necessarily in one chunk. This is the
same honest-proxy philosophy as §1.2's table-signature test, adapted from "did one chunk
keep the table intact" to "did the retrieved set collectively contain the answer".

- **recall@5** — primary. The extractor consumes a small candidate set; this is the
  number that predicts product recall.
- **recall@1** — secondary. Did the single best chunk already contain the answer?
  Matters for any future re-rank/short-context path.
- **embed_time_sec, RAM delta** — the cost axis (§2.1 point 2).

A **pre-flight coverage check** rejects test cases the chunker cannot possibly answer
(every signature substring must exist *somewhere* in the doc's chunk set before the case
counts) — the embedding analogue of §1's refusal to credit a degenerate chunker. Final
test set: **20/20 answerable**, so recall@5 = 1.0 is achievable on every query and a miss
is a genuine embedding failure, not a chunker artifact.

### 2.3 B1 — model shootout

Five models, both documents, language-routed scoring.
Artifact: `scripts/experiments/results/embedding_comparison.json`.
MLflow: `m2-embedding-experiments` (this experiment *did* land — the B1/B2 scripts force
`PYTHONIOENCODING`/stream reconfigure, fixing the §1.8 cp1252 banner crash).

| Model | dim | R@1 EN | R@5 EN | R@1 AR | R@5 AR | R@5 overall | embed s | RAM MB |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `e5-base` (incumbent) | 768 | 0.20 | **0.80** | 0.10 | 0.80 | 0.80 | **126** | 1610 |
| `e5-large` | 1024 | 0.20 | 0.70 | **0.50** | 0.80 | 0.75 | 440 | 2352 |
| `mpnet-multi` | 768 | **0.50** | 0.70 | 0.20 | **0.30** | 0.50 | **63** | **673** |
| **`bge-m3`** | 1024 | 0.20 | **0.80** | 0.40 | **0.90** | **0.85** | 696 | 2622 |
| `arabertv2` (AR-only) | 768 | — | — | **0.00** | **0.00** | — | 66 | 403 |

**Reading the table — model by model:**

- **`intfloat/multilingual-e5-base` (incumbent).** Balanced and cheap: R@5 0.80 in both
  languages, 126 s, 1.6 GB. No language is its weak point. This is the bar to beat.

- **`intfloat/multilingual-e5-large`.** Strictly *worse value* than e5-base here: same EN
  R@5 minus 0.10, equal AR R@5, but 3.5× the encode time and +0.7 GB RAM. Its one genuine
  edge is **AR R@1 = 0.50** (vs 0.10 for e5-base) — it surfaces the exact answer chunk
  first in Arabic far more often. Irrelevant to recall@5, logged for a possible future
  re-rank path. Rejected as a primary model: paying 3.5× for a R@5 regression is the
  embedding version of §1.3's `recursive` trap (a tempting headline number that costs
  recall).

- **`paraphrase-multilingual-mpnet-base-v2` — the instructive near-miss.** On the
  **English-only** view this is the most *tempting* model in the field: best R@1 by far
  (0.50), the fastest (63 s), and the lightest by a wide margin (673 MB — 40% of e5-base,
  25% of bge-m3). An English-only evaluation would have made a strong case to ship it.
  The bilingual run disqualifies it outright: **AR R@5 collapses to 0.30** — it fails 7
  of 10 Arabic queries. This is the embedding analogue of §1.4's *rate-vs-count trap*:
  there, a higher pass-*rate* hid a collapse in absolute ESG *count*; here, a strong
  *English* number hides a collapse in *Arabic* recall. **Lesson, stated as a rule:
  evaluate every model in every target language before trusting any aggregate — an
  English-only embedding benchmark is actively misleading for a bilingual product.**

- **`BAAI/bge-m3`.** Best AR R@5 (0.90 — one miss in ten) and ties the incumbent on EN
  R@5 (0.80). Highest overall R@5 (0.85). It pays for it: 696 s encode (5.5× e5-base) and
  2.6 GB RAM (the heaviest). It is the only model that is never the weak link in either
  language.

- **`aubmindlab/bert-base-arabertv2` (Arabic specialist) — degenerate, instructive.**
  R@1 = R@5 = **0.00** on Arabic. This is the embedding twin of §1.3's degenerate
  `semantic` chunker: a clean experiment that produces a non-result for an understood
  reason. AraBERT is a **masked-LM encoder with no contrastive/retrieval fine-tuning**;
  mean-pooling its token states yields vectors that do not separate similar from
  dissimilar text, so cosine ranking is no better than random and never lands a
  signature in top-5. The finding is logged precisely so it is **not over-generalized**:
  it does *not* say "Arabic-specialist embeddings are bad", it says "an MLM checkpoint is
  not a retrieval model". A retrieval-fine-tuned Arabic SBERT remains an open,
  un-tested alternative (§2.9).

### 2.4 The English-only reversal (why B1 needed Arabic)

This deserves its own subsection because it is the methodological core of the embedding
decision, exactly as §1.4's objective-function discussion is for chunking.

Run the same harness on **English only** (the natural first instinct — the §1 corpus is
English, the incumbent test doc is Beltone):

| Model | R@1 EN | R@5 EN | encode | RAM | English-only verdict |
|---|---:|---:|---:|---:|---|
| e5-base | 0.20 | 0.80 | 126 s | 1.6 GB | solid, balanced |
| **mpnet-multi** | **0.50** | 0.70 | **63 s** | **0.7 GB** | **most tempting — best R@1, cheapest, lightest** |
| bge-m3 | 0.20 | 0.80 | 696 s | 2.6 GB | best R@5 but 11× mpnet's encode |
| e5-large | 0.20 | 0.70 | 440 s | 2.4 GB | dominated |

On this view mpnet-multi is a defensible production pick: it puts the answer chunk
*first* 2.5× as often as the incumbent, at half the RAM and half the encode time. Adding
the 10 Arabic queries inverts the decision completely — mpnet's AR R@5 is **0.30**.
Shipping the English-only recommendation would have silently halved Arabic retrieval
quality with **no failing test to catch it**, because there would have been no Arabic
test. The reversal is the justification for the entire bilingual test-set investment.

### 2.5 Decision

> **Production embedding: language-routed, separate models per language.**
> **English chunks → `intfloat/multilingual-e5-base` (768-d). Arabic chunks →
> `BAAI/bge-m3` (1024-d).** Routing is by a chunk-level Unicode-script heuristic
> (≥ 10 % of characters in Arabic Unicode blocks ⇒ Arabic, else English).

### 2.6 Why this, and why not the simpler single-model choice

The honest reading of §2.3 is that **single-model `bge-m3` is the simplest defensible
choice**: it ties the incumbent on EN R@5 and wins AR R@5 outright, so on recall alone
one multilingual model dominates and needs no routing logic. We did not choose it, and
the reason is the §2.1-point-2 cost axis, applied with the same cost-of-error asymmetry
that drove §1.4's composite:

- bge-m3 buys **+0.10 AR R@5** (0.90 vs 0.80) over e5-base and **+0.00 EN R@5** (tie).
- bge-m3 costs **5.5× encode time** (696 s vs 126 s for the same 609 chunks) and
  **+1.0 GB resident RAM** on every worker.
- The current corpus is **majority English**; the Arabic share is real but not dominant.

Paying bge-m3's tax on *English* chunks buys exactly zero recall (EN R@5 is tied) while
incurring the full latency/RAM cost on the majority of the corpus. Routing pays the
expensive model only where it demonstrably buys recall (Arabic), and keeps the cheap,
equal-recall model on the majority path. This is the same shape of argument as §1.4's
"5× penalty on truncation, 2× on noise" — spend cost where the error is expensive, not
uniformly.

**This decision is falsifiable**, and we state the kill-criteria up front:

- If the corpus shifts to majority-Arabic, or worker encode time stops being a
  constraint (GPU, batch pre-embed), the cost argument collapses and **single-model
  bge-m3 becomes the correct choice** — routing should then be removed, not kept for
  inertia.
- If a wider Arabic test set (§2.9) erases the 0.10 AR gap, the routing buys nothing and
  the incumbent single-model e5-base wins on simplicity.

**Forced architectural consequence (not a free choice).** e5-base is 768-d and bge-m3 is
1024-d. A single ChromaDB collection has one fixed dimensionality, so language routing
*forces* **two physical collections**: `document_chunks_en` (768-d) and
`document_chunks_ar` (1024-d). This is a direct, unavoidable consequence of §2.5 and is
called out so it is not mistaken for incidental design.

### 2.7 Production integration

Integrated without breaking the public contract, mirroring §1.6's discipline:

- **`backend/app/core/nlp/embedder.py`** — rewritten for language routing.
  `embed_chunks(chunks) -> list[EmbeddedChunk]` is the public API (each `EmbeddedChunk`
  carries `chunk`, `embedding`, and detected `language`); `compute_embeddings` is kept
  as a verbatim back-compat alias so existing callers (`backend/test_nlp.py`,
  `app.core.nlp.__init__`) do not break. New `embed_query(query, lang=…)` (auto-detects
  or forces language, applies the E5 `query:` prefix only for the E5 family),
  `detect_chunk_language()`, and `preload_models()` (eager dual-model load for worker
  warm-start). Models are lazy singletons, one per language, loaded once per process.
- **`embed_and_store()`** — now returns `{"en": [...ids], "ar": [...ids]}` and writes to
  the two language collections, each created with **`metadata={"hnsw:space": "cosine"}`**.
  This is a correctness fix, not a tuning knob: every candidate model emits
  L2-normalized vectors, so the ChromaDB default **L2 distance ranks on magnitude noise
  instead of angle**. Cosine is the metric the models were trained for.
- **`backend/app/config.py`** — `embedding_model_en` (default e5-base),
  `embedding_model_ar` (default bge-m3); legacy `embedding_model` retained as an
  EN-mirror alias so nothing reading the old field breaks. Swappable via
  `EMBEDDING_MODEL_EN` / `EMBEDDING_MODEL_AR` env vars with **zero code change** — same
  operability stance as §1.6's `CHUNK_STRATEGY`.
- **`scripts/download_models.py`** — pre-caches both e5-base and bge-m3.
  **`.env.example`** documents both vars + the one-time migration.

> *Ownership/scope note (cf. §1.6's repo-path note).* `CLAUDE.md`'s M1 backlog assigns
> per-chunk `ar`/`en` tagging to the chunker (M1). That tag does not yet exist on
> `Chunk`. Rather than edit M1-owned `chunker.py` from an M2 task, language detection is
> done **inside the embedder** via the Unicode-script heuristic. It is a clean ownership
> boundary, not a workaround, and is documented so the duplication is removed if/when M1
> adds the canonical tag.
>
> *Migration.* Per-language collections are new names. Any pre-existing
> `document_chunks` collection was created with the default L2 metric and the old single
> model — it must be **deleted and re-embedded once**; the new collections are created on
> first write. This is stated in `.env.example` and the CLAUDE.md session log.

**Operability tooling.** Because ChromaDB 1.0 removed the legacy `/api/v1` path that
every community admin image targets, a small first-party Streamlit browser
(`frontend/chromadb_admin.py`, docker-compose service `chromadb_admin`) was added. It
uses the official client (v2 tenant-scoped) and the production `embed_query`, so the
store can be inspected and ad-hoc semantic queries run with the *exact* production
embedding path. Not part of the DS decision; logged because it is the verification
surface for §2.8 follow-ups.

### 2.8 End-to-end verification (offline numbers vs live ChromaDB)

The §1.7 analogue: prove the production store reproduces the experiment, so the decision
is not an artifact of the offline harness. `embedder_chromadb_test.py` re-embeds both
documents through the **production `embed_and_store`**, writes to the live cosine
collections, then re-runs the identical 20-query set via `collection.query()`.

| Path | Model | R@1 | R@5 | B1 offline reference | Match |
|---|---|---:|---:|---|:--:|
| EN → `document_chunks_en` | e5-base | 0.20 | 0.80 | R@1 0.20 / R@5 0.80 | ✅ exact |
| AR → `document_chunks_ar` | bge-m3 | 0.40 | 0.90 | R@1 0.40 / R@5 0.90 | ✅ exact |
| Overall (routed) | — | 0.30 | **0.85** | R@1 0.30 / R@5 0.85 | ✅ exact |

Top-hit cosine distances were all < 0.5 (similarity > 0.5). The live store with
`hnsw:space=cosine` reproduces the in-memory dot-product ranking **exactly** — the
cosine collection config is verified correct, not assumed. ADIB split 20 EN / 110 AR
chunks across collections, confirming the routing heuristic handles a genuinely
bilingual document at the chunk level.

### 2.9 Threats to validity (read before trusting these numbers elsewhere)

- **Embedding was validated on the *superseded* chunker.** B1/B2 ran on `block_merge`
  (479 Beltone chunks), **not** the §1.5 `sentence_window` decision (695 chunks). The two
  M2 decisions were optimized **independently and never composed**. Expected impact:
  model *ranking* is likely robust (the bge-m3 ≥ e5-base ≫ mpnet-on-Arabic ordering is
  large and mechanism-driven, unlikely to invert under finer chunks), but every
  *absolute* recall number here will move on `sentence_window` chunks. **Re-running B1/B2
  on the §1.5 chunker is the highest-priority open task** and a hard prerequisite before
  these recall figures are quoted as the production stack's numbers.
- **Tiny test set; the AR decision rides on one query.** AR R@5 0.90 (bge-m3) vs 0.80
  (e5-base) is a **one-query** difference on 10. The §2.6 routing rationale survives a
  one-query swing only because it rests primarily on the *cost asymmetry*, not the 0.10
  gap — but the gap itself is within sampling noise and must not be cited as a precise
  effect size.
- **Two documents, between-issuer confound (accepted, unlike §1).** §1 deliberately used
  one document to remove issuer variance; §2 *cannot* (English-only can't test Arabic),
  so EN and AR results are each single-issuer and confound "language" with "this issuer's
  writing/layout". Beltone-EN vs ADIB-AR differences are language **and** issuer.
- **Signature-coverage recall is classifier-free but not ground truth.** Same caveat
  class as §1.8's "classifier-defined recall": a hit means the answer string is present
  in the retrieved set, not that a human judged the chunk relevant. It is an honest,
  reproducible proxy, not adjudicated relevance.
- **AraBERT 0.00 is bounded evidence.** It disqualifies *one MLM checkpoint used as a
  retriever*. It says nothing about retrieval-fine-tuned Arabic models; do not cite it
  as evidence against Arabic-specialist embeddings generally.
- **e5-large's AR R@1 = 0.50 is unexploited.** The strongest single-chunk Arabic result
  in the field is sitting in a rejected model. If a re-rank/short-context stage is added,
  this number should be revisited rather than treated as closed.

### 2.10 Open follow-ups (embedding)

- **Re-run B1 + B2 on the §1.5 `sentence_window` chunker** and re-confirm the decision.
  Until this is done, §2 and §1 are not a validated joint stack (top priority).
- **Widen the Arabic test set to 30+ queries across 2–3 Arabic issuers** before
  committing to bge-m3 long-term — the current AR decision is one query from a tie and
  one issuer from generalizable.
- **Evaluate a retrieval-fine-tuned Arabic SBERT** (e.g.
  `sentence-transformers/distiluse-base-multilingual-cased-v2`, or an Arabic-tuned E5)
  as a lighter AR-side alternative to bge-m3's 2.6 GB footprint — directly tests the
  §2.6 kill-criterion.
- **Re-test the §2.6 cost argument under GPU/batch pre-embed.** If encode latency stops
  being a per-document tax, single-model bge-m3 should replace the routing.
- **Promote language detection to M1** (canonical per-chunk `ar`/`en` tag on `Chunk`)
  and delete the embedder's heuristic duplicate once it exists.
- **Reconcile with M3.** Confirm the chosen embeddings actually improve extraction
  recall end-to-end, not just retrieval recall — retrieval R@5 is a proxy for the
  product outcome, not the outcome (same stance as §1.8's `n_esg_relevant` caveat).

---

## 3. Classification

### 3.1 Problem framing

The classifier is the **gate**: it decides which chunks the LLM extractor (M3) ever
sees. A chunk it rejects is invisible to the rest of the product no matter how good the
chunker (§1) or the embedder (§2) are. So its failure mode is the same shape as §1's
silent truncation and §2's silent Arabic loss — *recall lost with no signal* — but here
it is the most direct: a rejected Governance disclosure is a Governance metric the report
will never contain.

The incumbent (Iteration 0) was **ClimateBERT alone**
(`climatebert/distilroberta-base-climate-detector`), thresholded on `P(yes)`. ClimateBERT
is a binary *climate-relevance* detector. Using it as an *ESG*-relevance gate embeds a
structural bias: it is trained to recognise the Environmental register, and ESG reports
write Social and Governance disclosures in a different register (HR tables, OHS bullet
lists, board-composition prose, Code-of-Conduct paragraphs). The objective for this work:
**replace the E-biased gate with one whose recall is balanced across all three pillars,
without sacrificing precision** — and prove it on the same honest-proxy discipline §1/§2
used.

Work was split into four stages (C1–C4), mirroring §1's A1/A2 and §2's B1/B2:

- **C1 — bias audit:** quantify the incumbent's E-bias so the problem is a measured
  number, not an assertion.
- **C2 — single-model shootout:** is there one drop-in model that fixes it?
- **C3 — architecture shootout:** do multi-model compositions beat the best single model?
- **C4 — production integration:** wire the winner in behind the existing contract.

### 3.2 Experimental setup

**Corpus.** One real in-domain document — Beltone 2024, the §1 corpus — for the same
reason §1 used one document: it removes between-issuer variance so model/architecture
differences are not confounded. Generalization to Arabic and to other issuers is
explicitly deferred (§3.11), exactly as in §1.8.

**Chunker version (read before §3.10).** C1–C4 all ran on the **`block_merge`
incumbent** (479 Beltone chunks, §1.3), **not** the §1.5 `sentence_window` decision (695
chunks). This is the same cross-section integration gap §2.8 flags for embedding, and it
is deliberate: C1's ClimateBERT audit had to be on the chunks the incumbent classifier
actually saw in production at the time, and C2/C3 had to hold the chunker fixed to
compare classifiers. It is reconciled head-on in §3.10 — and unlike §2, the
reconciliation **already exists** because §1.7 ran this exact classifier on both
chunkers.

**Harness.** `scripts/experiments/classification_baseline.py` (C1),
`classification_shootout.py` (C2), `classification_multi.py` (C3). Each runs real M1
ingestion + the M2 chunker once, caches every model's per-chunk scores to JSON, and
composes decisions from the cache — so C3's architectures are evaluated on *exactly* the
same per-model scores C2 measured, with zero re-inference drift. Read-only against
pipeline code during C1–C3; C4 is the only stage that edits `classifier.py`.

**Ground truth.** `scripts/experiments/ground_truth_60.json` — 60 chunks, 20 per pillar,
**auto-seeded** by keyword density: the 20 chunks with the strongest *pure* E-keyword
signal (and zero S/G keywords), 20 pure-S, 20 pure-G, drawn from the Beltone block_merge
chunk set. Auto-seeding is a deliberate, stated trade — it is reproducible and unbiased
by the experimenter, but it is *keyword-defined*, not human-adjudicated (§3.11). The
"pure single-pillar" constraint keeps the GT unambiguous so a model that genuinely
predicts the pillar is rewarded and a model that pattern-matches one register is exposed.

**Metrics and why each one.**

| Metric | What it proxies | Why it matters |
|---|---|---|
| `n_passed` | gate permissiveness | too low = recall loss (the C1 failure); too high = no filtering value |
| `pct_E / pct_S / pct_G` | pillar balance | the bias this work exists to fix; a balanced gate has all three non-trivial |
| **min-pillar coverage** | **worst-case pillar recall** | the single number that captures "is any pillar being starved" — the C1 bias metric |
| precision on the 60-GT | label correctness | a balanced gate that mislabels pillars is useless to M4 scoring |
| latency ms/chunk, RAM | the cost axis | a per-document worker tax + container budget — a hard secondary axis, as in §2.1 |

> **Precision, stated honestly.** On a *fixed* 60-chunk GT where every item has a known
> pillar, "precision per pillar" = (correctly-pillared GT items)/(GT items of that
> pillar) — arithmetically this is recall/accuracy on the GT, reported under the column
> name `precision` for continuity with the experiment scripts. It is **not** IR-precision
> over the model's full positive set. This is called out so the 0.98/0.97 numbers are
> not over-claimed (cf. §1.8's "classifier-defined recall is not ground truth" and
> §2.9's "signature-coverage recall is not adjudicated relevance").

### 3.3 C1 — the ClimateBERT bias audit (baseline)

ClimateBERT alone, every Beltone chunk, threshold 0.3.
Artifact: `scripts/experiments/results/baseline.json`.
MLflow: `m2-classification-experiments`, run `baseline-climatebert`.

| | n_passed | pct_E | pct_S | pct_G | avg P(yes) on E | avg P(yes) on S |
|---|---:|---:|---:|---:|---:|---:|
| ClimateBERT only (incumbent) | 170 / 479 | 25.9 | **13.5** | 17.1 | **0.977** | **0.803** |

**Reading the result.** ClimateBERT passes only 170 of 479 chunks, and the survivors are
E-skewed: S is the smallest pillar at 13.5%. The decisive number is the **score gap**:
chunks that are genuinely Social score on average 0.803 vs 0.977 for Environmental — the
model is systematically *less confident* on Social content even when it lets it through.
The audit also surfaced concrete dropped content: textbook S/G disclosures
(whistleblowing policy, occupational-health-and-safety, internal-audit mandate,
Code-of-Conduct) scored **P(yes) = 0.04–0.09** — far below any usable threshold. These
are GRI 2-9 / 2-23 / 403-9 disclosures, i.e. exactly the metrics M4 needs. The bias is
not subtle and it is not a thresholding artifact; it is the model doing what it was
trained to do (detect *climate* text) applied to a job it was not trained for (detect
*ESG* text). C1's job was only to make this a number — it succeeded; min-pillar = 13.5%
is the bar §3 must beat.

### 3.4 C2 — single-model shootout

Four candidate single models, same chunks, same threshold 0.3, scored on the 60-GT.
Artifact: `scripts/experiments/results/shootout.json`. MLflow: four runs
(`finbert-esg`, `esgbert`, `envbert`, `finbert`).

| Model | n_passed | pct_E | pct_S | pct_G | precision_60GT | role |
|---|---:|---:|---:|---:|---:|---|
| **`yiyanghkust/finbert-esg-9-categories`** | 420 | 21.4 | **56.4** | 22.1 | **0.983** | best precision |
| `nbroad/ESG-BERT` (26 SASB topics) | 479 | 8.4 | 30.1 | **61.6** | 0.967 | runner-up |
| `ESGBERT/EnvironmentalBERT-environmental` | 183 | 100.0 | 0.0 | 0.0 | 0.333 | E-only by design |
| `ProsusAI/finbert` (sentiment) | 0 | — | — | — | 0.000 | control |

**Reading the table — model by model:**

- **`finbert-esg-9-categories`.** Highest precision in the field (0.983) and the only
  model with all three pillars materially represented. Its weakness is a **Social lean**
  (pct_S 56.4 vs pct_G 22.1) — it over-routes to Human Capital / Community Relations.
  Best single model, but not balanced.

- **`nbroad/ESG-BERT`.** Precision essentially tied (0.967), finest-grained label space
  (26 SASB topics — useful for the new `topic` field), but a **Governance lean** (pct_G
  61.6) and it passes *every* chunk (479/479): with all 26 labels mapped to a pillar it
  has no "not-ESG" class, so its argmax-confidence ESG signal is almost always above
  threshold. It filters nothing on its own.

- **`EnvironmentalBERT`.** Binary E-only by construction — pct_E 100, S = G = 0. It is
  the §1.3-`semantic` / §2.3-AraBERT analogue: a clean experiment with a non-result for
  an understood reason (it *cannot* predict S/G). Logged so the finding is not
  over-generalized: it disqualifies *this binary E detector as an ESG gate*, not
  environmental specialists generally.

- **`ProsusAI/finbert` (sentiment) — the control.** Correctly registers **0/0/0** — it
  has no ESG-relevance label, so under the corrected pass rule (§3.5) nothing passes.
  Its purpose is exactly that: a model with no ESG signal must score zero, and it does,
  which validates the harness.

### 3.5 The argmax-confidence trap (why C2 needed a definitional fix)

This subsection is the methodological core of the classification decision, the analogue
of §1.4's *rate-vs-count trap* and §2.4's *English-only reversal*. Two definitional bugs
in the first C2 pass would have produced a confidently wrong ranking:

1. **`nbroad/ESG-BERT` labels are `Snake_Case`.** The pillar map was first written with
   space-separated labels (`"business model resilience"`); the model actually emits
   `Business_Model_Resilience`. Every label missed the map, ESG-BERT scored 0/0/0, and it
   would have been discarded as a dead model. It is in fact the runner-up. **Lesson:
   verify a model's label space against its actual output before trusting a zero.**

2. **"Passes" must be ESG-mass, not argmax confidence.** The first pass marked a chunk
   ESG-relevant if the model's *top-label confidence* exceeded the threshold. But
   finbert-esg's top label is frequently **`Non-ESG`** with high confidence — a model
   confidently saying "this is not ESG" was being counted as passing. With the argmax
   rule, finbert-esg passed 477/479 (almost everything) and finbert-sentiment passed on
   confident `neutral`. The fix: a chunk passes iff **Σ P(labels that map to E/S/G) >
   threshold** — probability mass on *ESG* classes, not raw confidence on *any* class.
   Under the corrected rule finbert-esg drops to a sensible 420 and the sentiment control
   correctly collapses to 0.

**Stated as a rule:** *a relevance gate must threshold the probability mass on the
relevant classes, never the model's top-1 confidence — otherwise a confident "irrelevant"
prediction is scored as relevant.* This is the same family of error as §1.4 (optimising a
rate while the product needs a count) and §2.4 (optimising English while the product is
bilingual): the tempting default metric measures the wrong thing, and only an
adversarial check (here, the sentiment control returning non-zero) exposes it.

### 3.6 C3 — multi-model architectures

Three compositions, decisions composed from the C2 cache, latency measured warmed on a
50-chunk sample. Artifact: `scripts/experiments/results/multi_arch.json`. MLflow:
`arch-A`, `arch-B`, `arch-C`.

| Architecture | n_passed | pct_E | pct_S | pct_G | precision_60GT | latency ms/chunk | RAM resident |
|---|---:|---:|---:|---:|---:|---:|---:|
| `arch-A` ClimateBERT gate → finbert-esg pillar | 170 | 47.7 | 35.9 | 16.5 | 0.567 | 374 | ~0.7 GB |
| **`arch-B` ensemble (CB + finbert-esg + ESG-BERT, 2-of-3)** | **396** | **28.3** | **38.4** | **33.3** | **0.967** | 992 | ~1.0 GB |
| `arch-C` finbert-sent → ClimateBERT → finbert-esg | 170 | 47.7 | 35.9 | 16.5 | 0.567 | 740 | ~1.15 GB |

**Reading the table:**

- **`arch-A` and `arch-C` both collapse to C1.** Both use ClimateBERT as the *first*
  gate, so they inherit its 170-chunk E-biased survivor set verbatim (identical n_passed,
  identical pillar split). Precision then **crashes to 0.567** — not because the
  downstream pillar classifier is bad, but because the GT's S and G chunks were *already
  filtered by ClimateBERT* before finbert-esg ever saw them. Putting the biased model
  first poisons everything after it; these are **strictly worse than finbert-esg solo**.
  `arch-C`'s extra FinBERT-sentiment stage is additionally a proven no-op: it gives ≥0.5
  confidence on ~100% of ESG-report text, filtering nothing while adding latency and RAM.

- **`arch-B` is the only composition that beats the best single model on balance.**
  2-of-3 majority vote on the corrected ESG-mass signal. n_passed 396, **all three
  pillars within an 11-point band (28.3 / 38.4 / 33.3)**, precision 0.967 — statistically
  tied with finbert-esg solo. The vote is what fixes the bias: a chunk needs two
  independent models to agree, so no single model's register-bias dominates the gate. It
  costs 992 ms/chunk (the three models run per chunk) and ~1 GB resident.

### 3.7 Decision

> **Production classifier: architecture B — a 3-voter parallel ensemble.**
> ClimateBERT + `yiyanghkust/finbert-esg-9-categories` + `nbroad/ESG-BERT`, scored on
> every chunk; a chunk is ESG-relevant iff **≥ 2 of 3 voters** clear threshold 0.3 on
> their ESG-mass signal; pillar = majority vote of passing voters (ClimateBERT may only
> vote E; ties broken by summed vote confidence); `topic` = finbert-esg's argmax category
> if present, else ESG-BERT's argmax SASB topic.
> Selected because it is the only configuration that fixes the C1 bias —
> **min-pillar coverage 28.3% vs the incumbent's 13.5% (>2×)** — at a precision (0.967)
> statistically tied with the best single model.

### 3.8 Why this, and why not the simpler single-model choice

The honest reading of §3.4 is that **single-model `finbert-esg` is the simplest
defensible choice**: precision 0.983 (highest in the field, 1.6 pp *above* arch-B), one
model instead of three, 375 ms/chunk vs 992, ~0.44 GB vs ~1.0 GB. On precision and cost
alone, it wins. We did not choose it, for one reason that overrides all of those: it does
not fix the problem this work exists to fix.

- finbert-esg solo: pct_S 56.4 / pct_G 22.1 → **min-pillar 21.4%**.
- arch-B: 28.3 / 38.4 / 33.3 → **min-pillar 28.3%** — **+32% relative** worst-pillar
  recall.
- The precision difference (0.983 vs 0.967) is **1.6 pp on a 60-item GT** — within
  sampling noise, and on the *honest* precision caveat of §3.2 it is recall-on-GT, not
  IR-precision, so the gap is even less load-bearing than it looks.

This is the same cost-of-error asymmetry that drove §1.4's 5×-vs-2× penalty and §2.6's
"pay the expensive model only where it buys recall": a 1.6 pp precision give-back is
*cheap* (it is noise; M4 tolerates it), but a starved Governance pillar is *expensive*
(it is silent, structural recall loss — the exact C1 failure). We spend the precision and
the compute where the error is expensive.

**This decision is falsifiable. Kill-criteria, stated up front:**

- If a **human-adjudicated** GT (replacing the §3.2 keyword-seeded one) shows arch-B's
  pillar balance is a labelling artifact rather than recovered recall, the ensemble buys
  nothing and **finbert-esg solo wins on simplicity**.
- If worker latency/RAM becomes the binding constraint (no GPU, tight container), the
  992 ms / 1 GB cost may not justify +32% min-pillar — finbert-esg solo is the documented
  fallback, and the `use_climate_model=False` path already exists in code for an even
  cheaper keyword-only degrade.
- If a threshold sweep (§3.11) shows finbert-esg solo reaches arch-B's balance at a
  different operating point, the ensemble is redundant.

### 3.9 Production integration

Integrated without breaking the public contract, mirroring §1.6 / §2.7 discipline:

- **`backend/app/core/nlp/classifier.py`** — rewritten end-to-end. The original
  ClimateBERT path is preserved as the `use_climate_model=False` keyword-only fallback so
  the incumbent behaviour remains available for A/B and a cheap degrade.
  `classify_chunks(chunks, threshold=0.3, use_climate_model=True)` — **signature
  unchanged**. The three models are lazy per-process singletons.
- **`ClassifiedChunk`** gained four fields, all additive: `esg_relevant` (canonical,
  mirrors legacy `is_relevant` which is kept), `topic: Optional[str]` (the new
  fine-grained category), `votes_for: int` (0–3, for triage/debug), `ensemble: bool`
  (False on the keyword fallback). `pillar` is now `Optional[str]` — `None` on
  non-relevant chunks (was the string `"none"`). Existing fields and the legacy
  `is_relevant` are untouched, so the two known callers (`workers/tasks.py:153`, the M2
  tests) — which read only `.chunk`/`.is_relevant` and pass only the existing kwargs —
  work without modification.
- **`CONFIDENCE_THRESHOLD=0.80` in `.env` was NOT changed.** Verified by grep that it
  gates M3 metric-extraction confidence (`extractor.py`, `scorer.py`, `gap_analysis.py`),
  not the M2 classifier; the M2 threshold is the in-code default 0.3, matching what
  `tasks.py` already passed. Conflating the two would have been a silent behaviour change
  to extraction — explicitly avoided.
- **`scripts/download_models.py`** must be re-run on every machine so finbert-esg and
  ESG-BERT are HF-cached alongside ClimateBERT (the `hf_cache` named volume already
  persists them across container rebuilds per the dockerization session log). *Open
  flag:* the script edit itself is adjacent to the M1/M2 owner boundary and was left for
  an explicit pass — stated, not silently done.

> *Ownership/scope note (cf. §1.6, §2.7).* C4 deliberately did **not** touch
> `chunker.py` or `embedder.py` (the §1/§2-owned files) — the user gate was explicit and
> it preserves the clean M2-sub-module boundaries this whole document is organised around.

### 3.10 End-to-end reconciliation with §1.7 (and the joint-stack gap)

The §1.7/§2.8 analogue: prove the production classifier reproduces the experiment, and
reconcile the fact that the classifier was decided on `block_merge` chunks while §1.5
chose `sentence_window`.

**C4 integration smoke** (`classify_chunks` on Beltone, threshold 0.3): 479 chunks → 396
passed, **E 28.28 % / S 38.64 % / G 33.08 %**, votes_for distribution
{0:12, 1:71, 2:273, 3:123}, 738 s on CPU. These reproduce the C3 cached-decision
prediction *exactly* — the implementation is faithful to the experiment, not an
approximation of it.

**This is the reconciliation the §3 placeholder asked for.** §1.7 already ran *this exact
arch-B classifier*, held fixed, across both chunkers:

| Held: arch-B classifier | OLD `block_merge` | NEW `sentence_window` |
|---|---:|---:|
| chunks | 479 | 695 |
| ESG-relevant | **396** | 642 |
| E / S / G | 112 / 153 / 131 | 159 / 286 / 197 |

The block_merge column (396, 112/153/131) is **byte-identical** to the C4 smoke and the
C3 prediction — the two documents (§1 and §3) describe the *same measured run* from the
two module owners' perspectives, and they agree. §1.7's +62 % ESG gain is therefore
cleanly attributable to the *chunker* (classifier held fixed), and §3's pillar-balance
gain is cleanly attributable to the *classifier* (chunker held fixed at block_merge).
Each module's contribution is isolated.

**The honest gap (stated, not buried — cf. §2.8/§2.9):** the *fully composed* production
stack — `sentence_window` chunks → arch-B classifier → language-routed embedding — has
**never been measured end-to-end as a unit**. We have: chunker swap with classifier fixed
(§1.7), classifier swap with chunker fixed (§3.10), embedding with chunker superseded
(§2.8). The model *rankings* are mechanism-driven and expected to compose; the *absolute*
numbers will move. Measuring the composed stack is the top joint open follow-up, shared
with §2.10.

### 3.11 Threats to validity (read before trusting these numbers elsewhere)

- **Single document, single language.** All C1–C4 numbers are Beltone-only, English —
  same limitation as §1.8. Directionally safe (the bias and the fix are large,
  mechanism-driven effects), magnitudes will not transfer 1:1. Arabic is untested; the
  three voters all *claim* multilingual coverage but none is verified on
  `ar-adib-esg-report-2022_ar.pdf`.
- **Ground truth is keyword-seeded, not human-adjudicated.** `ground_truth_60.json` was
  auto-built from pure single-pillar keyword chunks. It is reproducible and
  experimenter-unbiased, but it is the same caveat *class* as §1.8's "classifier-defined
  recall" and §2.9's "signature coverage is not adjudicated relevance": we are scoring
  models against a keyword heuristic's notion of pillar, not a human's. Worse, the GT was
  seeded from **block_merge** chunks, so it inherits any block_merge fragmentation. A
  human-labelled GT is the single highest-value follow-up and is an explicit kill-
  criterion in §3.8.
- **"Precision" is recall-on-GT, not IR-precision.** Restated from §3.2 because it is the
  most over-claimable number here: 0.983 / 0.967 are accuracy on a fixed 60-item set, not
  precision over each model's full positive set. The arch-B-vs-finbert-esg gap (1.6 pp)
  is well within the noise of a 60-item GT and must not be cited as a precise effect size
  (cf. §2.9's "one-query AR difference").
- **Classifier decided on the superseded chunker.** C1–C4 ran on `block_merge`, not the
  §1.5 `sentence_window` decision. Unlike §2.8 this is *already reconciled* (§3.10, via
  §1.7 running this classifier on both chunkers) — but the joint stack is still unmeasured
  as a unit.
- **arch-B's precision is *below* the best single model.** The decision knowingly trades
  −1.6 pp precision for +32 % min-pillar. If that precision turns out to matter to M4
  more than pillar balance does, the decision inverts — §3.8 states this as an explicit
  kill-criterion rather than hiding it.
- **ESG-BERT is a near-constant "yes" voter.** With all 26 of its labels mapped to a
  pillar it has no not-ESG class, so its ESG-mass signal clears 0.3 on almost every
  chunk. In the 2-of-3 vote it therefore behaves close to a constant — the *effective*
  filter is "ClimateBERT AND finbert-esg agree, OR either agrees with ESG-BERT's
  ever-present yes". This still fixes the bias (it stops ClimateBERT being a *sole* gate)
  but the ensemble is less independent than "3 voters" implies. Quantifying ESG-BERT's
  marginal contribution (ablate it → 2-voter CB+finbert-esg) is an open follow-up.
- **Latency/RAM are psutil load-deltas, which under-report.** The ~1 GB figure is the
  honest peak-RSS estimate; the per-model `load_delta_mb` instrumentation under-counts
  due to allocator arena reuse. Treat "~1 GB resident" as the planning number, not the
  53 MB the raw delta logged.
- **MLflow for this experiment *did* land.** Unlike §1.8's empty `m2-chunking-experiments`
  (cp1252 banner crash), the classification scripts wrap MLflow stdout in a
  `redirect_stdout` so the 🏃 banner cannot crash the Windows console. All C1–C3 runs are
  in `m2-classification-experiments`. **Caveat:** the first C2 pass left **4 zombie
  `RUNNING` runs** (the crash happened before the run context closed); they carry the
  pre-fix buggy numbers and must be ignored / deleted — only the `FINISHED` runs are
  authoritative, and the JSON artifacts remain the system of record (same stance as §1.8).

### 3.12 Open follow-ups (classification)

- **Human-adjudicated ground truth** to replace the keyword-seeded 60-set — directly
  tests the §3.8 kill-criterion and removes the §3.11 GT caveat. Highest value.
- **Threshold sweep at 0.25 / 0.40** to find the precision/coverage knee, and to test
  whether finbert-esg solo reaches arch-B's balance at a different operating point (if so,
  the ensemble is redundant — a §3.8 kill-criterion).
- **ESG-BERT ablation:** measure the 2-voter (ClimateBERT + finbert-esg) ensemble vs the
  3-voter, to quantify ESG-BERT's marginal value given it is a near-constant yes (§3.11).
- **Arabic validation** on `ar-adib-esg-report-2022_ar.pdf` — verify the three voters do
  not degrade on Arabic the way mpnet did for embedding (§2.4); the bias audit (C1) should
  be re-run per-language.
- **Re-run C1–C3 on the §1.5 `sentence_window` chunks** and **measure the fully composed
  stack end-to-end** (sentence_window + arch-B + routed embedding) — the shared joint-
  stack task with §2.10; until then the production stack's numbers are inferred, not
  measured.
- **Reconcile with M3.** Confirm arch-B's recovered S/G recall actually raises GRI 401 /
  403 / 418 extraction hit-rates end-to-end — retrieval/gate recall is a proxy for the
  product outcome, not the outcome (identical stance to §1.8 and §2.10).

---

## Appendix — Reproduce

```bash
# A1 — 5-strategy shootout (ClimateBERT-only signal)
PYTHONPATH=backend python scripts/experiments/chunking_comparison.py
#   -> scripts/experiments/results/chunking_comparison.json

# A2 — tune sentence_window, ensemble classifier signal
PYTHONPATH=backend python scripts/experiments/chunking_tuning.py
#   -> scripts/experiments/results/chunking_tuning.json

# Old vs new, same ensemble classifier (apples-to-apples)
PYTHONPATH=backend python scripts/experiments/chunker_integration_check.py
#   -> scripts/experiments/results/chunker_integration_check.json

# B1 — 5-model bilingual embedding shootout
#   EMBEDDING_COMPARISON_FORCE_ONLINE=1 to refresh weights; default = HF offline
python scripts/experiments/embedding_comparison.py
#   -> scripts/experiments/results/embedding_comparison.json

# B2 — production embedder + live ChromaDB, re-run the 20-query set
#   requires ChromaDB up (docker compose up -d chromadb)
python scripts/experiments/embedder_chromadb_test.py
#   -> scripts/experiments/results/embedder_chromadb_test.json

# C1 — ClimateBERT bias audit (baseline)
PYTHONIOENCODING=utf-8 PYTHONPATH=backend python scripts/experiments/classification_baseline.py
#   -> scripts/experiments/results/baseline.json
# C2 — 4-model single-classifier shootout (auto-seeds ground_truth_60.json)
PYTHONIOENCODING=utf-8 PYTHONPATH=backend python scripts/experiments/classification_shootout.py
#   -> scripts/experiments/results/shootout.json
# C3 — 3 multi-model architectures, latency/RAM measured
PYTHONIOENCODING=utf-8 PYTHONPATH=backend python scripts/experiments/classification_multi.py
#   -> scripts/experiments/results/multi_arch.json
```

| Artifact | Path |
|---|---|
| A1 results | `scripts/experiments/results/chunking_comparison.json` |
| A2 results | `scripts/experiments/results/chunking_tuning.json` |
| Integration A/B | `scripts/experiments/results/chunker_integration_check.json` |
| B1 results | `scripts/experiments/results/embedding_comparison.json` |
| B2 ChromaDB verification | `scripts/experiments/results/embedder_chromadb_test.json` |
| Retrieval test set | `scripts/experiments/retrieval_test_set.json` (20 pairs, 10 EN + 10 AR) |
| C1 bias audit | `scripts/experiments/results/baseline.json` |
| C2 single-model shootout | `scripts/experiments/results/shootout.json` |
| C3 architecture shootout | `scripts/experiments/results/multi_arch.json` |
| C4 integration smoke | `scripts/experiments/results/integration_smoke.json` |
| Classification ground truth | `scripts/experiments/ground_truth_60.json` (60 chunks, 20 E + 20 S + 20 G, keyword-seeded) |
| Classification decision record | `ESG_Catalyst_Wiki/wiki/decisions/classification-architecture.md` |
| Production code | `backend/app/core/nlp/chunker.py`, `backend/app/core/nlp/embedder.py`, `backend/app/core/nlp/classifier.py`, `backend/app/config.py` |
| Chunking MLflow | `m2-chunking-experiments` *(empty — see §1.8 encoding bug; use JSON)* |
| Embedding MLflow | `m2-embedding-experiments` *(populated — B1/B2 scripts fix the cp1252 banner crash)* |
| Classification MLflow | `m2-classification-experiments` *(populated — C1–C3; ignore the 4 zombie `RUNNING` runs from the pre-fix first C2 pass, §3.11)* |