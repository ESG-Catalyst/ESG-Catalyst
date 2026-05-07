from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class CompanyCreate(BaseModel):
    name: str
    industry: str
    country: str


class CompanyUpdate(BaseModel):
    name: str | None = None
    industry: str | None = None
    country: str | None = None


class CompanyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    industry: str
    country: str
    created_at: datetime
    updated_at: datetime
