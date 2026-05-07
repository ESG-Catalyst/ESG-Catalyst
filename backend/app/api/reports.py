"""Reports API — create, list, and export ESG reports (auth + scoping)."""

from __future__ import annotations

import io
import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import assert_company_access, get_accessible_company_ids, get_current_user
from app.database import get_db
from app.models.enums import ReportStatus
from app.models.metric import ExtractedMetric
from app.models.report import Report
from app.models.user import User
from app.schemas.report import ReportCreate, ReportResponse

router = APIRouter(prefix="/reports", tags=["reports"])


# ── POST /reports/generate ────────────────────────────────────────────────
@router.post("/generate", status_code=status.HTTP_201_CREATED, response_model=ReportResponse)
async def generate_report(
    body: ReportCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new report record. User must have access to the company."""
    assert_company_access(user, body.company_id)

    report = Report(
        company_id=body.company_id,
        title=body.title,
        reporting_year=body.reporting_year,
        frameworks=body.frameworks,
        status=ReportStatus.draft,
        created_by=user.id,
    )
    db.add(report)
    await db.flush()
    await db.refresh(report)
    return report


# ── GET /reports/ ─────────────────────────────────────────────────────────
@router.get("/", response_model=list[ReportResponse])
async def list_reports(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List reports. Automatically scoped to user's accessible companies."""
    stmt = select(Report).order_by(Report.created_at.desc())

    allowed = get_accessible_company_ids(user)
    if allowed is not None:
        stmt = stmt.where(Report.company_id.in_(allowed))

    result = await db.execute(stmt)
    return result.scalars().all()


# ── GET /reports/{report_id} ──────────────────────────────────────────────
@router.get("/{report_id}", response_model=ReportResponse)
async def get_report(
    report_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a single report by ID."""
    result = await db.execute(select(Report).where(Report.id == report_id))
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    assert_company_access(user, report.company_id)
    return report


# ── GET /reports/export/{report_id} ───────────────────────────────────────
@router.get("/export/{report_id}")
async def export_report(
    report_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Export a report as a downloadable JSON summary."""
    result = await db.execute(select(Report).where(Report.id == report_id))
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    assert_company_access(user, report.company_id)

    metrics_result = await db.execute(
        select(ExtractedMetric)
        .where(ExtractedMetric.report_id == report_id)
        .order_by(ExtractedMetric.gri_code)
    )
    metrics = metrics_result.scalars().all()

    export_data = {
        "report": {
            "id": str(report.id),
            "title": report.title,
            "reporting_year": report.reporting_year,
            "status": report.status.value,
            "frameworks": report.frameworks,
            "scores": {
                "total": report.total_score,
                "gri": report.gri_score,
                "fra": report.fra_score,
                "sasb": report.sasb_score,
            },
        },
        "metrics": [
            {
                "gri_code": m.gri_code,
                "label": m.label,
                "value": m.value,
                "unit": m.unit,
                "original_value": m.original_value,
                "confidence": m.confidence,
                "status": m.status.value,
                "evidence": m.evidence_chunk,
                "source_file": m.source_file,
                "source_page": m.source_page,
                "note": m.note,
            }
            for m in metrics
        ],
        "summary": {
            "total_metrics": len(metrics),
            "extracted": sum(1 for m in metrics if m.status.value == "extracted"),
            "approved": sum(1 for m in metrics if m.status.value == "approved"),
            "missing": sum(1 for m in metrics if m.status.value == "missing"),
            "ambiguous": sum(1 for m in metrics if m.status.value == "ambiguous"),
        },
    }

    content = json.dumps(export_data, indent=2, ensure_ascii=False)
    buffer = io.BytesIO(content.encode("utf-8"))

    filename = f"esg_report_{report.title.replace(' ', '_')}_{report.reporting_year}.json"
    return StreamingResponse(
        buffer,
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
