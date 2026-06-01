"""Reports API — trigger M5 generation and stream the resulting PDF.

Report generation is a separate Celery task (``report.generate``) queued
after at least one metric has been approved.  Like all routes in this module,
the task is dispatched via ``celery_app.send_task(name, kwargs=...)`` so this
file never imports ``app.core.*`` pipeline modules.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional
from uuid import UUID

import structlog
from celery.result import AsyncResult
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, require_company, require_owned_record
from app.models.document import Document
from app.models.enums import MetricStatus, ReportStatus
from app.models.metric import ExtractedMetric
from app.models.report import Report
from app.models.user import User
from app.schemas.report import ReportResponse
from app.workers.celery_app import celery_app

log: structlog.BoundLogger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/v1/reports", tags=["reports"])


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------


class ReportGenerateRequest(BaseModel):
    """Body for POST /reports/generate."""

    document_id: UUID


class ReportGenerateResponse(BaseModel):
    """Returned immediately after enqueueing the report-generation task."""

    report_id: UUID
    job_id: str
    status: str  # always "generating"


class ReportStatusResponse(ReportResponse):
    """``ReportResponse`` with the latest Celery job state inlined."""

    job_state: Optional[str] = None


# ---------------------------------------------------------------------------
# Celery state → public phase
# ---------------------------------------------------------------------------

_REPORT_STATE_MAP: dict[str, str] = {
    "PENDING":   "queued",
    "RECEIVED":  "queued",
    "STARTED":   "generating",
    "BUILDING":  "generating",
    "NARRATING": "generating",
    "RENDERING": "generating",
    "SUCCESS":   "ready",
    "FAILURE":   "failed",
    "REVOKED":   "failed",
}


# ---------------------------------------------------------------------------
# GET /reports/
# ---------------------------------------------------------------------------


@router.get("/", response_model=list[ReportResponse])
async def list_reports(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[Report]:
    """Return the caller's company's reports, newest first."""
    try:
        company_id = require_company(current_user)
        result = await db.execute(
            select(Report)
            .where(Report.company_id == company_id)
            .order_by(Report.created_at.desc())
        )
        return list(result.scalars().all())
    except HTTPException:
        raise
    except Exception as exc:
        log.exception("reports.list_error", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list reports due to an unexpected server error",
        ) from exc


# ---------------------------------------------------------------------------
# POST /reports/generate
# ---------------------------------------------------------------------------


@router.post(
    "/generate",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=ReportGenerateResponse,
)
async def generate_report(
    body: ReportGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ReportGenerateResponse:
    """Queue M5 report generation for the document's linked report.

    Requires that the extraction pipeline has already run for this document
    and that at least one extracted metric has been approved by a reviewer.
    """
    try:
        doc = await require_owned_record(
            db,
            Document,
            body.document_id,
            current_user,
            not_found_detail="Document not found",
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

        log.info(
            "report.generate_enqueued",
            job_id=async_result.id,
            report_id=str(doc.report_id),
            document_id=str(body.document_id),
        )
        return ReportGenerateResponse(
            report_id=doc.report_id,
            job_id=async_result.id,
            status="generating",
        )
    except HTTPException:
        raise
    except Exception as exc:
        log.exception("reports.generate_error", document_id=str(body.document_id), error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to enqueue report generation due to an unexpected server error",
        ) from exc


# ---------------------------------------------------------------------------
# GET /reports/{report_id}
# ---------------------------------------------------------------------------


@router.get("/{report_id}", response_model=ReportStatusResponse)
async def get_report(
    report_id: UUID,
    job_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ReportStatusResponse:
    """Return the Report row plus (optionally) the latest Celery job state.

    Pass ``?job_id=<celery_task_id>`` to resolve a live task state; omit it to
    derive the state from the persisted ``pdf_path`` / ``status`` columns.
    """
    try:
        report = await require_owned_record(
            db,
            Report,
            report_id,
            current_user,
            not_found_detail="Report not found",
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
        log.exception("reports.get_error", report_id=str(report_id), error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve report due to an unexpected server error",
        ) from exc


# ---------------------------------------------------------------------------
# GET /reports/{report_id}/pdf
# ---------------------------------------------------------------------------


@router.get("/{report_id}/pdf")
async def download_report_pdf(
    report_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> FileResponse:
    """Stream the rendered PDF (404 if generation has not produced a file yet)."""
    try:
        report = await require_owned_record(
            db,
            Report,
            report_id,
            current_user,
            not_found_detail="Report not found",
        )

        if not report.pdf_path:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Report PDF not ready",
            )
        pdf_file = Path(report.pdf_path)
        if not pdf_file.exists():
            log.warning("reports.pdf_missing_on_disk", report_id=str(report_id), path=report.pdf_path)
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Report PDF file missing on disk",
            )

        media_type = "application/pdf" if pdf_file.suffix.lower() == ".pdf" else "text/html"
        return FileResponse(
            path=str(pdf_file),
            media_type=media_type,
            filename=pdf_file.name,
        )
    except HTTPException:
        raise
    except Exception as exc:
        log.exception("reports.pdf_error", report_id=str(report_id), error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="PDF download failed due to an unexpected server error",
        ) from exc
