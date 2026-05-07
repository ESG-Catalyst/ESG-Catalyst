from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.models.enums import ReportStatus


class ReportCreate(BaseModel):
    company_id: UUID
    title: str
    reporting_year: int
    frameworks: list[str] = ["GRI"]


class ReportUpdate(BaseModel):
    title: str | None = None
    reporting_year: int | None = None
    status: ReportStatus | None = None
    frameworks: list[str] | None = None
    total_score: float | None = None
    gri_score: float | None = None
    fra_score: float | None = None
    sasb_score: float | None = None
    pdf_path: str | None = None


class ReportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    company_id: UUID
    title: str
    reporting_year: int
    status: ReportStatus
    frameworks: list[str]
    total_score: float | None
    gri_score: float | None
    fra_score: float | None
    sasb_score: float | None
    pdf_path: str | None
    created_by: UUID
    created_at: datetime
    updated_at: datetime
