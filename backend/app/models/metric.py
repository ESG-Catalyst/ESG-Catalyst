from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
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


class ExtractedMetric(Base):
    """
    Central table — every ESG value extracted from a document lands here.
    Schema is the contract between pipeline, API, review UI, and report generator.
    Never remove or rename a column without a migration.
    """

    __tablename__ = "extracted_metrics"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    report_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("reports.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # ── GRI / framework codes ────────────────────────────────────────────────
    gri_code: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    fra_code: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    sasb_code: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Human-readable label, e.g. "Energy consumption within org"
    label: Mapped[str] = mapped_column(String(255), nullable=False)

    # Normalised value + unit (e.g. 12500.0, "GJ")
    value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    unit: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Raw value + unit exactly as found in the source document
    original_value: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    original_unit: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # 0.0 – 1.0; when in doubt, return lower confidence
    confidence: Mapped[float] = mapped_column(Float, nullable=False)

    # Workflow state: extracted → ambiguous|missing → rejected|approved
    status: Mapped[MetricStatus] = mapped_column(
        Enum(MetricStatus), nullable=False, default=MetricStatus.extracted
    )

    # ── Provenance ───────────────────────────────────────────────────────────
    source_file: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    source_page: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # The exact text passage used for extraction — stored for few-shot correction loop
    evidence_chunk: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # "llm" | "questionnaire" | "manual"
    extraction_method: Mapped[ExtractionMethod] = mapped_column(
        Enum(ExtractionMethod), nullable=False
    )

    # ── Review fields ────────────────────────────────────────────────────────
    # Populated when a consultant approves / rejects
    reviewer_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # ── Iteration 2 — finance-sector GRI + SASB additions ───────────────────
    # Strictly additive + nullable. Legacy rows have these as NULL.
    # For Postgres, JSON maps to JSONB-compatible; on SQLite it is TEXT.
    framework: Mapped[Optional[MetricFramework]] = mapped_column(
        Enum(MetricFramework), nullable=True, index=True
    )
    metric_type: Mapped[Optional[MetricType]] = mapped_column(
        Enum(MetricType), nullable=True
    )
    sector_standard_ref: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    currency: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    reporting_period_start: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    reporting_period_end: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    breakdown: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)

    # ── Iteration 2 / Scoring-engine additions ───────────────────────────────
    # Required by the ESG scoring framework spec (esg_scoring_framework.md).
    # All nullable / have defaults so existing rows continue to load unchanged.
    # Run scripts/migrate_extracted_metrics_scoring.py on existing Postgres DBs.

    # Canonical metric identifier within the scoring weight registry.
    # Examples: "FRA-E1.1", "GRI 305-1", "FN-CF-230a.1"
    metric_code: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True, index=True
    )

    # Top-level framework source — coarser than MetricFramework (which carries
    # fine-grained SASB sub-standard codes).
    framework_source: Mapped[Optional[FrameworkType]] = mapped_column(
        Enum(FrameworkType), nullable=True
    )

    # Sector determines which pillar weights and topic hierarchy apply.
    sector: Mapped[Optional[SectorType]] = mapped_column(
        Enum(SectorType), nullable=True, index=True
    )

    # ESG pillar: E | S | G (stored as single char matching PillarType values).
    pillar: Mapped[Optional[PillarType]] = mapped_column(
        Enum(PillarType), nullable=True, index=True
    )

    # Human-readable GRI / classifier topic for this metric, e.g. "GRI 305",
    # "GRI 401", "FRA". Distinct from topic_id (the scoring weight-registry
    # bucket). Part of the ExtractedMetric contract — the review UI and report
    # generator group metrics by pillar + topic.
    topic: Mapped[Optional[str]] = mapped_column(String(120), nullable=True, index=True)

    # Topic bucket within the pillar, e.g. "FIN-E1", "MFG-S4".
    # Used by the topic aggregator to group metrics and apply topic weights.
    topic_id: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, index=True)

    # This metric's fractional weight within its topic (must sum to 1.0 per topic).
    weight_in_topic: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # True if this is an FRA Stage 1 mandatory KPI (E1, G2, G3, G4 checked by
    # check_fra_gate()).  False / NULL = not mandatory.
    fra_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Short FRA KPI category code from the FRA registry (spec §7.2).
    # Examples: "E1", "G4", "S3".  NULL for non-FRA metrics.
    fra_kpi_code: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)

    # Scoring direction for QUANTITATIVE metrics (spec §2.1).
    # NULL / NEUTRAL means existence alone earns full score.
    direction: Mapped[Optional[MetricDirection]] = mapped_column(
        Enum(MetricDirection), nullable=True
    )

    # Sector benchmark value used by score_quantitative() Stage 2.
    # NULL → Stage 1 existence scoring only.
    benchmark: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Criteria list for score_qualitative() / score_q_plus_ql().
    # Stored as a JSON array of keyword strings checked against extracted_text.
    completeness_criteria: Mapped[Optional[list[str]]] = mapped_column(JSON, nullable=True)

    # Blend weights for Q_PLUS_QL metrics.  Defaults mirror spec §2.1.
    q_weight: Mapped[float] = mapped_column(Float, nullable=False, default=0.6)
    ql_weight: Mapped[float] = mapped_column(Float, nullable=False, default=0.4)

    # NLP extraction hints — Arabic and English keywords that suggest this
    # metric is present in a chunk.  Used by the indicator-aware chunk selector.
    extraction_keywords: Mapped[Optional[list[str]]] = mapped_column(JSON, nullable=True)

    # Data availability score per spec §9.4 (0.0 = never in reports,
    # 1.0 = always in structured tables).  Feeds the three-factor weight model.
    data_availability_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
