from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.enums import ExtractionMethod, MetricStatus


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

    # GRI / framework codes
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

    # Provenance
    source_file: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    source_page: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # The exact text passage used for extraction — stored for few-shot correction loop
    evidence_chunk: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # "llm" | "questionnaire" | "manual"
    extraction_method: Mapped[ExtractionMethod] = mapped_column(
        Enum(ExtractionMethod), nullable=False
    )

    # Review fields (populated when a consultant approves/rejects)
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
