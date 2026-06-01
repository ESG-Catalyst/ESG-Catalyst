"""Scoring API — expose the spec-compliant scoring engine via four endpoints.

Endpoints:
    POST /api/v1/scoring/score-document   full pipeline for a document
    GET  /api/v1/scoring/weights/{sector} weight registry transparency
    GET  /api/v1/scoring/fra-registry     FRA KPI registry
    POST /api/v1/scoring/gap-analysis     gap analysis for an existing report

# FLAGGED FOR RECONCILIATION (cross-area seam):
#
# This module imports directly from ``app.core.scoring.*``.  That violates the
# load-bearing invariant that route modules must NEVER import core pipeline
# modules (so the API container stays slim and doesn't pull in torch /
# transformers / MLflow).
#
# The scoring engine is lighter than the NLP pipeline, but the principle
# still applies.  The correct fix is to extract the scoring invocation into
# a dedicated Celery task (``scoring.score_document``) and call it via
# ``celery_app.send_task(...)`` — identical to how pipeline.py calls
# ``pipeline.run_extraction``.  This is an M4 + M6 cross-area change; it
# requires a new task in workers/tasks.py (M6-owned) wrapping the M4 scorer.
#
# Until that task exists, the direct import is kept so the endpoint remains
# functional.  Do NOT add further ``from app.core.*`` imports to this file.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# FLAGGED: direct core imports — see module docstring for remediation path.
from app.core.scoring import (
    FINANCIAL_WEIGHTS,
    FRA_KPI_REGISTRY,
    MANUFACTURING_WEIGHTS,
    check_fra_gate,
    generate_gap_analysis,
    get_weight_registry,
    score_document,
)
from app.core.scoring.fra_compliance import extract_fra_results_from_scores
from app.core.scoring.gap_analysis import generate_improvement_roadmap
from app.database import get_db
from app.models.document import Document
from app.models.enums import MetricDirection, MetricType
from app.models.metric import ExtractedMetric
from app.models.report import Report
from app.schemas.metric import MetricScoreInput

log: structlog.BoundLogger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/v1/scoring", tags=["scoring"])

_VALID_SECTORS = frozenset({"FINANCIAL", "MANUFACTURING"})

# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------


class ScoreDocumentRequest(BaseModel):
    """Body for POST /scoring/score-document."""

    document_id: UUID
    sector: str = "FINANCIAL"
    external_assurance: bool = False


class GapAnalysisRequest(BaseModel):
    """Body for POST /scoring/gap-analysis."""

    report_id: UUID


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_MT_MAP: dict[str, MetricType] = {
    "binary":       MetricType.BINARY,
    "quantitative": MetricType.QUANTITATIVE,
    "qualitative":  MetricType.QUALITATIVE,
    "q_plus_ql":    MetricType.Q_PLUS_QL,
}

_DIR_MAP: dict[str, MetricDirection] = {
    "higher_better": MetricDirection.HIGHER_BETTER,
    "lower_better":  MetricDirection.LOWER_BETTER,
    "neutral":       MetricDirection.NEUTRAL,
}


def _metric_to_score_input(m: ExtractedMetric) -> MetricScoreInput:
    """Convert an ``ExtractedMetric`` ORM row to a ``MetricScoreInput``.

    Priority for ``metric_code``: fra_code > gri_code > sasb_code > str(id).
    """
    code = m.fra_code or m.gri_code or m.sasb_code or str(m.id)

    raw_mt = str(getattr(m, "metric_type", "quantitative") or "quantitative").lower()
    raw_dir = str(getattr(m, "direction", "neutral") or "neutral").lower()

    mt = _MT_MAP.get(raw_mt, MetricType.QUANTITATIVE)
    dir_ = _DIR_MAP.get(raw_dir, MetricDirection.NEUTRAL)

    criteria_raw = getattr(m, "completeness_criteria", None)
    criteria: list[str] = criteria_raw if isinstance(criteria_raw, list) else []

    return MetricScoreInput(
        metric_code=code,
        metric_type=mt,
        extracted_value=m.value,
        extracted_text=getattr(m, "evidence_chunk", None),
        benchmark=getattr(m, "benchmark", None),
        direction=dir_,
        completeness_criteria=criteria,
        weight_in_topic=float(getattr(m, "weight_in_topic", 0.0) or 0.0),
        fra_required=bool(getattr(m, "fra_required", False)),
    )


def _serialise(obj: Any) -> Any:
    """Recursively make a scoring result JSON-serialisable."""
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if isinstance(obj, dict):
        return {k: _serialise(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_serialise(i) for i in obj]
    return obj


def _validate_sector(sector: str) -> str:
    """Return the normalised uppercase sector or raise HTTP 422."""
    key = sector.upper()
    if key not in _VALID_SECTORS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="sector must be FINANCIAL or MANUFACTURING",
        )
    return key


# ---------------------------------------------------------------------------
# POST /scoring/score-document
# ---------------------------------------------------------------------------


@router.post(
    "/score-document",
    status_code=status.HTTP_200_OK,
    summary="Run full spec-compliant scoring for a document",
)
async def score_document_endpoint(
    body: ScoreDocumentRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Load a document's extracted metrics, score them, persist results, return output.

    Steps:
    1. Resolve document → report_id
    2. Load all ``ExtractedMetric`` rows for that report
    3. Convert to ``MetricScoreInput`` list
    4. Call ``score_document()`` (full 9-step pipeline)
    5. Persist composite score fields back to the ``Report`` row
    6. Return the full scoring result dict
    """
    try:
        sector = _validate_sector(body.sector)

        # 1 — resolve document
        doc_res = await db.execute(select(Document).where(Document.id == body.document_id))
        doc = doc_res.scalar_one_or_none()
        if doc is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found",
            )
        if doc.report_id is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Document has no linked report — run the extraction pipeline first",
            )

        # 2 — load metrics
        m_res = await db.execute(
            select(ExtractedMetric).where(ExtractedMetric.report_id == doc.report_id)
        )
        metrics = list(m_res.scalars().all())
        if not metrics:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="No extracted metrics found for this document",
            )

        # 3 — convert
        inputs: list[MetricScoreInput] = [_metric_to_score_input(m) for m in metrics]

        # 4 — score
        result = score_document(
            sector=sector,
            extracted_metrics=inputs,
            external_assurance=body.external_assurance,
        )

        # 5 — persist to Report
        rpt_res = await db.execute(select(Report).where(Report.id == doc.report_id))
        report = rpt_res.scalar_one_or_none()
        if report is not None:
            composite = result.get("composite", {})
            report.total_score = composite.get("final_score")
            # Store pillar scores: gri_score=E, fra_score=G, sasb_score=S
            pillar = result.get("pillar_scores", {})
            report.gri_score = round(pillar.get("E", 0.0) * 100, 1)
            report.fra_score = round(pillar.get("G", 0.0) * 100, 1)
            report.sasb_score = round(pillar.get("S", 0.0) * 100, 1)
            await db.flush()

        log.info(
            "scoring.score_document",
            document_id=str(body.document_id),
            sector=sector,
            n_metrics=len(metrics),
        )
        # 6 — return serialised result
        return _serialise(result)

    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        log.exception("scoring.score_document_error", document_id=str(body.document_id), error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Scoring failed due to an unexpected server error",
        ) from exc


