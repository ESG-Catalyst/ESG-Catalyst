from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import (
    ExtractionMethod,
    FrameworkType,
    MetricDirection,
    MetricFramework,
    MetricStatus,
    MetricType,
    PillarType,
    SectorType,
)


# ---------------------------------------------------------------------------
# ExtractedMetricCreate / Update / Schema
# CANONICAL CONTRACT between pipeline, API, review UI, and report generator.
# NEVER deviate from these definitions without a full team discussion.
# ---------------------------------------------------------------------------

class ExtractedMetricCreate(BaseModel):
    """Fields required to persist a freshly extracted metric."""

    company_id: UUID
    report_id: UUID
    gri_code: str
    fra_code: str | None = None
    sasb_code: str | None = None
    label: str
    value: float | None = None
    unit: str | None = None
    original_value: str | None = None
    original_unit: str | None = None
    confidence: float
    status: MetricStatus = MetricStatus.extracted
    source_file: str | None = None
    source_page: int | None = None
    evidence_chunk: str | None = None
    extraction_method: ExtractionMethod
    note: str | None = None

    # Iteration 2 additions — finance-sector GRI + SASB support.
    # All optional / nullable, never break existing rows or extraction code.
    framework: MetricFramework | None = None
    metric_type: MetricType | None = None
    sector_standard_ref: str | None = None
    currency: str | None = None
    reporting_period_start: date | None = None
    reporting_period_end: date | None = None
    breakdown: dict[str, Any] | None = None

    # Metric-contract pillar / topic. Team-approved schema extension
    # (2026-05-18 diagnostic session — see CLAUDE.md session log).
    pillar: PillarType | None = None
    topic: str | None = None


class ExtractedMetricUpdate(BaseModel):
    """Fields a reviewer may change during the review workflow."""

    value: float | None = None
    unit: str | None = None
    status: MetricStatus | None = None
    note: str | None = None
    reviewer_id: UUID | None = None
    reviewed_at: datetime | None = None
    currency: str | None = None
    breakdown: dict[str, Any] | None = None


class ExtractedMetricSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    company_id: UUID
    report_id: UUID
    gri_code: str                  # e.g. "GRI 302-1"
    fra_code: str | None           # e.g. "FRA-36-SCOPE1"
    sasb_code: str | None          # e.g. "FN-CB-230a.1"
    label: str                     # "Energy consumption within org"
    value: float | None
    unit: str | None               # normalised: "GJ", "tCO2e", "m3"
    original_value: str | None     # raw value as found in doc
    original_unit: str | None      # raw unit as found in doc
    confidence: float              # 0.0 – 1.0
    status: MetricStatus           # extracted|ambiguous|missing|rejected|approved
    source_file: str | None
    source_page: int | None
    evidence_chunk: str | None     # the text passage used for extraction
    extraction_method: str         # "llm" | "questionnaire" | "manual"
    reviewer_id: UUID | None
    reviewed_at: datetime | None
    note: str | None
    created_at: datetime
    updated_at: datetime

    # Iteration 2 — finance-sector GRI + SASB additions.
    # Strictly additive + nullable; legacy rows simply have these as None.
    framework: MetricFramework | None = None
    metric_type: MetricType | None = None
    sector_standard_ref: str | None = None     # "XX.1.7" (GRI), "FN-IN-410c.1" (SASB)
    currency: str | None = None                # for monetary metrics: "EGP", "USD", ...
    reporting_period_start: date | None = None
    reporting_period_end: date | None = None
    breakdown: dict[str, Any] | None = None    # nested sub-values (e.g., by_sector, by_country)

    # Metric-contract pillar / topic. ``pillar`` mirrors the ORM PillarType
    # column ("E" | "S" | "G"); ``topic`` is the human-readable GRI / classifier
    # topic (e.g. "GRI 305"). Team-approved schema extension (2026-05-18).
    pillar: PillarType | None = None
    topic: str | None = None


# ---------------------------------------------------------------------------
# Scoring-engine schemas — added to support the new weight-aware scorer.
# These do NOT replace ExtractedMetricCreate / ExtractedMetricSchema; they
# carry the additional scoring-configuration fields defined in the ORM model.
# ---------------------------------------------------------------------------

