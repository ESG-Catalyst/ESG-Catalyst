"""Pipeline contracts — typed input/output schemas for the AI pipeline.

These are the inter-module contracts. No module imports from another
module's internals — all communication goes through these schemas.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class PipelineStage(str, Enum):
    queued = "queued"
    parsing = "parsing"
    chunking = "chunking"
    classifying = "classifying"
    extracting = "extracting"
    scoring = "scoring"
    complete = "complete"
    failed = "failed"


class PipelineInput(BaseModel):
    """Input contract for starting a pipeline run."""

    document_id: UUID
    company_id: UUID
    report_id: UUID
    indicator_codes: Optional[list[str]] = None


class PipelineState(BaseModel):
    """Real-time state of a running pipeline job."""

    job_id: str
    stage: PipelineStage
    message: str
    progress_pct: Optional[float] = None  # 0–100


class GapSummary(BaseModel):
    """Condensed gap item in the pipeline output."""

    code: str
    name: str
    status: str
    recommendation: str


class PipelineOutput(BaseModel):
    """Full result returned when a pipeline job completes."""

    document_id: UUID
    company_id: UUID
    report_id: UUID
    pages_parsed: int
    chunks_total: int
    chunks_relevant: int
    metrics_extracted: int
    metrics_total: int
    total_score: float
    gri_score: float
    environmental_score: float
    social_score: float
    governance_score: float
    benchmark_tier: str
    coverage_pct: float
    gaps: list[GapSummary]
