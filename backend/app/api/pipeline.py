"""Pipeline API — trigger the M1→M4 extraction pipeline and poll its status."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from celery.result import AsyncResult
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.document import Document
from app.models.enums import DocumentStatus, ReportStatus
from app.models.report import Report
from app.workers.celery_app import celery_app

router = APIRouter(prefix="/api/v1/pipeline", tags=["pipeline"])


# ── Request / response schemas ─────────────────────────────────────────────
class PipelineRunRequest(BaseModel):
    document_id: UUID


class PipelineRunResponse(BaseModel):
    job_id: str
    document_id: UUID
    report_id: UUID
    status: str  # "queued"


class PipelineStatusResponse(BaseModel):
    job_id: str
    stage: str  # ingestion|chunking|embedding|classifying|extracting|scoring|complete|failed|queued
    progress: int
    error: Optional[str] = None


# Celery custom state → public stage + progress (0-100)
_STATE_MAP: dict[str, tuple[str, int]] = {
    "PENDING": ("queued", 0),
    "RECEIVED": ("queued", 5),
    "STARTED": ("ingestion", 10),
    "INGESTING": ("ingestion", 15),
    "CHUNKING": ("chunking", 30),
    "EMBEDDING": ("embedding", 45),
    "CLASSIFYING": ("classifying", 50),
    "EXTRACTING": ("extracting", 70),
    "SCORING": ("scoring", 85),
    "PERSISTING": ("scoring", 95),
    "SUCCESS": ("complete", 100),
    "FAILURE": ("failed", 100),
    "REVOKED": ("failed", 100),
    "RETRY": ("queued", 5),
}


# ── POST /pipeline/run ─────────────────────────────────────────────────────
@router.post(
    "/run",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=PipelineRunResponse,
)
async def run_pipeline(
    body: PipelineRunRequest,
    db: AsyncSession = Depends(get_db),
) -> PipelineRunResponse:
    """Queue the full M1→M4 extraction pipeline for a previously uploaded document."""
    try:
        result = await db.execute(select(Document).where(Document.id == body.document_id))
        doc = result.scalar_one_or_none()
        if doc is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found",
            )

        if doc.status == DocumentStatus.processing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Pipeline already running for this document",
            )

        # Auto-create or reuse the Report record this pipeline will populate
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

        return PipelineRunResponse(
            job_id=async_result.id,
            document_id=doc.id,
            report_id=report.id,
            status="queued",
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Failed to enqueue pipeline: {exc}",
        ) from exc


# ── GET /pipeline/status/{job_id} ──────────────────────────────────────────
@router.get("/status/{job_id}", response_model=PipelineStatusResponse)
async def get_pipeline_status(job_id: str) -> PipelineStatusResponse:
    """Return the current Celery task state mapped to public pipeline stages."""
    try:
        async_result = AsyncResult(job_id, app=celery_app)
        state = async_result.state or "PENDING"
        stage, progress = _STATE_MAP.get(state, ("queued", 0))

        error: Optional[str] = None
        info: Any = async_result.info

        if state == "FAILURE":
            # info is the exception raised inside the task
            error = str(info) if info is not None else "Task failed"
            progress = 100
        elif isinstance(info, dict):
            # Custom states stash a 'status' message in meta
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
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Status lookup failed: {exc}",
        ) from exc