class MetricBase(BaseModel):
    """Shared field definitions used by MetricCreate and MetricRead."""

    # ── Framework identification ───────────────────────────────────────────
    metric_code: str | None = None
    """Canonical code within the scoring weight registry, e.g. 'FRA-E1.1'."""

    framework_source: FrameworkType | None = None
    """Top-level framework: GRI | SASB | FRA | COMPOSITE."""

    sector: SectorType | None = None
    """FINANCIAL or MANUFACTURING — selects the pillar weight table."""

    pillar: PillarType | None = None
    """E, S, or G — determines pillar aggregation bucket."""

    topic_id: str | None = None
    """Topic bucket within the pillar, e.g. 'FIN-E1', 'MFG-S4'."""

    # ── Scoring configuration ──────────────────────────────────────────────
    metric_type: MetricType | None = None
    """BINARY | QUANTITATIVE | QUALITATIVE | Q_PLUS_QL — selects scoring fn."""

    weight_in_topic: float | None = Field(default=None, ge=0.0, le=1.0)
    """This metric's fractional weight within its topic (0.0–1.0)."""

    fra_required: bool = False
    """True if this is an FRA Stage 1 mandatory KPI (enforced by FRA gate)."""

    fra_kpi_code: str | None = None
    """Short FRA registry code, e.g. 'E1', 'G4'.  None for non-FRA metrics."""

    direction: MetricDirection | None = None
    """HIGHER_BETTER | LOWER_BETTER | NEUTRAL.  Only meaningful for QUANTITATIVE."""

    benchmark: float | None = None
    """Sector benchmark for Stage 2 quantitative scoring.  None → Stage 1 only."""

    # ── Qualitative scoring config ─────────────────────────────────────────
    completeness_criteria: list[str] | None = None
    """Keywords checked by score_qualitative() against the extracted disclosure."""

    q_weight: float = Field(default=0.6, ge=0.0, le=1.0)
    """Quantitative blend weight for Q_PLUS_QL metrics (default 0.6)."""

    ql_weight: float = Field(default=0.4, ge=0.0, le=1.0)
    """Qualitative blend weight for Q_PLUS_QL metrics (default 0.4)."""

    # ── Extraction linkage ─────────────────────────────────────────────────
    extraction_keywords: list[str] | None = None
    """Arabic/English hints for the indicator-aware chunk selector."""

    data_availability_score: float | None = Field(default=None, ge=0.0, le=1.0)
    """Ease of NLP extraction per spec §9.4 (0.0 = rarely disclosed, 1.0 = always structured)."""


class MetricCreate(MetricBase):
    """Schema for inserting a new scoring-aware metric definition.

    These are the *definition* records (weight registry rows) — not the
    per-extraction rows created by ExtractedMetricCreate.
    """

    metric_code: str                    # required on create
    sector: SectorType                  # required on create
    pillar: PillarType                  # required on create
    topic_id: str                       # required on create
    metric_type: MetricType             # required on create
    weight_in_topic: float = Field(ge=0.0, le=1.0)  # required on create


class MetricRead(MetricBase):
    """Full read schema including database-assigned fields.

    Returned by the weight-registry and metric-definition endpoints.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
    updated_at: datetime

    # Mirror all non-nullable ORM fields
    fra_required: bool
    q_weight: float
    ql_weight: float


# ---------------------------------------------------------------------------
# Scorer I/O schemas — used exclusively by the scoring engine.
# Decoupled from the ORM: the scorer receives and returns plain Pydantic models.
# ---------------------------------------------------------------------------

class MetricScoreInput(BaseModel):
    """Input to the per-metric scoring dispatcher (score_binary / quantitative /
    qualitative / q_plus_ql).

    The scorer reads metric_type to select the correct function, then uses
    the relevant subset of fields.
    """

    metric_code: str
    """Canonical identifier, e.g. 'FRA-E1.1'.  Used for logging and output."""

    metric_type: MetricType
    """Determines which scoring function is invoked."""

    extracted_value: Any | None = None
    """For BINARY: str/bool.  For QUANTITATIVE/Q_PLUS_QL: float.  For QUALITATIVE: None."""

    extracted_text: str | None = None
    """For QUALITATIVE/Q_PLUS_QL: the narrative disclosure extracted from the document."""

    benchmark: float | None = None
    """Stage 2 benchmark.  None → Stage 1 existence scoring for QUANTITATIVE."""

    direction: MetricDirection = MetricDirection.NEUTRAL
    """Scoring direction for QUANTITATIVE metrics.  Ignored for other types."""

    completeness_criteria: list[str] = Field(default_factory=list)
    """Keyword list for score_qualitative().  Empty list → presence alone = full score."""

    q_weight: float = Field(default=0.6, ge=0.0, le=1.0)
    """Quantitative blend weight for Q_PLUS_QL (must sum to 1.0 with ql_weight)."""

    ql_weight: float = Field(default=0.4, ge=0.0, le=1.0)
    """Qualitative blend weight for Q_PLUS_QL (must sum to 1.0 with q_weight)."""

    weight_in_topic: float = Field(default=0.0, ge=0.0, le=1.0)
    """This metric's fractional weight within its topic — passed through to MetricScoreOutput."""

    fra_required: bool = False
    """True if this is an FRA mandatory KPI — passed through to MetricScoreOutput."""


class MetricScoreOutput(BaseModel):
    """Per-metric result returned by the scoring engine.

    Consumed by the topic aggregator (score_topic) to compute the weighted sum.
    """

    metric_code: str
    """Mirrors MetricScoreInput.metric_code."""

    metric_type: MetricType
    """The scoring function that was applied."""

    raw_score: float = Field(ge=0.0, le=1.0)
    """0.0–1.0 result from the relevant scoring function."""

    weight_in_topic: float = Field(ge=0.0, le=1.0)
    """This metric's weight within its topic — used by score_topic()."""

    weighted_contribution: float
    """raw_score × weight_in_topic — pre-multiplied for the topic aggregator."""

    fra_required: bool
    """Propagated from MetricBase — consumed by check_fra_gate()."""

    scoring_notes: str | None = None
    """Optional diagnostic note, e.g. 'Stage 2 benchmark used', 'partial criteria match'."""