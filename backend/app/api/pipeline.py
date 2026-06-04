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
from pydantic import BaseModel, Field
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
    """Body for POST /pipeline/run.

    Accepts one OR more documents to analyse together as a single Report (a
    "document set"): each file is ingested/chunked/classified/embedded into a
    shared pool, then ONE pooled extraction pass runs, with each metric
    attributed to the document its evidence came from.
    """

    document_ids: list[UUID] = Field(..., min_length=1)


class PipelineRunResponse(BaseModel):
    """Returned immediately after enqueueing the pipeline task."""

    job_id: str
    document_id: UUID            # primary (first) document — for navigation
    document_ids: list[UUID]
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

        # Fetch + validate every document in the set (all must belong to the
        # caller's company; 404 on any cross-company id to avoid existence leaks).
        result = await db.execute(
            select(Document).where(Document.id.in_(body.document_ids))
        )
        found = {d.id: d for d in result.scalars().all()}
        ordered: list[Document] = []
        for did in body.document_ids:
            doc = found.get(did)
            if doc is None or doc.company_id != company_id:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Document not found",
                )
            if doc.status == DocumentStatus.processing:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Pipeline already running for document {doc.filename!r}",
                )
            ordered.append(doc)

        primary = ordered[0]

        # One Report groups the whole document set. Reuse the primary doc's
        # report if it already has one; else create it and link EVERY doc to it.
        report: Optional[Report] = None
        if primary.report_id is not None:
            res = await db.execute(select(Report).where(Report.id == primary.report_id))
            report = res.scalar_one_or_none()
        if report is None:
            title = (
                f"ESG Report — {primary.filename}"
                if len(ordered) == 1
                else f"ESG Report — {primary.filename} +{len(ordered) - 1} more"
            )
            report = Report(
                company_id=company_id,
                title=title,
                reporting_year=datetime.now().year,
                frameworks=["GRI", "FRA", "SASB"],
                status=ReportStatus.draft,
            )
            db.add(report)
            await db.flush()
            await db.refresh(report)
        for doc in ordered:
            doc.report_id = report.id
        await db.flush()

        async_result = celery_app.send_task(
            "pipeline.run_extraction",
            kwargs={
                "document_ids": [str(d.id) for d in ordered],
                "company_id": str(company_id),
                "report_id": str(report.id),
            },
        )

        log.info(
            "pipeline.enqueued",
            job_id=async_result.id,
            document_ids=[str(d.id) for d in ordered],
            report_id=str(report.id),
        )
        return PipelineRunResponse(
            job_id=async_result.id,
            document_id=primary.id,
            document_ids=[d.id for d in ordered],
            report_id=report.id,
            status="queued",
        )
    except HTTPException:
        raise
    except Exception as exc:
        log.exception("pipeline.enqueue_error", error=str(exc))
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
