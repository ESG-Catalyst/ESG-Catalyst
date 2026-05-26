"""Metrics API — list a document's extracted metrics and apply review decisions."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.database import get_db
from app.models.document import Document
from app.models.enums import MetricStatus
from app.models.metric import ExtractedMetric
from app.models.report import Report
from app.models.user import User
from app.schemas.metric import ExtractedMetricSchema

router = APIRouter(prefix="/api/v1/metrics", tags=["metrics"])


class MetricReviewRequest(BaseModel):
    """Reviewer decision body for PATCH /metrics/{id}."""

    status: MetricStatus = Field(..., description="approved or rejected")
    value: Optional[float] = None
    unit: Optional[str] = None
    note: Optional[str] = None


_ALLOWED_REVIEW_STATUSES = {MetricStatus.approved, MetricStatus.rejected}


@router.get("/{document_id}", response_model=list[ExtractedMetricSchema])
async def list_document_metrics(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ExtractedMetric]:
    """Return every extracted metric belonging to a document's report."""
    try:
        if current_user.company_id is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User has no associated company",
            )
        doc_result = await db.execute(select(Document).where(Document.id == document_id))
        doc = doc_result.scalar_one_or_none()
        # 404 (not 403) on cross-company.
        if doc is None or doc.company_id != current_user.company_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found",
            )
        if doc.report_id is None:
            return []

        metrics_result = await db.execute(
            select(ExtractedMetric)
            .where(ExtractedMetric.report_id == doc.report_id)
            .order_by(ExtractedMetric.gri_code)
        )
        return list(metrics_result.scalars().all())
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Metric lookup failed: {exc}",
        ) from exc


@router.patch("/{metric_id}", response_model=ExtractedMetricSchema)
async def review_metric(
    metric_id: UUID,
    body: MetricReviewRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ExtractedMetric:
    """Apply a reviewer decision (approve / reject) to a single metric."""
    try:
        if current_user.company_id is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User has no associated company",
            )
        if body.status not in _ALLOWED_REVIEW_STATUSES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="status must be one of: approved, rejected",
            )

        # Join Metric → Report so we can verify company ownership in one trip.
        result = await db.execute(
            select(ExtractedMetric, Report)
            .join(Report, ExtractedMetric.report_id == Report.id)
            .where(ExtractedMetric.id == metric_id)
        )
        row = result.one_or_none()
        # 404 (not 403) on cross-company.
        if row is None or row[1].company_id != current_user.company_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Metric not found",
            )
        metric = row[0]
        metric.reviewer_id = current_user.id

        metric.status = body.status
        if body.value is not None:
            metric.value = body.value
        if body.unit is not None:
            metric.unit = body.unit
        if body.note is not None:
            metric.note = body.note
        metric.reviewed_at = datetime.now(timezone.utc)

        await db.flush()
        await db.refresh(metric)
        return metric
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Metric update failed: {exc}",
        ) from exc
