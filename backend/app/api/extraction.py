"""Extraction API — trigger pipeline runs and check status (auth + scoping)."""

from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import assert_company_access, get_current_user
from app.database import get_db
from app.models.metric import ExtractedMetric
from app.models.user import User
from app.schemas.metric import ExtractedMetricSchema
from app.workers.tasks import run_extraction_pipeline

router = APIRouter(prefix="/extraction", tags=["extraction"])


# ── Request / response schemas ────────────────────────────────────────────
class ExtractionRunRequest(BaseModel):
    document_id: UUID
    company_id: UUID
    report_id: UUID
    indicator_codes: Optional[list[str]] = None


class ExtractionRunResponse(BaseModel):
    task_id: str
    message: str


class ExtractionStatusResponse(BaseModel):
    task_id: str
    state: str
    status: Optional[str] = None
    result: Optional[dict] = None


# ── POST /extraction/run ──────────────────────────────────────────────────
@router.post("/run", response_model=ExtractionRunResponse)
async def run_extraction(
    body: ExtractionRunRequest,
    user: User = Depends(get_current_user),
):
    """Launch the extraction pipeline. User must have access to the company."""
    assert_company_access(user, body.company_id)

    task = run_extraction_pipeline.delay(
        document_id=str(body.document_id),
        company_id=str(body.company_id),
        report_id=str(body.report_id),
        indicator_codes=body.indicator_codes,
    )

    return ExtractionRunResponse(
        task_id=task.id,
        message="Pipeline started. Poll /extraction/status/{task_id} for progress.",
    )


# ── GET /extraction/status/{task_id} ─────────────────────────────────────
@router.get("/status/{task_id}", response_model=ExtractionStatusResponse)
async def extraction_status(
    task_id: str,
    user: User = Depends(get_current_user),
):
    """Check the status of a running extraction pipeline task."""
    result = run_extraction_pipeline.AsyncResult(task_id)

    response = ExtractionStatusResponse(
        task_id=task_id,
        state=result.state,
    )

    if result.state == "FAILURE":
        response.status = str(result.info) if result.info else "Task failed"
    elif result.state == "SUCCESS":
        response.status = "Pipeline complete"
        response.result = result.result
    elif isinstance(result.info, dict):
        response.status = result.info.get("status", "Processing...")
    else:
        response.status = "Queued" if result.state == "PENDING" else "Processing..."

    return response


# ── GET /extraction/results/{report_id} ──────────────────────────────────
@router.get("/results/{report_id}", response_model=list[ExtractedMetricSchema])
async def extraction_results(
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

    # Verify the user can access this company's data
    assert_company_access(user, metrics[0].company_id)

    return metrics
