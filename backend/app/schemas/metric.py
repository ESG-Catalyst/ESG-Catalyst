from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.models.enums import ExtractionMethod, MetricFramework, MetricStatus, MetricType


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


# ---------------------------------------------------------------------------
# ExtractedMetricSchema — the canonical contract between pipeline, API,
# review UI, and report generator. NEVER deviate from this definition.
# ---------------------------------------------------------------------------
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