# ---------------------------------------------------------------------------
# GET /scoring/weights/{sector}
# ---------------------------------------------------------------------------


@router.get(
    "/weights/{sector}",
    status_code=status.HTTP_200_OK,
    summary="Return the weight registry for a sector",
)
async def get_sector_weights(sector: str) -> dict:
    """Return pillar, topic, and metric weights for FINANCIAL or MANUFACTURING.

    Useful for UI transparency panels and debugging weight configurations.
    """
    key = _validate_sector(sector)
    try:
        registry = get_weight_registry(key)
        return {
            "sector":         registry.sector,
            "pillar_weights": registry.pillar_weights,
            "topic_weights":  registry.topic_weights,
            "metric_weights": registry.metric_weights,
            "fra_topic_map":  registry.fra_topic_map,
        }
    except HTTPException:
        raise
    except Exception as exc:
        log.exception("scoring.weights_error", sector=sector, error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Registry load failed due to an unexpected server error",
        ) from exc


# ---------------------------------------------------------------------------
# GET /scoring/fra-registry
# ---------------------------------------------------------------------------


@router.get(
    "/fra-registry",
    status_code=status.HTTP_200_OK,
    summary="Return the full FRA KPI registry",
)
async def get_fra_registry() -> dict:
    """Return all 17 FRA KPIs with metadata (mandatory flag, sub-KPI count, pillar)."""
    return FRA_KPI_REGISTRY


