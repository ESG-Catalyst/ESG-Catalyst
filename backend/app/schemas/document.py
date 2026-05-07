from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.models.enums import DocumentStatus


class DocumentUploadResponse(BaseModel):
    """Returned after a successful document upload."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    company_id: UUID
    report_id: UUID | None
    filename: str
    file_type: str
    status: DocumentStatus
    page_count: int | None
    language: str | None
    uploaded_by: UUID
    created_at: datetime
    updated_at: datetime


class DocumentSchema(BaseModel):
    """Full document representation for API responses."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    company_id: UUID
    report_id: UUID | None
    filename: str
    file_type: str
    status: DocumentStatus
    page_count: int | None
    language: str | None
    uploaded_by: UUID
    created_at: datetime
    updated_at: datetime
