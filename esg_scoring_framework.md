# ESG Scoring Framework
## AI-Powered ESG Reporting Platform — Financial & Manufacturing Sectors
### Version 1.0 | Frameworks: FRA (Egypt) · GRI · SASB

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Core Scoring Algorithm](#2-core-scoring-algorithm)
3. [Financial Sector Scoring](#3-financial-sector-scoring)
   - 3.1 Pillar Weights & Rationale
   - 3.2 Environmental Pillar (E)
   - 3.3 Social Pillar (S)
   - 3.4 Governance Pillar (G)
4. [Manufacturing Sector Scoring](#4-manufacturing-sector-scoring)
   - 4.1 Pillar Weights & Rationale
   - 4.2 Environmental Pillar (E)
   - 4.3 Social Pillar (S)
   - 4.4 Governance Pillar (G)
5. [Metric Scoring Functions](#5-metric-scoring-functions)
6. [Composite Score Calculation](#6-composite-score-calculation)
7. [FRA Compliance Gate](#7-fra-compliance-gate)
8. [Gap Analysis Output](#8-gap-analysis-output)
9. [Weight Derivation Methodology](#9-weight-derivation-methodology)

---

## 1. Architecture Overview

### 1.1 Framework Hierarchy

The scoring engine combines three frameworks in a layered architecture:

```
┌─────────────────────────────────────────────────────────┐
│                    COMPOSITE ESG SCORE                  │
│                      (0 – 100)                         │
└──────────┬──────────────┬──────────────────────────────┘
           │              │              │
      E Score         S Score       G Score
      (E_weight)     (S_weight)    (G_weight)
           │              │              │
    ┌──────┴──────┐  ┌───┴────┐  ┌─────┴──────┐
    │  Topics     │  │ Topics │  │  Topics    │
    │ (Σ = 100%)  │  │(Σ=100%)│  │ (Σ = 100%) │
    └──────┬──────┘  └───┬────┘  └─────┬──────┘
           │              │              │
    ┌──────┴──────┐  ┌───┴────┐  ┌─────┴──────┐
    │  Metrics    │  │Metrics │  │  Metrics   │
    │ (Σ = 100%   │  │(Σ=100%)│  │ (Σ = 100%) │
    │  per topic) │  │        │  │            │
    └──────┬──────┘  └───┬────┘  └─────┬──────┘
           │              │              │
    ┌──────┴──────────────┴──────────────┴──────┐
    │         FRAMEWORK SOURCE LAYER             │
    │  FRA KPIs (floor) · GRI · SASB            │
    └───────────────────────────────────────────┘
```

### 1.2 Sector Selection

| Sector | SASB SICS | GRI Sector Standard | FRA Applicability |
|--------|-----------|---------------------|-------------------|
| Financial (NBFIs) | FN-CF, FN-IN | Banking Sector Standard | Full — Stage 1 KPIs |
| Manufacturing | RT-CH, EM-MM, etc. | Sector-specific per sub-industry | Partial — E/S/G policy KPIs |

### 1.3 Document Ingestion → Score Pipeline

```
Arabic/English PDF/DOCX
        │
        ▼
   NLP Extraction
   (named entity, table, value extraction)
        │
        ▼
   Metric Mapper
   (maps extracted text/values to metric codes)
        │
        ▼
   Metric Scorer
   (applies scoring function per metric type)
        │
        ▼
   Topic Aggregator
   (weighted sum within topic)
        │
        ▼
   Pillar Aggregator
   (weighted sum within pillar)
        │
        ▼
   Composite Calculator
   (weighted sum across pillars + FRA gate + assurance bonus)
        │
        ▼
   Gap Analyzer
   (missing metrics, FRA gaps, improvement priority)
```

---

## 2. Core Scoring Algorithm

### 2.1 Metric-Level Scoring Functions

Each metric has a `type` that determines how it is scored:

#### Type: BINARY
Used for: FRA yes/no KPIs, policy existence checks

```python
def score_binary(value: str | bool) -> float:
    """
    Returns 1.0 if the company discloses the item, 0.0 if not.
    value: extracted answer from document ('yes', 'no', True, False, None)
    """
    if value is None:
        return 0.0
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    normalized = str(value).strip().lower()
    return 1.0 if normalized in ('yes', 'true', '1', 'oui', 'نعم') else 0.0
```

#### Type: QUANTITATIVE
Used for: numeric disclosures (emissions in metric tons, headcount, ratios)

```python
def score_quantitative(value, benchmark=None, direction='higher_better') -> float:
    """
    Returns 0.0–1.0 based on whether a value is disclosed and, optionally,
    how it compares to a peer benchmark.

    Stage 1 (existence scoring — default):
      - Value present and non-zero → 1.0
      - Value present and zero (legitimately zero) → 0.8
      - Value absent / not disclosed → 0.0

    Stage 2 (benchmark scoring — when benchmark provided):
      - Scales the score relative to sector median.
      - For 'higher_better' metrics: score = min(value / benchmark, 1.0)
      - For 'lower_better' metrics: score = min(benchmark / value, 1.0)
        (e.g. emissions intensity — lower is better)
    """
    if value is None or value == '':
        return 0.0

    # Existence scoring (Stage 1 — no benchmark)
    if benchmark is None:
        return 1.0 if float(value) != 0 else 0.8

    # Benchmark scoring (Stage 2)
    v = float(value)
    b = float(benchmark)
    if b == 0:
        return 1.0 if v == 0 else 0.0
    if direction == 'higher_better':
        return min(v / b, 1.0)
    else:  # lower_better
        return min(b / v, 1.0) if v > 0 else 1.0
```

#### Type: QUALITATIVE
Used for: narrative disclosures, policy descriptions, approach statements

```python
def score_qualitative(disclosure: str | None, completeness_criteria: list[str]) -> float:
    """
    Scores a qualitative disclosure on a 0 / 0.5 / 1.0 scale.

    0.0 → absent (no disclosure found in document)
    0.5 → partial (disclosure exists but missing required elements)
    1.0 → complete (all completeness_criteria elements present and evidenced)

    completeness_criteria: list of keywords/phrases the LLM checks for
    in the extracted disclosure text.

    Implementation note: In the platform, the LLM evaluates the extracted
    text against criteria and returns a completeness ratio:
      - ratio >= 0.75 → 1.0
      - 0.25 <= ratio < 0.75 → 0.5
      - ratio < 0.25 → 0.0
    """
    if disclosure is None or len(disclosure.strip()) == 0:
        return 0.0

    if not completeness_criteria:
        return 1.0  # No criteria defined — presence alone = full score

    matched = sum(
        1 for criterion in completeness_criteria
        if criterion.lower() in disclosure.lower()
    )
    ratio = matched / len(completeness_criteria)

    if ratio >= 0.75:
        return 1.0
    elif ratio >= 0.25:
        return 0.5
    else:
        return 0.0
```

#### Type: QUANTITATIVE + QUALITATIVE (Q+QL)
Used for: metrics requiring both a number and an explanation

```python
def score_q_plus_ql(
    quantitative_value,
    qualitative_disclosure: str | None,
    completeness_criteria: list[str],
    q_weight: float = 0.6,
    ql_weight: float = 0.4
) -> float:
    """
    Blended score for metrics that require both a number and context.
    Default split: 60% quantitative, 40% qualitative.
    """
    q_score = score_quantitative(quantitative_value)
    ql_score = score_qualitative(qualitative_disclosure, completeness_criteria)
    return (q_score * q_weight) + (ql_score * ql_weight)
```

### 2.2 Topic-Level Aggregation

```python
def score_topic(metrics: list[dict]) -> float:
    """
    Weighted average of metric scores within a topic.

    metrics: [
      {
        'code': 'GRI 305-1',
        'score': 0.8,          # result of metric-level scoring function
        'weight': 0.35,        # weight within this topic (must sum to 1.0)
        'fra_required': True,  # whether this is an FRA Stage 1 KPI
      },
      ...
    ]

    Returns: float 0.0–1.0
    """
    assert abs(sum(m['weight'] for m in metrics) - 1.0) < 0.001, \
        "Metric weights within topic must sum to 1.0"

    return sum(m['score'] * m['weight'] for m in metrics)
```

### 2.3 Pillar-Level Aggregation

```python
def score_pillar(topics: list[dict]) -> float:
    """
    Weighted average of topic scores within a pillar.

    topics: [
      {
        'id': 'E1',
        'score': 0.75,         # result of score_topic()
        'weight': 0.30,        # weight within this pillar (must sum to 1.0)
      },
      ...
    ]

    Returns: float 0.0–1.0
    """
    assert abs(sum(t['weight'] for t in topics) - 1.0) < 0.001, \
        "Topic weights within pillar must sum to 1.0"

    return sum(t['score'] * t['weight'] for t in topics)
```

### 2.4 Composite Score Calculation

```python
def score_composite(
    pillar_scores: dict,        # {'E': 0.72, 'S': 0.58, 'G': 0.81}
    pillar_weights: dict,       # {'E': 0.25, 'S': 0.40, 'G': 0.35}
    fra_gate_passed: bool,
    external_assurance: bool,
    assurance_bonus: float = 0.05
) -> dict:
    """
    Calculates the final composite ESG score (0–100).

    Steps:
    1. Weighted sum of pillar scores
    2. Apply FRA compliance gate (cap at 60 if gate fails)
    3. Apply external assurance bonus (+5 points, max 100)

    Returns dict with raw score, gated score, and final score.
    """
    assert abs(sum(pillar_weights.values()) - 1.0) < 0.001

    # Step 1: weighted pillar sum → 0–1 range
    raw = sum(
        pillar_scores[p] * pillar_weights[p]
        for p in pillar_scores
    )

    # Step 2: scale to 0–100
    score_100 = raw * 100

    # Step 3: FRA compliance gate
    # If company fails FRA mandatory KPIs, composite is capped at 60
    gated_score = score_100 if fra_gate_passed else min(score_100, 60.0)

    # Step 4: external assurance bonus
    final_score = min(gated_score + (assurance_bonus * 100 if external_assurance else 0), 100.0)

    return {
        'raw_score': round(score_100, 2),
        'fra_gate_passed': fra_gate_passed,
        'gated_score': round(gated_score, 2),
        'assurance_bonus_applied': external_assurance,
        'final_score': round(final_score, 2),
        'grade': score_to_grade(final_score)
    }


def score_to_grade(score: float) -> str:
    """Converts numeric score to letter grade for report display."""
    if score >= 85:  return 'A'
    if score >= 70:  return 'B'
    if score >= 55:  return 'C'
    if score >= 40:  return 'D'
    return 'F'
```

---

## 3. Financial Sector Scoring

**Target:** Egyptian NBFIs (banks, leasing, microfinance, insurance, factoring) regulated by FRA.  
**SASB codes:** FN-CF (Consumer Finance), FN-IN (Insurance)  
**GRI:** Banking Sector Standard (2022 exposure draft)

### 3.1 Pillar Weights & Rationale

| Pillar | Weight | Rationale |
|--------|--------|-----------|
| **Environmental (E)** | **25%** | FRA Stage 1 limits E to own-operations footprint. Financed emissions (SASB FN-IN-410c) are real but Egyptian NBFIs are far from reporting them. Low weight reflects disclosure maturity, not materiality. |
| **Social (S)** | **40%** | Highest weight. Banking is people-facing: FRA covers 6 S-topics. Customer protection, financial inclusion, data privacy (Egypt PDPL 2020), and mis-selling are the dominant risk areas for Egyptian NBFIs. |
| **Governance (G)** | **35%** | FRA covers 6 G-topics with mostly binary KPIs. Anti-corruption/AML, data governance, and sustainability reporting quality are immediate compliance pressures. Higher than E because regulatory enforcement is active. |

**Derivation formula:**

```
W_E = (FRA_E_topics / FRA_total_topics) × 0.4  +  Sector_E_materiality × 0.6
    = (5/16) × 0.4  +  0.15 × 0.6  = 0.125 + 0.09  ≈ 0.25  ✓

W_S = (FRA_S_topics / FRA_total_topics) × 0.4  +  Sector_S_materiality × 0.6
    = (5/16) × 0.4  +  0.53 × 0.6  = 0.125 + 0.32  ≈ 0.40  ✓

W_G = (FRA_G_topics / FRA_total_topics) × 0.4  +  Sector_G_materiality × 0.6
    = (6/16) × 0.4  +  0.32 × 0.6  = 0.15 + 0.19   ≈ 0.35  ✓
```

Where:
- `FRA_x_topics` = count of FRA KPI topics in each pillar (E=5, S=5, G=6; total=16)
- `Sector_x_materiality` = sector materiality score derived from GRI Banking Sector Standard topic count and SASB topic depth (see Section 9)

---

### 3.2 Environmental Pillar — Financial Sector (Weight: 25%)

#### Topic Weights within E Pillar

| Topic ID | Topic | Weight | FRA KPI | Framework |
|----------|-------|--------|---------|-----------|
| FIN-E1 | Environmental governance & policy | 30% | E1 | FRA + GRI 102 |
| FIN-E2 | Carbon emissions | 25% | E2 | FRA + GRI 305 + SASB FN-IN-410c |
| FIN-E3 | Energy usage | 20% | E3 | FRA + GRI 302 |
| FIN-E4 | Water usage | 15% | E4 | FRA + GRI 303 |
| FIN-E5 | Waste management | 10% | E5 | FRA + GRI 306 |

**Topic weight derivation:**
FIN-E1 highest (30%) because FRA E1 has 6 sub-KPIs (most granular E topic) and management systems underpin all other E disclosures. FIN-E2 second (25%) because carbon is the only FRA topic with a quantitative target (metric tons) and links to SASB financed emissions. FIN-E3–E5 decrease proportionally by number of FRA sub-KPIs (3, 2, 1 respectively).

---

#### FIN-E1: Environmental Governance & Policy (30% of E)

**FRA KPIs (E1):** 6 binary items

| # | Metric | Code | Type | Weight | Scoring |
|---|--------|------|------|--------|---------|
| 1 | E&S/sustainability policy published and followed | FRA-E1.1 / GRI 102-19 | BINARY | 35% | `score_binary()` |
| 2 | Policy self-developed or adopted from global/national standard | FRA-E1.2 / GRI 102-20 | BINARY | 30% | `score_binary()` |
| 3 | Environmental & social risk identification and assessment process | FRA-E1.3 / GRI 102-29,30,31 | QUALITATIVE | 30% | `score_qualitative(criteria=['risk identification','assessment process','risk register'])` |
| 4 | Sub-policies for waste, water, energy, recycling | FRA-E1.4 / GRI 103-2 | BINARY | 20% | `score_binary()` — 0.25 points per sub-policy present (max 1.0) |
| 5 | GHG targets set and disclosed | FRA-E1.5 | BINARY + QUANT | 10% | `score_q_plus_ql()` — binary for target existence, quantitative if value disclosed |
| 6 | ISO 14001 or equivalent certification | FRA-E1.6 | BINARY | 5% | `score_binary()` |

> **Note on metric 4:** Score = count of sub-policies disclosed / 4. Partial credit is intentional — a company with water + energy but not waste/recycling scores 0.5.

---

#### FIN-E2: Carbon Emissions (25% of E)

**FRA KPIs (E2):** 1 quantitative item (total annual CO₂e in metric tons)

| # | Metric | Code | Type | Weight | Scoring |
|---|--------|------|------|--------|---------|
| 1 | Scope 1 + 2 + 3 GHG emissions (own operations), metric tons CO₂e | FRA-E2 / GRI 305-1,2,3 | QUANTITATIVE | 35% | `score_quantitative(value, benchmark=None)` |
| 2 | Absolute gross financed emissions — Scope 1, 2, 3 (portfolio) | SASB FN-IN-410c.1 | QUANTITATIVE | 35% | `score_quantitative()` — 0 if not disclosed |
| 3 | Gross portfolio exposure by industry; % included in financed emissions calc | SASB FN-IN-410c.2/3 | QUANTITATIVE | 20% | `score_quantitative()` |
| 4 | Methodology for calculating financed emissions | SASB FN-IN-410c.4 | QUALITATIVE | 10% | `score_qualitative(criteria=['methodology','PCAF','asset class','boundary'])` |

---

#### FIN-E3: Energy Usage (20% of E)

**FRA KPIs (E3):** 3 quantitative items

| # | Metric | Code | Type | Weight | Scoring |
|---|--------|------|------|--------|---------|
| 1 | Total energy consumed (GJ or MWh) | FRA-E3 / GRI 302-1 | QUANTITATIVE | 50% | `score_quantitative()` |
| 2 | % energy by generation type (renewable vs non-renewable) | FRA-E3 / GRI 302-2 | QUANTITATIVE | 30% | `score_quantitative()` — scored as ratio 0–1 |
| 3 | % energy saved annually | FRA-E3 | QUANTITATIVE | 20% | `score_quantitative()` |

---

#### FIN-E4: Water Usage (15% of E)

**FRA KPIs (E4):** 2 quantitative items

| # | Metric | Code | Type | Weight | Scoring |
|---|--------|------|------|--------|---------|
| 1 | Total water consumed (m³) | FRA-E4 / GRI 303-5 | QUANTITATIVE | 60% | `score_quantitative()` |
| 2 | Total water reclaimed (m³, if any) | FRA-E4 | QUANTITATIVE | 40% | `score_quantitative()` — 0.8 if zero (legitimately none) |

---

#### FIN-E5: Waste Management (10% of E)

**FRA KPIs (E5):** 1 quantitative item

| # | Metric | Code | Type | Weight | Scoring |
|---|--------|------|------|--------|---------|
| 1 | Waste generated by type and weight; % recycled/reclaimed | FRA-E5 / GRI 306-3,4,5 | QUANTITATIVE | 100% | `score_quantitative()` — partial credit for partial breakdown |

---

### 3.3 Social Pillar — Financial Sector (Weight: 40%)

#### Topic Weights within S Pillar

| Topic ID | Topic | Weight | FRA KPI | Framework |
|----------|-------|--------|---------|-----------|
| FIN-S1 | Gender diversity & pay equity | 12% | S1 | FRA + GRI 405 |
| FIN-S2 | Employee turnover | 8% | S2 | FRA + GRI 401 |
| FIN-S3 | Non-discrimination | 8% | S3 | FRA + GRI 406 |
| FIN-S4 | Health & safety | 8% | S4 | FRA + GRI 403 |
| FIN-S5 | Child & forced labor | 6% | S5 | FRA + GRI 408/409 |
| FIN-S6 | Labor rights | 6% | S6 | FRA + GRI 407/412/414 |
| FIN-S7 | Financial health & inclusion | 22% | — | GRI Banking + SASB FN-CF |
| FIN-S8 | Customer privacy & data security | 18% | — | GRI 418 + SASB FN-CF |
| FIN-S9 | Marketing, labeling & fair advice | 12% | — | GRI 417 + SASB FN-IN |

**Topic weight derivation:**
FIN-S7 (22%) and FIN-S8 (18%) have no FRA Stage 1 KPI but are the highest-weight S topics because: (a) FIN-S7 maps directly to FRA's broader mandate on financial inclusion for NBFIs, (b) FIN-S8 is driven by Egypt's PDPL 2020 creating direct legal exposure, and (c) both have the most SASB quantitative metrics available. FRA-covered topics (S1–S6) sum to 48%, weighted by number of sub-KPIs.

---

#### FIN-S1: Gender Diversity & Pay Equity (12% of S)

**FRA KPIs (S1):** 5 items

| # | Metric | Code | Type | Weight | Scoring |
|---|--------|------|------|--------|---------|
| 1 | Employee headcount by gender and contract type | FRA-S1 / GRI 405-1 | QUANTITATIVE | 30% | `score_quantitative()` |
| 2 | % entry/mid-level positions by gender | FRA-S1 / GRI 405-1 | QUANTITATIVE | 35% | `score_quantitative()` |
| 3 | % senior/executive positions by gender | FRA-S1 / GRI 405-1 | QUANTITATIVE | 35% | `score_quantitative()` |
| 4 | Median male-to-female compensation ratio | FRA-S1 / GRI 405-2 | QUANTITATIVE | 35% | `score_quantitative()` — higher score for ratio closer to 1.0 |

> **Pay ratio scoring:**
> ```python
> def score_pay_ratio(ratio: float) -> float:
>     """Scores gender pay ratio. Ratio = male_median / female_median.
>     Perfect equality (1.0) → 1.0. Each 10% deviation → -0.1."""
>     if ratio is None: return 0.0
>     deviation = abs(ratio - 1.0)
>     return max(0.0, 1.0 - deviation * 1.0)
> ```

---

#### FIN-S2: Employee Turnover (8% of S)

**FRA KPIs (S2):** 3 quantitative items

| # | Metric | Code | Type | Weight | Scoring |
|---|--------|------|------|--------|---------|
| 1 | YoY turnover % — full-time employees | FRA-S2 / GRI 401-1b | QUANTITATIVE | 40% | `score_quantitative()` |
| 2 | YoY turnover % — part-time employees | FRA-S2 / GRI 401-1b | QUANTITATIVE | 30% | `score_quantitative()` |
| 3 | YoY turnover % — contractors/consultants | FRA-S2 / GRI 401-1b | QUANTITATIVE | 30% | `score_quantitative()` |

---

#### FIN-S3: Non-Discrimination (8% of S)

**FRA KPIs (S3):** 1 binary item

| # | Metric | Code | Type | Weight | Scoring |
|---|--------|------|------|--------|---------|
| 1 | Non-discrimination policy (gender, religion, nationality) published | FRA-S3 / GRI 406 | BINARY | 50% | `score_binary()` |
| 2 | Confirmed discrimination incidents — worker vs customer vs other | GRI 406-1 / XX.10.3 | QUANTITATIVE | 30% | `score_quantitative()` — 1.0 if disclosed (even if zero), 0 if not |
| 3 | Diversity of governance bodies and employees | GRI 405-1 / XX.10.2 | QUANTITATIVE | 20% | `score_quantitative()` |

---

#### FIN-S4: Health & Safety (8% of S)

**FRA KPIs (S4):** 3 items

| # | Metric | Code | Type | Weight | Scoring |
|---|--------|------|------|--------|---------|
| 1 | OHS policy existence and management system scope | FRA-S4 / GRI 403-1 | BINARY | 25% | `score_binary()` |
| 2 | Work-related injury and fatality rates | FRA-S4 / GRI 403-9 | QUANTITATIVE | 35% | `score_quantitative()` |
| 3 | Training hours on E/S/health topics | FRA-S4 / GRI 403-5,6 | QUANTITATIVE | 25% | `score_quantitative()` |
| 4 | % workers covered by OHS management system | GRI 403-8 | QUANTITATIVE | 15% | `score_quantitative()` |

---

#### FIN-S5: Child & Forced Labor (6% of S)

**FRA KPIs (S5):** 2 binary items

| # | Metric | Code | Type | Weight | Scoring |
|---|--------|------|------|--------|---------|
| 1 | Child/forced labor prohibition policy published | FRA-S5 / GRI 408-1, 409-1 | BINARY | 50% | `score_binary()` |
| 2 | Policy coverage of suppliers and vendors | FRA-S5 | BINARY | 50% | `score_binary()` |

---

#### FIN-S6: Labor Rights (6% of S)

**FRA KPIs (S6):** 2 items

| # | Metric | Code | Type | Weight | Scoring |
|---|--------|------|------|--------|---------|
| 1 | ILO core convention commitment beyond Egyptian Labor Code | FRA-S6 / GRI 407-1, 412-1 | BINARY + QUALITATIVE | 60% | `score_q_plus_ql(q_weight=0.4, ql_weight=0.6)` |
| 2 | Supplier social assessment (labor rights coverage) | GRI 414-1 | QUALITATIVE | 40% | `score_qualitative(criteria=['supplier screening','labor rights','social audit'])` |

---

#### FIN-S7: Financial Health & Inclusion (22% of S)

**FRA KPIs:** None (Stage 1). Flag as Stage 2 readiness item.

| # | Metric | Code | Type | Weight | Scoring |
|---|--------|------|------|--------|---------|
| 1 | Identified underserved customer groups and selection methodology | GRI XX.5.2 | QUALITATIVE | 18% | `score_qualitative(criteria=['customer groups','underserved','selection process','methodology'])` |
| 2 | Products/services for underserved groups; financial education count | GRI XX.5.3 | Q+QL | 18% | `score_q_plus_ql()` |
| 3 | Complaints on financial health & inclusion — by type, trend | GRI XX.5.7 | QUANTITATIVE | 16% | `score_quantitative()` |
| 4 | # complaints filed; % with monetary/non-monetary relief | SASB FN-CF-270a.4 | QUANTITATIVE | 14% | `score_quantitative()` |
| 5 | % MSMEs with outstanding loan/credit or deposit account | GRI XX.5.5 | QUANTITATIVE | 12% | `score_quantitative()` |
| 6 | Banking access points in low-income/rural areas | GRI XX.5.8 | QUANTITATIVE | 12% | `score_quantitative()` |
| 7 | Approval rates for credit and pre-paid products | SASB FN-CF-270a.2 | QUANTITATIVE | 10% | `score_quantitative()` |

---

#### FIN-S8: Customer Privacy & Data Security (18% of S)

**FRA KPIs:** Partial (G4 covers governance — data privacy scored here for operational outcomes)

| # | Metric | Code | Type | Weight | Scoring |
|---|--------|------|------|--------|---------|
| 1 | # data breaches; % involving personal data; # account holders affected | SASB FN-CF-230a.1 | QUANTITATIVE | 32% | `score_quantitative()` |
| 2 | Substantiated complaints — leaks/losses; total customers affected; % retail | GRI 418-1 / XX.6.2 | QUANTITATIVE | 28% | `score_quantitative()` |
| 3 | Card fraud losses — card-not-present vs card-present | SASB FN-CF-230a.2 | QUANTITATIVE | 18% | `score_quantitative()` |
| 4 | # account holders whose data used for secondary purposes | SASB FN-CF-220a.1 | QUANTITATIVE | 14% | `score_quantitative()` |
| 5 | Monetary losses from customer privacy legal proceedings | SASB FN-CF-220a.2 | QUANTITATIVE | 8% | `score_quantitative()` |

---

#### FIN-S9: Marketing, Labeling & Fair Advice (12% of S)

**FRA KPIs:** None (Stage 1). Flag as Stage 2 readiness item.

| # | Metric | Code | Type | Weight | Scoring |
|---|--------|------|------|--------|---------|
| 1 | Monetary losses from legal proceedings on marketing/communication | SASB FN-IN-270a.1 | QUANTITATIVE | 35% | `score_quantitative()` |
| 2 | Non-compliance incidents — product information & labeling | GRI 417-2 / XX.7.2 | QUANTITATIVE | 25% | `score_quantitative()` |
| 3 | Complaints-to-claims ratio (external dispute resolution) | SASB FN-IN-270a.2 | QUANTITATIVE | 20% | `score_quantitative()` |
| 4 | Non-compliance incidents — marketing communications | GRI 417-3 / XX.7.3 | QUANTITATIVE | 20% | `score_quantitative()` |

---

### 3.4 Governance Pillar — Financial Sector (Weight: 35%)

#### Topic Weights within G Pillar

| Topic ID | Topic | Weight | FRA KPI | Framework |
|----------|-------|--------|---------|-----------|
| FIN-G1 | Board diversity | 15% | G1 | FRA + GRI 405 |
| FIN-G2 | Anti-bribery & corruption | 20% | G2 | FRA + GRI 205 |
| FIN-G3 | Ethics & code of conduct | 12% | G3 | FRA + GRI 102 |
| FIN-G4 | Data privacy governance | 18% | G4 | FRA + GRI 418 + SASB |
| FIN-G5 | Sustainability reporting & disclosure | 20% | G5 | FRA (6 KPIs) |
| FIN-G6 | External assurance | 15% | G6 | FRA + GRI 102 |

---

#### FIN-G1: Board Diversity (15% of G)

**FRA KPIs (G1):** 2 quantitative items

| # | Metric | Code | Type | Weight | Scoring |
|---|--------|------|------|--------|---------|
| 1 | % board seats by gender | FRA-G1 / GRI 405-1 | QUANTITATIVE | 40% | `score_quantitative()` |
| 2 | % committee chair positions by gender | FRA-G1 / GRI 405-1 | QUANTITATIVE | 30% | `score_quantitative()` |
| 3 | Board diversity beyond gender (independence, tenure, expertise) | GRI 405-1 | QUALITATIVE | 30% | `score_qualitative(criteria=['independent directors','tenure','expertise','age diversity'])` |

---

#### FIN-G2: Anti-Bribery & Corruption (20% of G)

**FRA KPIs (G2):** 1 binary item

| # | Metric | Code | Type | Weight | Scoring |
|---|--------|------|------|--------|---------|
| 1 | Anti-corruption/bribery code published and active | FRA-G2 / GRI 102, 103 | BINARY | 25% | `score_binary()` |
| 2 | Confirmed corruption & financial crime incidents | GRI 205-3 / XX.19.4 | QUANTITATIVE | 35% | `score_quantitative()` |
| 3 | Monetary value of customer funds lost to financial crime | GRI XX.19.5 | QUANTITATIVE | 25% | `score_quantitative()` |
| 4 | Operations assessed for corruption risk; anti-corruption training | GRI 205-1,2 | Q+QL | 15% | `score_q_plus_ql()` |

---

#### FIN-G3: Ethics & Code of Conduct (12% of G)

**FRA KPIs (G3):** 1 binary item

| # | Metric | Code | Type | Weight | Scoring |
|---|--------|------|------|--------|---------|
| 1 | Ethics/code of conduct published and enforced | FRA-G3 / GRI 102, 103 | BINARY | 60% | `score_binary()` |
| 2 | Mechanisms for advice and ethical concerns (whistleblower) | GRI 102-17 | QUALITATIVE | 40% | `score_qualitative(criteria=['whistleblower','ethics hotline','reporting mechanism','anonymity'])` |

---

#### FIN-G4: Data Privacy Governance (18% of G)

**FRA KPIs (G4):** 2 items

| # | Metric | Code | Type | Weight | Scoring |
|---|--------|------|------|--------|---------|
| 1 | Egyptian PDPL compliance + international framework adoption | FRA-G4 / GRI 103 | BINARY + QUALITATIVE | 45% | `score_q_plus_ql(q_weight=0.5, ql_weight=0.5)` |
| 2 | Cybersecurity approach; third-party data policy; analytics governance | GRI XX.6.1 | QUALITATIVE | 35% | `score_qualitative(criteria=['cybersecurity','encryption','third-party','data governance','PDPL'])` |
| 3 | Approach to identifying and addressing data security risks | SASB FN-CF-230a.3 | QUALITATIVE | 20% | `score_qualitative(criteria=['risk identification','data security','incident response'])` |

---

#### FIN-G5: Sustainability Reporting & Disclosure (20% of G)

**FRA KPIs (G5):** 6 items — highest FRA G-topic coverage

| # | Metric | Code | Type | Weight | Scoring |
|---|--------|------|------|--------|---------|
| 1 | Sustainability report published (framework used) | FRA-G5 | BINARY + QUALITATIVE | 25% | `score_q_plus_ql()` — bonus if GRI/SASB/IIRC cited |
| 2 | SDG alignment — goals identified, targets set, progress tracked | FRA-G5 | QUALITATIVE | 20% | `score_qualitative(criteria=['SDG','sustainable development goals','targets','progress'])` |
| 3 | Corporate responsibility commitment and community investment policy | FRA-G5 | BINARY | 20% | `score_binary()` |
| 4 | Participation in public-private community development initiatives | FRA-G5 | BINARY | 15% | `score_binary()` |
| 5 | Political contributions and public policy engagement | GRI 415-1 / XX.22.2 | QUANTITATIVE | 20% | `score_quantitative()` |

---

#### FIN-G6: External Assurance (15% of G)

**FRA KPIs (G6):** 1 binary item  
**Special role:** Acts as reliability multiplier on composite score (+5 points bonus)

| # | Metric | Code | Type | Weight | Scoring |
|---|--------|------|------|--------|---------|
| 1 | Third-party assurance of ESG disclosures — scope and standard | FRA-G6 / GRI 102-56 | BINARY + QUALITATIVE | 60% | `score_q_plus_ql()` — 0 if absent, 0.5 if partial scope, 1.0 if full |
| 2 | Assurance standard used and assurer identity | GRI 102-56 | QUALITATIVE | 40% | `score_qualitative(criteria=['assurance standard','independent assurer','ISAE 3000','scope'])` |

---

## 4. Manufacturing Sector Scoring

**Target:** Egyptian manufacturing companies (chemicals, food & beverage, building materials, textiles, metals)  
**SASB codes:** EM-MM (Metals & Mining), RT-CH (Chemicals), FB-AG (Food/Bev/Tobacco), CG-HP (Household/Personal Products)  
**GRI:** Sector-specific standards per sub-industry + GRI 300/400 universal series

### 4.1 Pillar Weights & Rationale

| Pillar | Weight | Rationale |
|--------|--------|-----------|
| **Environmental (E)** | **45%** | Dominant pillar for manufacturing. Direct emissions, water consumption, hazardous waste, and energy intensity are operational realities — not indirect/financed exposures. FRA E1–E5 maps directly. Egyptian manufacturers face water scarcity and energy subsidy reform pressures. |
| **Social (S)** | **30%** | Supply chain labor, occupational safety (high fatality risk in manufacturing), and community impacts are material. Lower than Financial sector because customer-facing topics (financial inclusion, data privacy) do not apply. |
| **Governance (G)** | **25%** | FRA G-topics apply equally, but governance risk profile is less severe than financial sector. Anti-corruption (procurement, government contracts) and supply chain governance are the key topics. |

**Derivation formula:**

```
W_E = (FRA_E_topics / FRA_total) × 0.4  +  Sector_E_materiality × 0.6
    = (5/16) × 0.4  +  0.63 × 0.6  = 0.125 + 0.38  ≈ 0.45  ✓

W_S = (FRA_S_topics / FRA_total) × 0.4  +  Sector_S_materiality × 0.6
    = (5/16) × 0.4  +  0.23 × 0.6  = 0.125 + 0.14  ≈ 0.30  ✓

W_G = (FRA_G_topics / FRA_total) × 0.4  +  Sector_G_materiality × 0.6
    = (6/16) × 0.4  +  0.15 × 0.6  = 0.15 + 0.09   ≈ 0.25  ✓
```

---

### 4.2 Environmental Pillar — Manufacturing Sector (Weight: 45%)

#### Topic Weights within E Pillar

| Topic ID | Topic | Weight | FRA KPI | Key Standards |
|----------|-------|--------|---------|---------------|
| MFG-E1 | Environmental governance & policy | 15% | E1 | FRA + GRI 102 |
| MFG-E2 | GHG emissions (Scope 1/2/3) | 25% | E2 | FRA + GRI 305 + SASB sector |
| MFG-E3 | Energy consumption & intensity | 20% | E3 | FRA + GRI 302 |
| MFG-E4 | Water withdrawal & discharge | 18% | E4 | FRA + GRI 303 + GRI 306 |
| MFG-E5 | Waste & hazardous materials | 15% | E5 | FRA + GRI 306 |
| MFG-E6 | Biodiversity & land use | 7% | — | GRI 304 |

**Key difference from Financial sector:**  
MFG-E2 (GHG) takes only 25% vs FIN-E2's 25% despite identical weight because manufacturing Scope 1 is direct (smokestacks, furnaces) — easier to extract and verify. MFG-E4 Water takes 18% (vs FIN-E4's 15%) because water scarcity is an operational risk for Egyptian manufacturing, not just a reporting exercise. MFG-E6 Biodiversity (7%) has no FRA KPI but is added because manufacturing sites frequently affect land and ecosystems.

---

#### MFG-E1: Environmental Governance & Policy (15% of E)

Same FRA E1 structure as Financial sector. Identical scoring functions apply.

| # | Metric | Code | Type | Weight | Scoring |
|---|--------|------|------|--------|---------|
| 1 | E&S policy published | FRA-E1.1 / GRI 102-19 | BINARY | 30% | `score_binary()` |
| 2 | Risk identification and assessment process | FRA-E1.3 / GRI 102-29 | QUALITATIVE | 30% | `score_qualitative(criteria=['EIA','environmental impact','risk register','ISO 14001'])` |
| 3 | Sub-policies for waste, water, energy, recycling | FRA-E1.4 | BINARY×4 | 25% | `count_of_present / 4` |
| 4 | GHG targets set and disclosed | FRA-E1.5 | BINARY+QUANT | 10% | `score_q_plus_ql()` |
| 5 | ISO 14001 or equivalent certification | FRA-E1.6 | BINARY | 5% | `score_binary()` — higher weight than Financial because certification is operationally expected in manufacturing |

---

#### MFG-E2: GHG Emissions (25% of E)

**Manufacturing-specific:** Scope 1 dominates (combustion, process emissions). SASB codes vary by sub-sector.

| # | Metric | Code | Type | Weight | Scoring |
|---|--------|------|------|--------|---------|
| 1 | Scope 1 GHG emissions — metric tons CO₂e | FRA-E2 / GRI 305-1 | QUANTITATIVE | 35% | `score_quantitative()` |
| 2 | Scope 2 GHG emissions (market-based and location-based) | GRI 305-2 | QUANTITATIVE | 20% | `score_quantitative()` |
| 3 | Scope 3 GHG emissions — relevant categories | GRI 305-3 | QUANTITATIVE | 20% | `score_quantitative()` — partial credit by category count |
| 4 | GHG emissions intensity (CO₂e per unit of production) | GRI 305-4 | QUANTITATIVE | 15% | `score_quantitative()` |
| 5 | GHG reduction initiatives and targets | GRI 305-5 | QUALITATIVE | 10% | `score_qualitative(criteria=['reduction target','initiative','timeline','baseline year'])` |

> **GHG intensity scoring:**
> ```python
> def score_ghg_intensity(intensity: float, sector_benchmark: float) -> float:
>     """
>     Lower emissions intensity = better score.
>     intensity: company's CO₂e per unit of production
>     sector_benchmark: sector median intensity
>     """
>     if intensity is None: return 0.0
>     if sector_benchmark is None: return 1.0 if intensity > 0 else 0.8  # existence only
>     return min(sector_benchmark / intensity, 1.0) if intensity > 0 else 1.0
> ```

---

#### MFG-E3: Energy Consumption & Intensity (20% of E)

| # | Metric | Code | Type | Weight | Scoring |
|---|--------|------|------|--------|---------|
| 1 | Total energy consumed (GJ) — by source | FRA-E3 / GRI 302-1 | QUANTITATIVE | 35% | `score_quantitative()` |
| 2 | Energy from non-renewable vs renewable sources (%) | FRA-E3 / GRI 302-1 | QUANTITATIVE | 25% | `score_quantitative()` — score renewable % / industry avg |
| 3 | Energy intensity (GJ per unit of production or revenue) | GRI 302-3 | QUANTITATIVE | 25% | `score_ghg_intensity()` adapted for energy |
| 4 | Energy reduction initiatives and targets | GRI 302-4 | QUALITATIVE | 15% | `score_qualitative(criteria=['energy efficiency','reduction','target','initiative'])` |

---

#### MFG-E4: Water Withdrawal & Discharge (18% of E)

**Manufacturing-specific:** Water intensity and effluent quality are critical for Egyptian industry (Nile basin concerns).

| # | Metric | Code | Type | Weight | Scoring |
|---|--------|------|------|--------|---------|
| 1 | Total water withdrawn by source (m³) | FRA-E4 / GRI 303-3 | QUANTITATIVE | 30% | `score_quantitative()` |
| 2 | Total water consumed (m³) | FRA-E4 / GRI 303-5 | QUANTITATIVE | 25% | `score_quantitative()` |
| 3 | Water discharge — total volume and quality | GRI 303-4 | QUANTITATIVE | 25% | `score_quantitative()` |
| 4 | % operations in water-stressed areas | GRI 303-2 | QUALITATIVE | 20% | `score_qualitative(criteria=['water stress','water risk','water scarcity','AQUEDUCT','WRI'])` |

---

#### MFG-E5: Waste & Hazardous Materials (15% of E)

| # | Metric | Code | Type | Weight | Scoring |
|---|--------|------|------|--------|---------|
| 1 | Total waste generated by type and disposal method (metric tons) | FRA-E5 / GRI 306-3 | QUANTITATIVE | 35% | `score_quantitative()` |
| 2 | Hazardous waste generated and disposal method | GRI 306-3 (hazardous) | QUANTITATIVE | 30% | `score_quantitative()` |
| 3 | Waste recycled/reclaimed (% of total) | FRA-E5 / GRI 306-4,5 | QUANTITATIVE | 20% | `score_quantitative()` |
| 4 | Significant spills — number and volume | GRI 306-3 | QUANTITATIVE | 15% | `score_quantitative()` — 1.0 if zero spills disclosed, not if absent |

---

#### MFG-E6: Biodiversity & Land Use (7% of E)

**FRA KPIs:** None. GRI 304 only.

| # | Metric | Code | Type | Weight | Scoring |
|---|--------|------|------|--------|---------|
| 1 | Operations in or adjacent to protected areas or high biodiversity value areas | GRI 304-1 | QUALITATIVE | 50% | `score_qualitative(criteria=['protected area','biodiversity','IUCN','habitat'])` |
| 2 | Significant impacts on biodiversity | GRI 304-2 | QUALITATIVE | 30% | `score_qualitative(criteria=['species impacted','habitat change','mitigation'])` |
| 3 | IUCN Red List species affected | GRI 304-4 | QUANTITATIVE | 20% | `score_quantitative()` |

---

### 4.3 Social Pillar — Manufacturing Sector (Weight: 30%)

#### Topic Weights within S Pillar

| Topic ID | Topic | Weight | FRA KPI | Key Standards |
|----------|-------|--------|---------|---------------|
| MFG-S1 | Gender diversity & pay equity | 10% | S1 | FRA + GRI 405 |
| MFG-S2 | Employee turnover | 7% | S2 | FRA + GRI 401 |
| MFG-S3 | Non-discrimination | 7% | S3 | FRA + GRI 406 |
| MFG-S4 | Occupational health & safety | 28% | S4 | FRA + GRI 403 |
| MFG-S5 | Child & forced labor | 10% | S5 | FRA + GRI 408/409 |
| MFG-S6 | Labor rights & supply chain | 15% | S6 | FRA + GRI 407/412/414 |
| MFG-S7 | Local communities & economic impact | 13% | — | GRI 413 + GRI 201 |
| MFG-S8 | Training & development | 10% | — | GRI 404 |

**Key difference from Financial sector:**  
MFG-S4 (OHS) takes 28% vs FIN-S4's 8% — manufacturing has genuine fatality risk (machinery, chemicals, confined spaces). MFG-S5 (Child/Forced Labor) takes 10% vs FIN-S5's 6% — manufacturing supply chains are higher risk. Financial sector's FIN-S7/S8/S9 customer-focused topics are replaced by MFG-S7 (community) and MFG-S8 (training).

---

#### MFG-S4: Occupational Health & Safety (28% of S)

**Most material S topic in manufacturing.**

| # | Metric | Code | Type | Weight | Scoring |
|---|--------|------|------|--------|---------|
| 1 | Work-related fatality rate | FRA-S4 / GRI 403-9 | QUANTITATIVE | 25% | `score_fatality_rate()` |
| 2 | Work-related injury rate (TRIR) | GRI 403-9 | QUANTITATIVE | 20% | `score_quantitative()` — lower_better |
| 3 | Work-related ill health rate | GRI 403-10 | QUANTITATIVE | 15% | `score_quantitative()` |
| 4 | OHS management system — scope and certification | FRA-S4 / GRI 403-1 | BINARY+QUALITATIVE | 15% | `score_q_plus_ql()` |
| 5 | Training hours on health and safety | FRA-S4 / GRI 403-5 | QUANTITATIVE | 10% | `score_quantitative()` |
| 6 | % workers covered by OHS system | GRI 403-8 | QUANTITATIVE | 8% | `score_quantitative()` |
| 7 | OHS worker participation and consultation | GRI 403-4 | QUALITATIVE | 7% | `score_qualitative(criteria=['worker committee','consultation','joint OHS committee'])` |

> **Fatality rate scoring:**
> ```python
> def score_fatality_rate(fatalities: int, total_workers: int) -> float:
>     """
>     Scoring rewards disclosure AND penalizes fatalities.
>     If not disclosed → 0.0
>     If disclosed:
>       0 fatalities → 1.0
>       1 fatality per 1000 workers → 0.7
>       2+ per 1000 → scaled down to 0.0 at 5+ per 1000
>     """
>     if fatalities is None or total_workers is None: return 0.0
>     if total_workers == 0: return 0.0
>     rate_per_1000 = (fatalities / total_workers) * 1000
>     if rate_per_1000 == 0: return 1.0
>     return max(0.0, 1.0 - (rate_per_1000 / 5.0))
> ```

---

#### MFG-S6: Labor Rights & Supply Chain (15% of S)

**Manufacturing-specific:** Deeper supply chain exposure than financial sector.

| # | Metric | Code | Type | Weight | Scoring |
|---|--------|------|------|--------|---------|
| 1 | ILO convention commitment beyond Egyptian Labor Code | FRA-S6 / GRI 407-1 | BINARY+QUALITATIVE | 35% | `score_q_plus_ql()` |
| 2 | Human rights assessment — operations assessed (%) | GRI 412-1 | QUANTITATIVE | 25% | `score_quantitative()` |
| 3 | Supplier screening for social criteria | GRI 414-1 | QUALITATIVE | 25% | `score_qualitative(criteria=['supplier audit','social criteria','labor rights','supplier code'])` |
| 4 | Supplier coverage of child/forced labor policy | FRA-S5 extension | BINARY | 15% | `score_binary()` |

---

#### MFG-S7: Local Communities & Economic Impact (13% of S)

**FRA KPIs:** None directly. Mapped to FRA G5 community investment policy.

| # | Metric | Code | Type | Weight | Scoring |
|---|--------|------|------|--------|---------|
| 1 | Operations with significant community impact and engagement | GRI 413-1 | QUALITATIVE | 40% | `score_qualitative(criteria=['community engagement','stakeholder','grievance mechanism','impact assessment'])` |
| 2 | Direct economic value generated and distributed (wages, taxes, community) | GRI 201-1 | QUANTITATIVE | 35% | `score_quantitative()` |
| 3 | Operations with negative community impacts | GRI 413-2 | QUANTITATIVE | 25% | `score_quantitative()` — 1.0 if disclosed, including zero |

---

#### MFG-S8: Training & Development (10% of S)

| # | Metric | Code | Type | Weight | Scoring |
|---|--------|------|------|--------|---------|
| 1 | Average training hours per employee per year | GRI 404-1 | QUANTITATIVE | 50% | `score_quantitative()` |
| 2 | % employees receiving regular performance reviews | GRI 404-3 | QUANTITATIVE | 30% | `score_quantitative()` |
| 3 | Programs for upgrading employee skills | GRI 404-2 | QUALITATIVE | 20% | `score_qualitative(criteria=['upskilling','training program','career development','learning'])` |

---

### 4.4 Governance Pillar — Manufacturing Sector (Weight: 25%)

#### Topic Weights within G Pillar

| Topic ID | Topic | Weight | FRA KPI | Key Standards |
|----------|-------|--------|---------|---------------|
| MFG-G1 | Board diversity | 15% | G1 | FRA + GRI 405 |
| MFG-G2 | Anti-bribery & corruption | 25% | G2 | FRA + GRI 205 |
| MFG-G3 | Ethics & code of conduct | 12% | G3 | FRA + GRI 102 |
| MFG-G4 | Supply chain governance | 18% | — | GRI 308 + GRI 414 |
| MFG-G5 | Sustainability reporting & disclosure | 18% | G5 | FRA |
| MFG-G6 | External assurance | 12% | G6 | FRA + GRI 102 |

**Key difference from Financial sector:**  
MFG-G4 Supply Chain Governance (18%) replaces FIN-G4 Data Privacy — manufacturing's governance risk is procurement corruption and supplier ESG, not data privacy. MFG-G2 Anti-corruption takes 25% (vs 20% in Financial) because Egyptian manufacturing faces government contract procurement corruption as a primary risk.

---

#### MFG-G4: Supply Chain Governance (18% of G)

**FRA KPIs:** None. GRI 308 + GRI 414.

| # | Metric | Code | Type | Weight | Scoring |
|---|--------|------|------|--------|---------|
| 1 | % new suppliers screened for environmental criteria | GRI 308-1 | QUANTITATIVE | 30% | `score_quantitative()` |
| 2 | Negative environmental impacts in supply chain | GRI 308-2 | QUALITATIVE | 25% | `score_qualitative(criteria=['supplier audit','environmental impact','corrective action'])` |
| 3 | % new suppliers screened for social criteria | GRI 414-1 | QUANTITATIVE | 25% | `score_quantitative()` |
| 4 | Negative social impacts in supply chain | GRI 414-2 | QUALITATIVE | 20% | `score_qualitative(criteria=['supplier labor','human rights','social audit','remediation'])` |

---

## 5. Metric Scoring Functions

### 5.1 Complete Function Reference

```python
# ─── scoring_engine.py ───────────────────────────────────────────────────────

from typing import Optional, Union
import re


def score_binary(value) -> float:
    if value is None: return 0.0
    if isinstance(value, bool): return 1.0 if value else 0.0
    normalized = str(value).strip().lower()
    positive = {'yes', 'true', '1', 'oui', 'نعم', 'да', 'present', 'available'}
    return 1.0 if normalized in positive else 0.0


def score_quantitative(
    value,
    benchmark: Optional[float] = None,
    direction: str = 'higher_better'
) -> float:
    if value is None or str(value).strip() == '': return 0.0
    try:
        v = float(str(value).replace(',', ''))
    except (ValueError, TypeError):
        return 0.0
    if benchmark is None:
        return 1.0 if v != 0 else 0.8
    b = float(benchmark)
    if b == 0: return 1.0 if v == 0 else 0.0
    if direction == 'higher_better':
        return min(v / b, 1.0)
    else:
        return min(b / v, 1.0) if v > 0 else 1.0


def score_qualitative(
    disclosure: Optional[str],
    completeness_criteria: list[str],
    partial_threshold: float = 0.25,
    full_threshold: float = 0.75
) -> float:
    if not disclosure or len(disclosure.strip()) == 0: return 0.0
    if not completeness_criteria: return 1.0
    text = disclosure.lower()
    matched = sum(1 for c in completeness_criteria if c.lower() in text)
    ratio = matched / len(completeness_criteria)
    if ratio >= full_threshold: return 1.0
    if ratio >= partial_threshold: return 0.5
    return 0.0


def score_q_plus_ql(
    quantitative_value,
    qualitative_disclosure: Optional[str],
    completeness_criteria: list[str],
    q_weight: float = 0.6,
    ql_weight: float = 0.4
) -> float:
    assert abs(q_weight + ql_weight - 1.0) < 0.001
    q = score_quantitative(quantitative_value)
    ql = score_qualitative(qualitative_disclosure, completeness_criteria)
    return q * q_weight + ql * ql_weight


def score_pay_ratio(ratio: Optional[float]) -> float:
    if ratio is None: return 0.0
    return max(0.0, 1.0 - abs(ratio - 1.0))


def score_fatality_rate(
    fatalities: Optional[int],
    total_workers: Optional[int]
) -> float:
    if fatalities is None or total_workers is None: return 0.0
    if total_workers == 0: return 0.0
    rate = (fatalities / total_workers) * 1000
    if rate == 0: return 1.0
    return max(0.0, 1.0 - rate / 5.0)


def score_ghg_intensity(
    intensity: Optional[float],
    sector_benchmark: Optional[float]
) -> float:
    if intensity is None: return 0.0
    if sector_benchmark is None:
        return 1.0 if intensity > 0 else 0.8
    return min(sector_benchmark / intensity, 1.0) if intensity > 0 else 1.0


def score_topic(metrics: list[dict]) -> float:
    total_weight = sum(m['weight'] for m in metrics)
    assert abs(total_weight - 1.0) < 0.001, f"Weights sum to {total_weight}, not 1.0"
    return sum(m['score'] * m['weight'] for m in metrics)


def score_pillar(topics: list[dict]) -> float:
    total_weight = sum(t['weight'] for t in topics)
    assert abs(total_weight - 1.0) < 0.001, f"Weights sum to {total_weight}, not 1.0"
    return sum(t['score'] * t['weight'] for t in topics)


def score_composite(
    pillar_scores: dict,
    pillar_weights: dict,
    fra_gate_passed: bool,
    external_assurance: bool,
    assurance_bonus: float = 0.05
) -> dict:
    assert abs(sum(pillar_weights.values()) - 1.0) < 0.001
    raw = sum(pillar_scores[p] * pillar_weights[p] for p in pillar_scores)
    score_100 = raw * 100
    gated = score_100 if fra_gate_passed else min(score_100, 60.0)
    final = min(gated + (assurance_bonus * 100 if external_assurance else 0), 100.0)
    return {
        'raw_score': round(score_100, 2),
        'fra_gate_passed': fra_gate_passed,
        'gated_score': round(gated, 2),
        'assurance_bonus_applied': external_assurance,
        'final_score': round(final, 2),
        'grade': _to_grade(final)
    }


def _to_grade(score: float) -> str:
    if score >= 85: return 'A'
    if score >= 70: return 'B'
    if score >= 55: return 'C'
    if score >= 40: return 'D'
    return 'F'
```

---

## 6. Composite Score Calculation

### 6.1 Full Worked Example — Financial Sector

**Company:** Egyptian Microfinance Institution (hypothetical)  
**Sector:** Financial (FN-CF / FN-IN)

```
─── Input: Pillar Scores (from pillar aggregation) ──────────────
  E_score = 0.62  (decent energy/carbon, no financed emissions)
  S_score = 0.54  (good gender diversity, weak financial inclusion)
  G_score = 0.78  (strong anti-corruption, good board, weak assurance)

─── Pillar Weights (Financial Sector) ──────────────────────────
  W_E = 0.25
  W_S = 0.40
  W_G = 0.35

─── Step 1: Weighted Sum ────────────────────────────────────────
  raw = (0.62 × 0.25) + (0.54 × 0.40) + (0.78 × 0.35)
      = 0.155 + 0.216 + 0.273
      = 0.644

  score_100 = 64.4

─── Step 2: FRA Gate Check ──────────────────────────────────────
  FRA mandatory KPIs present: 14/16  → fra_gate_passed = True
  (Gate only triggers if < 50% of FRA binary KPIs are present)

  gated_score = 64.4  (no cap applied)

─── Step 3: External Assurance ──────────────────────────────────
  external_assurance = False
  bonus = 0

─── Output ──────────────────────────────────────────────────────
  final_score = 64.4
  grade       = B
```

### 6.2 Full Worked Example — Manufacturing Sector

**Company:** Egyptian Cement Manufacturer (hypothetical)

```
─── Input: Pillar Scores ────────────────────────────────────────
  E_score = 0.71  (good emissions + energy, weak biodiversity)
  S_score = 0.65  (strong OHS reporting, weak community disclosure)
  G_score = 0.58  (ethics present, supply chain governance weak)

─── Pillar Weights (Manufacturing Sector) ───────────────────────
  W_E = 0.45
  W_S = 0.30
  W_G = 0.25

─── Step 1: Weighted Sum ────────────────────────────────────────
  raw = (0.71 × 0.45) + (0.65 × 0.30) + (0.58 × 0.25)
      = 0.3195 + 0.195 + 0.145
      = 0.6595

  score_100 = 65.95

─── Step 2: FRA Gate ────────────────────────────────────────────
  fra_gate_passed = True  (all binary KPIs present)
  gated_score = 65.95

─── Step 3: Assurance ───────────────────────────────────────────
  external_assurance = True  (+5 points)
  final_score = min(65.95 + 5, 100) = 70.95

─── Output ──────────────────────────────────────────────────────
  final_score = 70.95
  grade       = B
```

---

## 7. FRA Compliance Gate

### 7.1 Logic

The FRA compliance gate is a **hard cap**: if a company fails to disclose a minimum threshold of FRA Stage 1 KPIs, the composite score is capped at 60 regardless of strong GRI/SASB performance.

```python
def check_fra_gate(fra_kpi_results: dict) -> dict:
    """
    fra_kpi_results: {
      'E1': {'present': True, 'sub_kpis': 6, 'disclosed': 4},
      'E2': {'present': True, ...},
      ...
      'G6': {'present': False, ...}
    }

    Gate fails if:
    - Any MANDATORY FRA KPI is completely absent (binary = False AND no value)
    - OR fewer than 50% of total FRA KPIs are disclosed

    Mandatory FRA KPIs (cannot be absent):
      E1 (E&S policy), G2 (anti-corruption), G3 (ethics), G4 (data privacy)
    """
    MANDATORY = ['E1', 'G2', 'G3', 'G4']

    mandatory_pass = all(
        fra_kpi_results.get(k, {}).get('present', False)
        for k in MANDATORY
    )

    total_kpis = len(fra_kpi_results)
    disclosed = sum(1 for v in fra_kpi_results.values() if v.get('present', False))
    coverage_ratio = disclosed / total_kpis if total_kpis > 0 else 0

    gate_passed = mandatory_pass and coverage_ratio >= 0.50

    return {
        'gate_passed': gate_passed,
        'mandatory_pass': mandatory_pass,
        'coverage_ratio': round(coverage_ratio, 2),
        'missing_mandatory': [k for k in MANDATORY
                               if not fra_kpi_results.get(k, {}).get('present', False)],
        'total_disclosed': disclosed,
        'total_kpis': total_kpis
    }
```

### 7.2 FRA KPI Registry

| Code | Topic | Mandatory | Sub-KPI Count |
|------|-------|-----------|---------------|
| E1 | Environmental governance & policy | ✓ | 6 |
| E2 | Carbon emissions | | 1 |
| E3 | Energy usage | | 3 |
| E4 | Water usage | | 2 |
| E5 | Waste management | | 1 |
| S1 | Gender diversity & pay ratio | | 5 |
| S2 | Employee turnover | | 3 |
| S3 | Non-discrimination | | 1 |
| S4 | Health & safety | | 3 |
| S5 | Child & forced labor | | 2 |
| S6 | Labor rights | | 2 |
| G1 | Board diversity | | 2 |
| G2 | Anti-bribery & corruption | ✓ | 1 |
| G3 | Ethics & code of conduct | ✓ | 1 |
| G4 | Data privacy | ✓ | 2 |
| G5 | Sustainability reporting | | 6 |
| G6 | External assurance | | 1 |

---

## 8. Gap Analysis Output

### 8.1 Gap Score Function

```python
def generate_gap_analysis(
    topic_scores: dict,      # {'FIN-E1': 0.75, 'FIN-E2': 0.20, ...}
    topic_weights: dict,     # {'FIN-E1': 0.30, 'FIN-E2': 0.25, ...}
    pillar_weights: dict,    # {'E': 0.25, 'S': 0.40, 'G': 0.35}
    topic_to_pillar: dict    # {'FIN-E1': 'E', 'FIN-E2': 'E', ...}
) -> list[dict]:
    """
    Returns prioritized list of improvement opportunities,
    sorted by potential composite score impact (highest first).

    Impact = topic_weight × pillar_weight × (1 - current_score)
    """
    gaps = []
    for topic_id, current_score in topic_scores.items():
        pillar = topic_to_pillar[topic_id]
        t_weight = topic_weights[topic_id]
        p_weight = pillar_weights[pillar]
        potential_gain = t_weight * p_weight * (1 - current_score) * 100

        gaps.append({
            'topic_id': topic_id,
            'pillar': pillar,
            'current_score': round(current_score, 2),
            'topic_weight': t_weight,
            'pillar_weight': p_weight,
            'potential_gain_points': round(potential_gain, 2),
            'priority': 'HIGH' if potential_gain >= 3.0
                        else 'MEDIUM' if potential_gain >= 1.5
                        else 'LOW'
        })

    return sorted(gaps, key=lambda x: x['potential_gain_points'], reverse=True)
```

### 8.2 Stage 2 Readiness Flag

Topics with no FRA Stage 1 KPI are tagged for forward-looking reporting:

```python
FRA_STAGE_2_READINESS_TOPICS = {
    'financial': ['FIN-S7', 'FIN-S8', 'FIN-S9'],
    'manufacturing': ['MFG-E6', 'MFG-S7', 'MFG-S8', 'MFG-G4']
}
```

---

## 9. Weight Derivation Methodology

### 9.1 Three-Factor Weight Model

All weights (pillar, topic, metric) are derived from the same three-factor model, applied at different granularities:

```
Weight_i = α × Regulatory_Factor_i  +  β × Materiality_Factor_i  +  γ × Data_Factor_i

Where:
  α = 0.40  (regulatory prominence — FRA KPI count and enforcement priority)
  β = 0.40  (sector materiality — GRI topic depth + SASB metric count)
  γ = 0.20  (data availability — how extractable is this metric via NLP)

Constraints:
  Σ Weight_i = 1.0 within each level (pillar/topic/metric)
  All weights > 0
```

### 9.2 Regulatory Factor Derivation

```
Regulatory_Factor_i = FRA_sub_KPIs_i / Σ FRA_sub_KPIs_all_topics_in_level

Example (Financial E pillar topics):
  FIN-E1: 6 sub-KPIs / 13 total E KPIs = 0.46 → scaled to 0.30 after materiality blending
  FIN-E2: 1 sub-KPI / 13 = 0.08 → scaled to 0.25 (materiality elevates)
  FIN-E3: 3 / 13 = 0.23 → scaled to 0.20
  FIN-E4: 2 / 13 = 0.15 → scaled to 0.15
  FIN-E5: 1 / 13 = 0.08 → scaled to 0.10
```

### 9.3 Materiality Factor Derivation

```
Materiality_Factor_i = (GRI_disclosures_i + SASB_metrics_i × 1.5) / Σ across level

SASB metrics are weighted 1.5× because they are quantitative and investor-grade.

Example (Financial vs Manufacturing E pillar):
  Financial E materiality:
    GRI: 12 E-related disclosures (own ops only, financed is indirect)
    SASB: 4 FN-IN financed emissions metrics
    Score: (12 + 4×1.5) / total = 18/total → low relative to S

  Manufacturing E materiality:
    GRI: 28 E-related disclosures (direct ops — GRI 302, 303, 304, 305, 306)
    SASB: varies by sub-sector, avg 8 metrics
    Score: (28 + 8×1.5) / total = 40/total → much higher
    → Explains W_E = 0.45 for Manufacturing vs 0.25 for Financial
```

### 9.4 Data Availability Factor

```
Data_Factor_i = ease of NLP extraction from Arabic/English corporate reports

Scale:
  1.0 = always in structured tables (headcount, energy kWh, waste tons)
  0.7 = usually in dedicated ESG section
  0.5 = often in narrative, requires semantic extraction
  0.3 = rarely disclosed, requires multi-document inference
  0.0 = not typically in annual reports

Examples:
  Employee headcount by gender: 1.0  (HR table, always structured)
  GHG Scope 1 emissions: 0.9        (usually in environmental table)
  Financed emissions (SASB FN-IN-410c): 0.3  (rare, complex calculation)
  Community grievance mechanisms: 0.5  (narrative, inconsistent)
  Supplier audit coverage %: 0.4      (sometimes in supply chain section)
```

### 9.5 Sensitivity Checks

After applying the formula, weights are validated against two sensitivity checks:

**Check 1 — FRA alignment:** No FRA-covered topic should weight below 5% within its pillar.  
**Check 2 — materiality floor:** No metric with a SASB quantitative code should weight below 8% within its topic.

If either check fails, weights are adjusted proportionally and re-normalized.

---

## 10. Sector Comparison Summary

| Parameter | Financial Sector | Manufacturing Sector |
|-----------|-----------------|---------------------|
| E weight | 25% | 45% |
| S weight | 40% | 30% |
| G weight | 35% | 25% |
| E dominant topic | Climate / Financed Emissions (25%) | GHG Direct Emissions (25%) |
| S dominant topic | Financial Inclusion (22%) | OHS (28%) |
| G dominant topic | Anti-corruption (20%) + Sustainability Reporting (20%) | Anti-corruption (25%) |
| FRA gate threshold | ≥50% KPIs + 4 mandatory | ≥50% KPIs + 4 mandatory |
| Assurance bonus | +5 pts | +5 pts |
| SASB codes | FN-CF, FN-IN | EM-MM, RT-CH, FB-AG |
| Key sector-specific topics | Financed emissions, customer privacy, mis-selling | Biodiversity, supply chain governance, fatality rate |
| Stage 2 readiness topics | S7 (inclusion), S8 (data), S9 (marketing) | E6 (biodiversity), G4 (supply chain) |

---

*Document version: 1.0 — Generated for ESG Platform graduation project.*  
*Frameworks referenced: FRA Egypt ESG KPIs (March 2021), GRI Universal Standards 2021, GRI Banking Sector Standard (2022), SASB Standards 2023-12 (FN-CF, FN-IN).*
