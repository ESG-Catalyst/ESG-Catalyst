"""Scoring API — expose the spec-compliant scoring engine via four endpoints.

Endpoints:
    POST /api/v1/scoring/score-document   full pipeline for a document
    GET  /api/v1/scoring/weights/{sector} weight registry transparency
    GET  /api/v1/scoring/fra-registry     FRA KPI registry
    POST /api/v1/scoring/gap-analysis     gap analysis for an existing report
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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

router = APIRouter(prefix="/api/v1/scoring", tags=["scoring"])


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------

class ScoreDocumentRequest(BaseModel):
    document_id: UUID
    sector: str = "FINANCIAL"
    external_assurance: bool = False


class GapAnalysisRequest(BaseModel):
    report_id: UUID


# ---------------------------------------------------------------------------
# Helpers
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
    """Convert an ExtractedMetric ORM object to a MetricScoreInput.

    Priority for metric_code: fra_code > gri_code > sasb_code.
    Falls back to gri_code when no scoring-specific code is available.
    """
    code = m.fra_code or m.gri_code or m.sasb_code or str(m.id)

    raw_mt  = str(getattr(m, "metric_type",  "quantitative") or "quantitative").lower()
    raw_dir = str(getattr(m, "direction",     "neutral")      or "neutral").lower()

    mt  = _MT_MAP.get(raw_mt,  MetricType.QUANTITATIVE)
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


# ---------------------------------------------------------------------------
# POST /api/v1/scoring/score-document
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
    1. Resolve document -> report_id
    2. Load all ExtractedMetric rows for that report
    3. Convert to MetricScoreInput list
    4. Call score_document() (full 9-step pipeline)
    5. Persist composite score fields back to the Report row
    6. Return the full scoring result dict
    """
    try:
        # 1 — resolve document
        doc_res = await db.execute(select(Document).where(Document.id == body.document_id))
        doc = doc_res.scalar_one_or_none()
        if doc is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
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
        sector = body.sector.upper()
        if sector not in ("FINANCIAL", "MANUFACTURING"):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="sector must be FINANCIAL or MANUFACTURING",
            )
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
            # Store pillar scores in existing legacy columns where available
            pillar = result.get("pillar_scores", {})
            # gri_score reused as E pillar, fra_score reused as G, sasb_score as S
            report.gri_score  = round(pillar.get("E", 0.0) * 100, 1)
            report.fra_score  = round(pillar.get("G", 0.0) * 100, 1)
            report.sasb_score = round(pillar.get("S", 0.0) * 100, 1)
            await db.flush()

        # 6 — return (serialise MetricScoreOutput objects)
        return _serialise(result)

    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Scoring failed: {exc}",
        ) from exc


# ---------------------------------------------------------------------------
# GET /api/v1/scoring/weights/{sector}
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
    key = sector.upper()
    if key not in ("FINANCIAL", "MANUFACTURING"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="sector must be FINANCIAL or MANUFACTURING",
        )
    try:
        registry = get_weight_registry(key)
        return {
            "sector":          registry.sector,
            "pillar_weights":  registry.pillar_weights,
            "topic_weights":   registry.topic_weights,
            "metric_weights":  registry.metric_weights,
            "fra_topic_map":   registry.fra_topic_map,
        }
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Registry load failed: {exc}",
        ) from exc


# ---------------------------------------------------------------------------
# GET /api/v1/scoring/fra-registry
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
# POST /api/v1/scoring/gap-analysis
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
    """Re-derive gap analysis from a report's stored pillar/topic scores.

    This endpoint does NOT re-run scoring — it reads the score columns already
    persisted on the Report row and the associated ExtractedMetric rows, then
    re-runs only the gap analysis and roadmap generation.

    Returns:
        {gap_analysis, improvement_roadmap, fra_compliance}
    """
    try:
        rpt_res = await db.execute(select(Report).where(Report.id == body.report_id))
        report = rpt_res.scalar_one_or_none()
        if report is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")

        if report.total_score is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Report has not been scored yet — run score-document first",
            )

        # Reconstruct pillar scores from the legacy columns
        # gri_score=E, fra_score=G, sasb_score=S (as stored by score-document)
        pillar_scores_pct = {
            "E": report.gri_score  or 0.0,
            "S": report.sasb_score or 0.0,
            "G": report.fra_score  or 0.0,
        }

        # Derive sector from report frameworks list (best-effort)
        frameworks = report.frameworks or []
        sector = "FINANCIAL"
        if "MFG" in " ".join(str(f) for f in frameworks).upper():
            sector = "MANUFACTURING"

        registry = get_weight_registry(sector)

        # Build approximate topic scores: equal distribution within pillar
        # (this is an approximation since we only have pillar-level persisted scores)
        topic_scores: dict[str, float] = {}
        topic_to_pillar: dict[str, str] = {}
        flat_topic_weights: dict[str, float] = {}

        for pillar, tw in registry.topic_weights.items():
            pillar_score_01 = pillar_scores_pct.get(pillar, 0.0) / 100.0
            for tid, w in tw.items():
                topic_scores[tid] = pillar_score_01
                topic_to_pillar[tid] = pillar
                flat_topic_weights[tid] = w

        # FRA gate
        fra_results = extract_fra_results_from_scores(topic_scores, registry.fra_topic_map)
        gate_result = check_fra_gate(fra_results)

        # Gap analysis
        gap_results = generate_gap_analysis(
            topic_scores=topic_scores,
            topic_weights=flat_topic_weights,
            pillar_weights=registry.pillar_weights,
            topic_to_pillar=topic_to_pillar,
        )

        # Improvement roadmap
        roadmap = generate_improvement_roadmap(
            gap_analysis_results=gap_results,
            fra_gate_result=gate_result,
            sector=sector,
            fra_kpi_results=fra_results,
        )

        return {
            "report_id":          str(body.report_id),
            "sector":             sector,
            "pillar_scores_pct":  pillar_scores_pct,
            "total_score":        report.total_score,
            "fra_compliance":     gate_result,
            "gap_analysis":       gap_results,
            "improvement_roadmap": roadmap,
        }

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Gap analysis failed: {exc}",
        ) from exc
