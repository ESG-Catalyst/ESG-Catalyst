"""Pipeline API — trigger the M1→M4 extraction pipeline and poll its status.

Routes call the pipeline exclusively via ``celery_app.send_task(name, kwargs=...)``
so this module never imports any ``app.core.*`` pipeline module, keeping the
API container slim (no torch / transformers / MLflow dependency).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

import structlog
from celery.result import AsyncResult
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, require_company
from app.models.document import Document
from app.models.enums import DocumentStatus, ReportStatus
from app.models.report import Report
from app.models.user import User
from app.workers.celery_app import celery_app

log: structlog.BoundLogger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/v1/pipeline", tags=["pipeline"])


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------


class PipelineRunRequest(BaseModel):
    """Body for POST /pipeline/run."""

    document_id: UUID


class PipelineRunResponse(BaseModel):
    """Returned immediately after enqueueing the pipeline task."""

    job_id: str
    document_id: UUID
    report_id: UUID
    status: str  # always "queued"


class PipelineStatusResponse(BaseModel):
    """Polled by the frontend until ``stage`` is ``complete`` or ``failed``."""

    job_id: str
    stage: str  # ingestion|chunking|embedding|classifying|extracting|scoring|complete|failed|queued
    progress: int  # 0-100
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Celery state → public stage + progress (0-100)
# ---------------------------------------------------------------------------

_STATE_MAP: dict[str, tuple[str, int]] = {
    "PENDING":    ("queued",      0),
    "RECEIVED":   ("queued",      5),
    "STARTED":    ("ingestion",  10),
    "INGESTING":  ("ingestion",  15),
    "CHUNKING":   ("chunking",   30),
    "EMBEDDING":  ("embedding",  45),
    "CLASSIFYING":("classifying",50),
    "EXTRACTING": ("extracting", 70),
    "SCORING":    ("scoring",    85),
    "PERSISTING": ("scoring",    95),
    "SUCCESS":    ("complete",  100),
    "FAILURE":    ("failed",    100),
    "REVOKED":    ("failed",    100),
    "RETRY":      ("queued",     5),
}


# ---------------------------------------------------------------------------
# POST /pipeline/run
# ---------------------------------------------------------------------------


@router.post(
    "/run",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=PipelineRunResponse,
)
async def run_pipeline(
    body: PipelineRunRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PipelineRunResponse:
    """Queue the full M1→M4 extraction pipeline for a previously uploaded document.

    Creates a linked ``Report`` row on first run if one does not already exist.
    Returns 409 when a pipeline is already running for the same document.
    """
    try:
        company_id = require_company(current_user)

        result = await db.execute(select(Document).where(Document.id == body.document_id))
        doc = result.scalar_one_or_none()
        # 404 (not 403) on cross-company so a probe can't distinguish
        # "doesn't exist" from "belongs to someone else".
        if doc is None or doc.company_id != company_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found",
            )

        if doc.status == DocumentStatus.processing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Pipeline already running for this document",
            )

        # Auto-create or reuse the Report record this pipeline will populate.
        report: Optional[Report] = None
        if doc.report_id is not None:
            res = await db.execute(select(Report).where(Report.id == doc.report_id))
            report = res.scalar_one_or_none()
        if report is None:
            report = Report(
                company_id=doc.company_id,
                title=f"ESG Report — {doc.filename}",
                reporting_year=datetime.now().year,
                frameworks=["GRI", "FRA", "SASB"],
                status=ReportStatus.draft,
            )
            db.add(report)
            await db.flush()
            await db.refresh(report)
            doc.report_id = report.id
            await db.flush()

        async_result = celery_app.send_task(
            "pipeline.run_extraction",
            kwargs={
                "document_id": str(doc.id),
                "company_id": str(doc.company_id),
                "report_id": str(report.id),
            },
        )

        log.info(
            "pipeline.enqueued",
            job_id=async_result.id,
            document_id=str(doc.id),
            report_id=str(report.id),
        )
        return PipelineRunResponse(
            job_id=async_result.id,
            document_id=doc.id,
            report_id=report.id,
            status="queued",
        )
    except HTTPException:
        raise
    except Exception as exc:
        log.exception("pipeline.enqueue_error", document_id=str(body.document_id), error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to enqueue pipeline due to an unexpected server error",
        ) from exc


# ---------------------------------------------------------------------------
# GET /pipeline/status/{job_id}
# ---------------------------------------------------------------------------


@router.get("/status/{job_id}", response_model=PipelineStatusResponse)
async def get_pipeline_status(
    job_id: str,
    current_user: User = Depends(get_current_user),  # noqa: ARG001 — auth only, not used for filtering
) -> PipelineStatusResponse:
    """Return the current Celery task state mapped to public pipeline stages.

    Authentication is required.  Celery task state isn't tagged with
    ``company_id`` so we cannot filter further; the ``job_id`` is only ever
    returned by ``/pipeline/run`` (which IS company-scoped), so an attacker
    would have to correctly guess a UUID4 to leak progress info.
    """
    try:
        async_result = AsyncResult(job_id, app=celery_app)
        state = async_result.state or "PENDING"
        stage, progress = _STATE_MAP.get(state, ("queued", 0))

        error: Optional[str] = None
        info: Any = async_result.info

        if state == "FAILURE":
            # ``info`` is the exception raised inside the task.
            error = str(info) if info is not None else "Task failed"
            progress = 100
        elif isinstance(info, dict):
            # Custom states stash a 'status' message in meta.
            msg = info.get("status")
            if msg and stage == "queued":
                stage = msg.lower()

        return PipelineStatusResponse(
            job_id=job_id,
            stage=stage,
            progress=progress,
            error=error,
        )
    except HTTPException:
        raise
    except Exception as exc:
        log.exception("pipeline.status_error", job_id=job_id, error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Status lookup failed due to an unexpected server error",
        ) from exc