# ---------------------------------------------------------------------------
# POST /scoring/gap-analysis
# ---------------------------------------------------------------------------


@router.post(
    "/gap-analysis",
    status_code=status.HTTP_200_OK,
    summary="Return gap analysis and improvement roadmap for an existing scored report",
)
async def get_gap_analysis(
    body: GapAnalysisRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Re-derive gap analysis from a report's stored pillar / topic scores.

    Does NOT re-run full scoring — reads persisted score columns on the
    ``Report`` row and the associated ``ExtractedMetric`` rows, then
    re-runs only gap analysis and roadmap generation.

    Returns:
        A dict with keys: ``gap_analysis``, ``improvement_roadmap``,
        ``fra_compliance``.
    """
    try:
        rpt_res = await db.execute(select(Report).where(Report.id == body.report_id))
        report = rpt_res.scalar_one_or_none()
        if report is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Report not found",
            )

        if report.total_score is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Report has not been scored yet — run score-document first",
            )

        # Reconstruct pillar scores from legacy columns:
        # gri_score=E, fra_score=G, sasb_score=S (as stored by score-document).
        pillar_scores_pct = {
            "E": report.gri_score or 0.0,
            "S": report.sasb_score or 0.0,
            "G": report.fra_score or 0.0,
        }

        # Derive sector from report frameworks list (best-effort).
        frameworks = report.frameworks or []
        sector = "FINANCIAL"
        if "MFG" in " ".join(str(f) for f in frameworks).upper():
            sector = "MANUFACTURING"

        registry = get_weight_registry(sector)

        # Build approximate topic scores: equal distribution within pillar.
        # (Approximation — we only have pillar-level persisted scores.)
        topic_scores: dict[str, float] = {}
        topic_to_pillar: dict[str, str] = {}
        flat_topic_weights: dict[str, float] = {}

        for pillar, tw in registry.topic_weights.items():
            pillar_score_01 = pillar_scores_pct.get(pillar, 0.0) / 100.0
            for tid, w in tw.items():
                topic_scores[tid] = pillar_score_01
                topic_to_pillar[tid] = pillar
                flat_topic_weights[tid] = w

        fra_results = extract_fra_results_from_scores(topic_scores, registry.fra_topic_map)
        gate_result = check_fra_gate(fra_results)

        gap_results = generate_gap_analysis(
            topic_scores=topic_scores,
            topic_weights=flat_topic_weights,
            pillar_weights=registry.pillar_weights,
            topic_to_pillar=topic_to_pillar,
        )

        roadmap = generate_improvement_roadmap(
            gap_analysis_results=gap_results,
            fra_gate_result=gate_result,
            sector=sector,
            fra_kpi_results=fra_results,
        )

        return {
            "report_id":           str(body.report_id),
            "sector":              sector,
            "pillar_scores_pct":   pillar_scores_pct,
            "total_score":         report.total_score,
            "fra_compliance":      gate_result,
            "gap_analysis":        gap_results,
            "improvement_roadmap": roadmap,
        }

    except HTTPException:
        raise
    except Exception as exc:
        log.exception("scoring.gap_analysis_error", report_id=str(body.report_id), error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Gap analysis failed due to an unexpected server error",
        ) from exc
