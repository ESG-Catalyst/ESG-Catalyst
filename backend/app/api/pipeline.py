"""Pipeline API — trigger pipeline runs and poll job status."""

from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.auth import assert_company_access, get_current_user
from app.models.user import User
from app.workers.tasks import run_extraction_pipeline

router = APIRouter(prefix="/pipeline", tags=["pipeline"])


# ── Request / response schemas ────────────────────────────────────────────
class PipelineRunRequest(BaseModel):
    document_id: UUID
    company_id: UUID
    report_id: UUID
    indicator_codes: Optional[list[str]] = None


class PipelineRunResponse(BaseModel):
    job_id: str
    message: str


class PipelineStatusResponse(BaseModel):
    job_id: str
    state: str
    status: Optional[str] = None
    result: Optional[dict] = None


# ── POST /pipeline/run ────────────────────────────────────────────────────
@router.post("/run", response_model=PipelineRunResponse)
async def run_pipeline(
    body: PipelineRunRequest,
    user: User = Depends(get_current_user),
):
    """Launch the extraction pipeline for a document.

    Pipeline states: queued → parsing → chunking → classifying → extracting → scoring → complete | failed
    """
    assert_company_access(user, body.company_id)

    task = run_extraction_pipeline.delay(
        document_id=str(body.document_id),
        company_id=str(body.company_id),
        report_id=str(body.report_id),
        indicator_codes=body.indicator_codes,
    )

    return PipelineRunResponse(
        job_id=task.id,
        message="Pipeline started. Poll /pipeline/status/{job_id} for progress.",
    )


# ── GET /pipeline/status/{job_id} ─────────────────────────────────────────
@router.get("/status/{job_id}", response_model=PipelineStatusResponse)
async def pipeline_status(
    job_id: str,
    user: User = Depends(get_current_user),
):
    """Check the status of a running pipeline job."""
    result = run_extraction_pipeline.AsyncResult(job_id)

    response = PipelineStatusResponse(
        job_id=job_id,
        state=result.state,
    )

    if result.state == "FAILURE":
        response.status = str(result.info) if result.info else "Pipeline failed"
    elif result.state == "SUCCESS":
        response.status = "Pipeline complete"
        response.result = result.result
    elif isinstance(result.info, dict):
        response.status = result.info.get("status", "Processing...")
    else:
        response.status = "Queued" if result.state == "PENDING" else "Processing..."

    return response
