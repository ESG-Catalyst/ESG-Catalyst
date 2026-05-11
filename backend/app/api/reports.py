"""Reports API — trigger M5 generation and stream the resulting PDF."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional
from uuid import UUID

from celery.result import AsyncResult
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.document import Document
from app.models.enums import MetricStatus, ReportStatus
from app.models.metric import ExtractedMetric
from app.models.report import Report
from app.schemas.report import ReportResponse
from app.workers.celery_app import celery_app

router = APIRouter(prefix="/api/v1/reports", tags=["reports"])


# ── Request / response schemas ─────────────────────────────────────────────
class ReportGenerateRequest(BaseModel):
    document_id: UUID


class ReportGenerateResponse(BaseModel):
    report_id: UUID
    job_id: str
    status: str  # "generating"


class ReportStatusResponse(ReportResponse):
    """Same as ReportResponse but with the latest Celery job state inlined."""

    job_state: Optional[str] = None


# Celery state → public phase
_REPORT_STATE_MAP: dict[str, str] = {
    "PENDING": "queued",
    "RECEIVED": "queued",
    "STARTED": "generating",
    "BUILDING": "generating",
    "NARRATING": "generating",
    "RENDERING": "generating",
    "SUCCESS": "ready",
    "FAILURE": "failed",
    "REVOKED": "failed",
}


# ── POST /reports/generate ─────────────────────────────────────────────────
@router.post(
    "/generate",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=ReportGenerateResponse,
)
async def generate_report(
    body: ReportGenerateRequest,
    db: AsyncSession = Depends(get_db),
) -> ReportGenerateResponse:
    """Queue M5 report generation for the document's report.

    Requires that the pipeline has already run for this document and that
    at least one extracted metric has been approved by a reviewer.
    """
    try:
        doc_result = await db.execute(select(Document).where(Document.id == body.document_id))
        doc = doc_result.scalar_one_or_none()
        if doc is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found",
            )
        if doc.report_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Pipeline has not been run for this document yet",
            )

        approved_count = (
            await db.execute(
                select(func.count(ExtractedMetric.id)).where(
                    ExtractedMetric.report_id == doc.report_id,
                    ExtractedMetric.status == MetricStatus.approved,
                )
            )
        ).scalar_one()
        if approved_count == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Report generation requires at least one approved metric",
            )

        async_result = celery_app.send_task(
            "report.generate",
            kwargs={"report_id": str(doc.report_id)},
        )

        return ReportGenerateResponse(
            report_id=doc.report_id,
            job_id=async_result.id,
            status="generating",
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Failed to enqueue report generation: {exc}",
        ) from exc


# ── GET /reports/{report_id} ───────────────────────────────────────────────
@router.get("/{report_id}", response_model=ReportStatusResponse)
async def get_report(
    report_id: UUID,
    job_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
) -> ReportStatusResponse:
    """Return the Report row + (optionally) the latest job state."""
    try:
        result = await db.execute(select(Report).where(Report.id == report_id))
        report = result.scalar_one_or_none()
        if report is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Report not found",
            )

        job_state: Optional[str] = None
        if job_id:
            celery_state = AsyncResult(job_id, app=celery_app).state or "PENDING"
            job_state = _REPORT_STATE_MAP.get(celery_state, celery_state.lower())
        elif report.pdf_path:
            job_state = "ready"
        elif report.status == ReportStatus.published:
            job_state = "ready"
        else:
            job_state = "draft"

        payload: dict[str, Any] = ReportResponse.model_validate(report).model_dump()
        payload["job_state"] = job_state
        return ReportStatusResponse(**payload)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Report lookup failed: {exc}",
        ) from exc


# ── GET /reports/{report_id}/pdf ───────────────────────────────────────────
@router.get("/{report_id}/pdf")
async def download_report_pdf(
    report_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Stream the rendered PDF (404 if generation has not produced a file yet)."""
    try:
        result = await db.execute(select(Report).where(Report.id == report_id))
        report = result.scalar_one_or_none()
        if report is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Report not found",
            )
        if not report.pdf_path:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Report PDF not ready",
            )
        pdf_file = Path(report.pdf_path)
        if not pdf_file.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Report PDF file missing on disk",
            )

        return FileResponse(
            path=str(pdf_file),
            media_type="application/pdf" if pdf_file.suffix.lower() == ".pdf" else "text/html",
            filename=pdf_file.name,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"PDF download failed: {exc}",
        ) from exc
