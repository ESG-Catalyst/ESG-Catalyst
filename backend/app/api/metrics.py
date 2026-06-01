"""Metrics API — list a document's extracted metrics and apply review decisions."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, require_company
from app.models.document import Document
from app.models.enums import MetricStatus
from app.models.metric import ExtractedMetric
from app.models.report import Report
from app.models.user import User
from app.schemas.metric import ExtractedMetricSchema

log: structlog.BoundLogger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/v1/metrics", tags=["metrics"])

_ALLOWED_REVIEW_STATUSES = {MetricStatus.approved, MetricStatus.rejected}


class MetricReviewRequest(BaseModel):
    """Reviewer decision body for PATCH /metrics/{id}."""

    status: MetricStatus = Field(..., description="approved or rejected")
    value: Optional[float] = None
    unit: Optional[str] = None
    note: Optional[str] = None


# ---------------------------------------------------------------------------
# GET /metrics/{document_id}
# ---------------------------------------------------------------------------


@router.get("/{document_id}", response_model=list[ExtractedMetricSchema])
async def list_document_metrics(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ExtractedMetric]:
    """Return every extracted metric belonging to the document's linked report.

    Returns an empty list when the pipeline has not yet run for this document
    (i.e. no ``report_id`` is linked).
    """
    try:
        company_id = require_company(current_user)

        doc_result = await db.execute(select(Document).where(Document.id == document_id))
        doc = doc_result.scalar_one_or_none()
        # 404 (not 403) on cross-company — avoids existence leaks.
        if doc is None or doc.company_id != company_id:
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
        log.exception("metrics.list_error", document_id=str(document_id), error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve metrics due to an unexpected server error",
        ) from exc


# ---------------------------------------------------------------------------
# PATCH /metrics/{metric_id}
# ---------------------------------------------------------------------------


@router.patch("/{metric_id}", response_model=ExtractedMetricSchema)
async def review_metric(
    metric_id: UUID,
    body: MetricReviewRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ExtractedMetric:
    """Apply a reviewer decision (approve / reject) to a single metric.

    Validates ``status`` is ``approved`` or ``rejected`` before touching the
    database.  Ownership is verified by joining through ``Report`` so no extra
    round-trip is needed.
    """
    try:
        company_id = require_company(current_user)

        if body.status not in _ALLOWED_REVIEW_STATUSES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="status must be one of: approved, rejected",
            )

        # Join Metric → Report to verify company ownership in a single trip.
        result = await db.execute(
            select(ExtractedMetric, Report)
            .join(Report, ExtractedMetric.report_id == Report.id)
            .where(ExtractedMetric.id == metric_id)
        )
        row = result.one_or_none()
        # 404 (not 403) on cross-company — avoids existence leaks.
        if row is None or row[1].company_id != company_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Metric not found",
            )
        metric: ExtractedMetric = row[0]

        metric.status = body.status
        metric.reviewer_id = current_user.id
        metric.reviewed_at = datetime.now(timezone.utc)
        if body.value is not None:
            metric.value = body.value
        if body.unit is not None:
            metric.unit = body.unit
        if body.note is not None:
            metric.note = body.note

        await db.flush()
        await db.refresh(metric)
        log.info(
            "metric.reviewed",
            metric_id=str(metric_id),
            new_status=body.status.value,
            reviewer_id=str(current_user.id),
        )
        return metric
    except HTTPException:
        raise
    except Exception as exc:
        log.exception("metrics.review_error", metric_id=str(metric_id), error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update metric due to an unexpected server error",
        ) from exc
