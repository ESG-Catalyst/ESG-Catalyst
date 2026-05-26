from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, DateTime, Enum, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.enums import ReportStatus


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    reporting_year: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[ReportStatus] = mapped_column(
        Enum(ReportStatus), nullable=False, default=ReportStatus.draft
    )
    # e.g. ["GRI", "FRA", "SASB"]
    frameworks: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    total_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    gri_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    fra_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    sasb_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # E/S/G pillar scores (0–100). Same numbers the PDF prints; written by
    # the pipeline task and re-written at report-generation time so the
    # dashboard and the PDF always read the same snapshot.
    environmental_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    social_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    governance_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    pdf_path: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
