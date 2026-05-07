"""Metrics API — list, review, and export extracted ESG metrics."""

from __future__ import annotations

import csv
import io
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import assert_company_access, get_current_user
from app.database import get_db
from app.models.enums import MetricStatus
from app.models.metric import ExtractedMetric
from app.models.user import User
from app.schemas.metric import ExtractedMetricSchema, ExtractedMetricUpdate

router = APIRouter(prefix="/metrics", tags=["metrics"])


# ── GET /metrics/{report_id} ──────────────────────────────────────────────
@router.get("/{report_id}", response_model=list[ExtractedMetricSchema])
async def list_metrics(
    report_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Fetch all extracted metrics for a given report. Company-scoped."""
    result = await db.execute(
        select(ExtractedMetric)
        .where(ExtractedMetric.report_id == report_id)
        .order_by(ExtractedMetric.gri_code)
    )
    metrics = result.scalars().all()

    if not metrics:
        raise HTTPException(status_code=404, detail="No metrics found for this report")

    assert_company_access(user, metrics[0].company_id)
    return metrics


# ── PATCH /metrics/{id} ───────────────────────────────────────────────────
@router.patch("/{metric_id}", response_model=ExtractedMetricSchema)
async def review_metric(
    metric_id: UUID,
    body: ExtractedMetricUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Approve, reject, or edit a metric value. Requires company access."""
    result = await db.execute(
        select(ExtractedMetric).where(ExtractedMetric.id == metric_id)
    )
    metric = result.scalar_one_or_none()

    if not metric:
        raise HTTPException(status_code=404, detail="Metric not found")

    assert_company_access(user, metric.company_id)

    update_data = body.model_dump(exclude_unset=True)

    # Auto-stamp reviewer + timestamp when status changes to approved/rejected/edited
    final_status = update_data.get("status", metric.status)
    if final_status in (MetricStatus.approved, MetricStatus.rejected, MetricStatus.edited):
        if "reviewer_id" not in update_data:
            update_data["reviewer_id"] = user.id
        if "reviewed_at" not in update_data:
            update_data["reviewed_at"] = datetime.now(timezone.utc)

    for field, value in update_data.items():
        setattr(metric, field, value)

    await db.flush()
    await db.refresh(metric)
    return metric


# ── GET /metrics/{report_id}/export ──────────────────────────────────────
@router.get("/{report_id}/export")
async def export_metrics(
    report_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Export all metrics for a report as a downloadable CSV."""
    result = await db.execute(
        select(ExtractedMetric)
        .where(ExtractedMetric.report_id == report_id)
        .order_by(ExtractedMetric.gri_code)
    )
    metrics = result.scalars().all()

    if not metrics:
        raise HTTPException(status_code=404, detail="No metrics found for this report")

    assert_company_access(user, metrics[0].company_id)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "gri_code", "label", "value", "unit",
        "original_value", "original_unit",
        "confidence", "status", "source_file", "source_page",
        "evidence_chunk", "extraction_method", "note",
    ])

    for m in metrics:
        writer.writerow([
            m.gri_code, m.label, m.value, m.unit,
            m.original_value, m.original_unit,
            m.confidence, m.status.value, m.source_file, m.source_page,
            m.evidence_chunk, m.extraction_method.value if m.extraction_method else "",
            m.note,
        ])

    output.seek(0)
    filename = f"metrics_{report_id}.csv"
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode("utf-8")),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
