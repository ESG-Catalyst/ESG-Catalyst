"""Celery async tasks — wires the full extraction pipeline together.

Pipeline sequence (7 stages):
    1. ingest    — parse file into structured text (M1)
    2. chunk     — split into retrieval-ready windows (M1/M2)
    3. classify  — filter for ESG-relevant chunks via arch-B ensemble (M2)
    4. embed     — store chunks in per-language ChromaDB collections (M2)
    5. extract   — per-indicator retrieval + LLM calls (M3)
    6. score     — sector-aware disclosure-quality scoring v1 (M4)
    7. persist   — write metrics + report scores to Postgres (M6)

Report generation is a *separate* Celery task (``report.generate``)
triggered after at least one metric is approved. It re-runs scoring, builds
sections, generates LLM narratives, and renders the PDF. It does NOT
re-run extraction.

Each step has clean typed inputs/outputs so the Iteration 3 LangGraph
transition only needs to wrap these same calls in agent nodes.

Usage:
    from app.workers.tasks import run_extraction_pipeline

    result = run_extraction_pipeline.delay(
        document_id="...",
        company_id="...",
        report_id="...",
    )
    print(result.id)  # Celery task ID for status polling
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any, Optional

import structlog
from sqlalchemy import select, update

from app.config import settings
from app.core.exceptions import (
    ESGCatalystError,
    ExtractionError,
    IngestionError,
    LLMUnavailableError,
    ReportError,
    ScoringError,
)
from app.core.nlp.chunker import chunk_document
from app.core.nlp.classifier import classify_chunks
from app.core.extraction.extractor import extract_metrics
from app.core.ingestion.parser import ingest_document
from app.core.scoring.scorer import score_report
from app.database import Base, get_engine, get_session_factory
from app.models.document import Document
from app.models.enums import DocumentStatus, ReportStatus
from app.models.metric import ExtractedMetric
from app.models.report import Report
from app.workers.celery_app import celery_app

logger = structlog.get_logger(__name__)


class NoTextExtractedError(Exception):
    """Ingestion produced zero text — pipeline cannot proceed.

    Raised after parse for image-only docs (OCR not yet implemented) or
    any other format that yields an empty body. Caught specially by the
    Celery wrapper so it does NOT retry — there is no transient cause.
    """


@celery_app.task(
    bind=True,
    name="pipeline.run_extraction",
    max_retries=2,
    default_retry_delay=30,
)
def run_extraction_pipeline(
    self,
    document_ids: list[str],
    company_id: str,
    report_id: str,
    indicator_codes: Optional[list[str]] = None,
) -> dict[str, Any]:
    """Run the full extraction pipeline for a set of documents.

    Args:
        document_id: UUID of the uploaded document.
        company_id: UUID of the company.
        report_id: UUID of the report to populate.
        indicator_codes: Specific GRI codes to extract. None → all 13.

    Returns:
        Dict with task results (scores, metric count, gaps).
    """
    logger.info(
        "pipeline.start",
        task_id=self.request.id,
        document_ids=document_ids,
        company_id=company_id,
        report_id=report_id,
    )

    # Run the async pipeline inside Celery's sync worker
    try:
        result = asyncio.run(
            _run_pipeline_async(
                task=self,
                document_ids=[uuid.UUID(d) for d in document_ids],
                company_id=uuid.UUID(company_id),
                report_id=uuid.UUID(report_id),
                indicator_codes=indicator_codes,
            )
        )
        logger.info("pipeline.complete", task_id=self.request.id, **result)
        return result

    except NoTextExtractedError as exc:
        # Permanent: zero-text doc will never produce text on retry.
        # Document.error_message was already written by _run_pipeline_async.
        logger.warning(
            "pipeline.no_text",
            task_id=self.request.id,
            document_ids=document_ids,
            error=str(exc),
        )
        raise

    except LLMUnavailableError as exc:
        # Both primary and fallback LLM failed — log as error, mark failed,
        # but do NOT retry (retrying a billing failure is pointless).
        logger.error(
            "pipeline.llm_unavailable",
            task_id=self.request.id,
            document_ids=document_ids,
            error=str(exc),
        )
        asyncio.run(_mark_documents_failed(document_ids, str(exc)))
        raise

    except ESGCatalystError as exc:
        # Known pipeline-stage failure — log with stage context, mark failed,
        # and retry up to max_retries (transient infra issues may resolve).
        logger.error(
            "pipeline.stage_error",
            task_id=self.request.id,
            document_ids=document_ids,
            exc_type=type(exc).__name__,
            error=str(exc),
        )
        asyncio.run(_mark_documents_failed(document_ids, str(exc)))
        raise self.retry(exc=exc) if self.request.retries < self.max_retries else exc

    except Exception as exc:
        # Unexpected failure — wrap in context for observability.
        logger.error(
            "pipeline.failed",
            task_id=self.request.id,
            document_ids=document_ids,
            exc_type=type(exc).__name__,
            error=str(exc),
        )
        asyncio.run(_mark_documents_failed(document_ids, str(exc)))
        raise self.retry(exc=exc) if self.request.retries < self.max_retries else exc


async def _run_pipeline_async(
    task,
    document_ids: list[uuid.UUID],
    company_id: uuid.UUID,
    report_id: uuid.UUID,
    indicator_codes: Optional[list[str]] = None,
) -> dict[str, Any]:
    """Async pipeline orchestration — called from the sync Celery task.

    Processes a SET of documents: each is ingested -> chunked -> classified ->
    embedded into the shared ChromaDB pool (tagged by report_id), then a single
    extraction pass runs over the pool with per-metric source attribution.
    """

    factory = get_session_factory()

    # ── 1. Fetch all documents in the set + company sector ────────────
    async with factory() as session:
        result = await session.execute(
            select(Document).where(Document.id.in_(document_ids))
        )
        doc_map = {d.id: d for d in result.scalars().all()}
        docs = [doc_map[did] for did in document_ids if did in doc_map]
        if not docs:
            raise ValueError(f"No documents found for {document_ids}")

        # Look up the company's sector (industry) — scorer needs it for the
        # sector-specific materiality_weights lookup. Default to "banking"
        # with a warning if missing, so a misconfigured company row doesn't
        # take the pipeline down.
        from app.models.company import Company
        company_record = (
            await session.execute(select(Company).where(Company.id == company_id))
        ).scalar_one_or_none()
        if company_record is None or not (company_record.industry or "").strip():
            logger.warning(
                "pipeline.company_sector_missing",
                company_id=str(company_id),
                falling_back_to="banking",
            )
            sector = "banking"
        else:
            sector = company_record.industry.lower()

        # Mark every document in the set as processing.
        await session.execute(
            update(Document)
            .where(Document.id.in_(document_ids))
            .values(status=DocumentStatus.processing)
        )
        await session.commit()

    n_docs = len(docs)
    total_embedded = 0
    fallback_parts: list[str] = []
    doc_meta: dict[uuid.UUID, tuple[Optional[int], Optional[str]]] = {}
    any_text = False

    from app.core.nlp.embedder import embed_and_store

    # ── 2-4. Per document: ingest → chunk → classify → embed (shared pool) ─
    for i, doc in enumerate(docs, start=1):
        _update_state(task, "INGESTING", f"Parsing document {i}/{n_docs}...")
        ingested = ingest_document(doc.file_path)
        doc_meta[doc.id] = (ingested.page_count, ingested.language)
        logger.info(
            "pipeline.ingested",
            document_id=str(doc.id),
            file=doc.filename,
            pages=ingested.page_count,
            chars=len(ingested.full_text),
        )
        # One empty document must not sink the whole set — skip it and keep
        # going; the whole-set guard below fails only if ALL are empty.
        if not ingested.full_text.strip():
            logger.warning("pipeline.doc_empty", document_id=str(doc.id), file=doc.filename)
            continue
        any_text = True

        _update_state(task, "CHUNKING", f"Splitting document {i}/{n_docs}...")
        chunks = chunk_document(ingested)

        _update_state(task, "CLASSIFYING", f"Filtering ESG content {i}/{n_docs}...")
        classified = classify_chunks(chunks, threshold=0.3, use_climate_model=True)
        relevant_chunks = [c.chunk for c in classified if c.is_relevant]
        logger.info(
            "pipeline.classified",
            document_id=str(doc.id),
            total=len(classified),
            relevant=len(relevant_chunks),
        )

        _update_state(task, "EMBEDDING", f"Embedding document {i}/{n_docs}...")
        chunks_to_embed = relevant_chunks if len(relevant_chunks) >= 3 else chunks
        embed_and_store(
            chunks_to_embed,
            company_id=str(company_id),
            report_id=str(report_id),
            document_id=str(doc.id),
            filename=doc.filename,
        )
        total_embedded += len(chunks_to_embed)
        # Per-doc fallback text (only used if ChromaDB is unreachable).
        if len(relevant_chunks) >= 3:
            fallback_parts.append("\n\n".join(c.text for c in relevant_chunks))
        else:
            fallback_parts.append(ingested.full_text)

    # ── 2a. Whole-set zero-text guard ─────────────────────────────────
    if not any_text:
        msg = (
            "Could not extract any text from the uploaded document(s) — they may be "
            "empty, image-only (OCR not implemented), password-protected, or corrupted."
        )
        for doc in docs:
            await _mark_document_failed_async(doc.id, msg)
        raise NoTextExtractedError(msg)

    extraction_text = "\n\n".join(fallback_parts)

    _update_state(task, "EXTRACTING", "Extracting ESG metrics via LLM...")

    # ── 5. Extraction — ONE pooled pass over ALL docs' chunks ─────────
    # Retrieval filters by report_id, so chunks from every document in the set
    # compete for each indicator; each metric is then attributed to the source
    # document of its winning evidence chunk. ~46 LLM calls total, not 46 × N.
    metrics = await extract_metrics(
        company_id=company_id,
        report_id=report_id,
        indicator_codes=indicator_codes,
        document_id=docs[0].id,
        n_chunks_processed=total_embedded,
        document_text=extraction_text,  # combined fallback if ChromaDB is down
    )
    logger.info("pipeline.extracted", metrics=len(metrics), documents=n_docs)

    _update_state(task, "SCORING", "Computing ESG scores...")

    # ── 6. Scoring — sector-aware disclosure quality (v1 methodology) ─
    scoring_result = score_report(metrics, sector=sector, indicator_codes=indicator_codes)

    _update_state(task, "PERSISTING", "Saving results to database...")

    # ── 7. Persist metrics + update report scores in DB ───────────────
    async with factory() as session:
        # Insert extracted metrics
        for m in metrics:
            metric_row = ExtractedMetric(
                id=uuid.uuid4(),
                company_id=m.company_id,
                report_id=m.report_id,
                gri_code=m.gri_code,
                fra_code=m.fra_code,
                sasb_code=m.sasb_code,
                label=m.label,
                value=m.value,
                unit=m.unit,
                original_value=m.original_value,
                original_unit=m.original_unit,
                confidence=m.confidence,
                status=m.status,
                source_file=m.source_file,
                source_page=m.source_page,
                evidence_chunk=m.evidence_chunk,
                extraction_method=m.extraction_method,
                note=m.note,
                # Restore fields the extractor sets but this hand-written ORM
                # construction previously dropped — they were left NULL in the
                # DB, which (for pillar) broke the E/S/G filter on the review page.
                framework=m.framework,
                metric_type=m.metric_type,
                sector_standard_ref=m.sector_standard_ref,
                currency=m.currency,
                reporting_period_start=m.reporting_period_start,
                reporting_period_end=m.reporting_period_end,
                breakdown=m.breakdown,
                pillar=m.pillar,
                topic=m.topic,
            )
            session.add(metric_row)

        # Update report with scores. All 7 fields come from the same
        # ScoringResult so the dashboard (which reads these) shows the
        # same numbers as the PDF (which renders from the same scorer).
        await session.execute(
            update(Report)
            .where(Report.id == report_id)
            .values(
                total_score=scoring_result.total_score,
                gri_score=scoring_result.gri_score,
                fra_score=scoring_result.fra_score,
                sasb_score=scoring_result.sasb_score,
                environmental_score=scoring_result.environmental_score,
                social_score=scoring_result.social_score,
                governance_score=scoring_result.governance_score,
                status=ReportStatus.in_review,
            )
        )

        # Mark every document in the set as processed (each with its own page
        # count + language captured during ingestion).
        for doc in docs:
            pc, lang = doc_meta.get(doc.id, (None, None))
            await session.execute(
                update(Document)
                .where(Document.id == doc.id)
                .values(
                    status=DocumentStatus.processed,
                    page_count=pc,
                    language=lang,
                )
            )

        await session.commit()

    logger.info(
        "pipeline.persisted",
        metrics=len(metrics),
        total_score=scoring_result.total_score,
    )

    # ── 8. Build result summary ───────────────────────────────────────
    return {
        "document_id": str(docs[0].id),
        "document_ids": [str(d.id) for d in docs],
        "documents": n_docs,
        "company_id": str(company_id),
        "report_id": str(report_id),
        "chunks_total": total_embedded,
        "metrics_extracted": scoring_result.indicators_found,
        "metrics_total": scoring_result.indicators_total,
        "total_score": scoring_result.total_score,
        "gri_score": scoring_result.gri_score,
        "fra_score": scoring_result.fra_score,
        "sasb_score": scoring_result.sasb_score,
        "coverage_pct": scoring_result.coverage_pct,
        "gaps": [
            {
                "code": g.code,
                "name": g.name,
                "status": g.status,
                "recommendation": g.recommendation,
            }
            for g in scoring_result.gaps
        ],
    }


async def _mark_documents_failed(document_ids: list[str], msg: str) -> None:
    """Mark every document in a set as failed (used by the task error handlers)."""
    for did in document_ids:
        await _mark_document_failed(did, msg)


def _update_state(task, state: str, status: str) -> None:
    """Update Celery task meta so /extraction/status can report progress."""
    if task and task.request.id:
        task.update_state(state=state, meta={"status": status})


@celery_app.task(
    bind=True,
    name="report.generate",
    max_retries=1,
    default_retry_delay=30,
)
def generate_report_task(self, report_id: str) -> dict[str, Any]:
    """Build sections + narratives + PDF for *report_id*.

    Reads metrics, the parent Company, and the Report row, runs the M5
    pipeline (builder → narrative → renderer), writes the PDF under
    ``data/generated_reports/<report_id>/``, and stores the path on the
    Report row.
    """
    logger.info("report.generate.start", task_id=self.request.id, report_id=report_id)
    try:
        result = asyncio.run(_generate_report_async(self, uuid.UUID(report_id)))
        logger.info("report.generate.complete", task_id=self.request.id, **result)
        return result
    except LLMUnavailableError as exc:
        # Both primary and fallback LLM failed — no point retrying a billing issue.
        logger.error(
            "report.generate.llm_unavailable",
            task_id=self.request.id,
            report_id=report_id,
            error=str(exc),
        )
        asyncio.run(_mark_report_failed(report_id))
        raise
    except (ReportError, ESGCatalystError) as exc:
        logger.error(
            "report.generate.stage_error",
            task_id=self.request.id,
            report_id=report_id,
            exc_type=type(exc).__name__,
            error=str(exc),
        )
        asyncio.run(_mark_report_failed(report_id))
        raise self.retry(exc=exc) if self.request.retries < self.max_retries else exc
    except Exception as exc:
        logger.error(
            "report.generate.failed",
            task_id=self.request.id,
            report_id=report_id,
            exc_type=type(exc).__name__,
            error=str(exc),
        )
        asyncio.run(_mark_report_failed(report_id))
        raise self.retry(exc=exc) if self.request.retries < self.max_retries else exc


async def _generate_report_async(task, report_id: uuid.UUID) -> dict[str, Any]:
    """Async M5 driver: pull data from DB, render PDF, persist pdf_path."""
    from pathlib import Path

    from app.core.reporting.builder import CompanyProfile, build_report_sections
    from app.core.reporting.narrative import generate_narratives
    from app.core.reporting.renderer import render_pdf
    from app.core.scoring.scorer import score_report
    from app.models.company import Company

    factory = get_session_factory()

    async with factory() as session:
        report_row = (
            await session.execute(select(Report).where(Report.id == report_id))
        ).scalar_one_or_none()
        if report_row is None:
            raise ValueError(f"Report {report_id} not found")

        company_row = (
            await session.execute(select(Company).where(Company.id == report_row.company_id))
        ).scalar_one_or_none()
        if company_row is None:
            raise ValueError(f"Company {report_row.company_id} not found for report")

        metric_rows = (
            await session.execute(
                select(ExtractedMetric).where(ExtractedMetric.report_id == report_id)
            )
        ).scalars().all()

    _update_state(task, "BUILDING", "Building report sections...")

    # sector for scorer's materiality_weights lookup — fall back to banking
    # if the company row has no industry set, so an unconfigured company
    # doesn't crash report generation.
    if not (company_row.industry or "").strip():
        logger.warning(
            "report.generate.company_sector_missing",
            company_id=str(company_row.id),
            falling_back_to="banking",
        )
        sector = "banking"
    else:
        sector = company_row.industry.lower()

    company_profile = CompanyProfile(
        name=company_row.name,
        sector=sector,
        reporting_period=str(report_row.reporting_year),
        headquarters=company_row.country or "",
    )

    score = score_report(list(metric_rows), sector=sector)
    bundle = build_report_sections(metrics=list(metric_rows), score=score, company=company_profile)

    _update_state(task, "NARRATING", "Generating narratives...")
    bundle.sections = await generate_narratives(bundle.sections)

    _update_state(task, "RENDERING", "Rendering PDF...")
    out_dir = Path("data/generated_reports") / str(report_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    safe_company = "".join(c for c in company_row.name if c.isalnum() or c in "-_") or "company"
    output_path = out_dir / f"{safe_company}_ESG_report.pdf"
    final_path = render_pdf(bundle, output_path)

    # Re-persist all 7 score fields from the live ScoringResult. Metrics
    # may have been approved/rejected between pipeline-time and now, so
    # this snapshot is the one the PDF was rendered from — the dashboard
    # must read these same values.
    async with factory() as session:
        await session.execute(
            update(Report)
            .where(Report.id == report_id)
            .values(
                pdf_path=str(final_path),
                status=ReportStatus.published,
                total_score=score.total_score,
                gri_score=score.gri_score,
                fra_score=score.fra_score,
                sasb_score=score.sasb_score,
                environmental_score=score.environmental_score,
                social_score=score.social_score,
                governance_score=score.governance_score,
            )
        )
        await session.commit()

    return {
        "report_id": str(report_id),
        "pdf_path": str(final_path),
        "sections": len(bundle.sections),
        "metrics": len(metric_rows),
    }


async def _mark_report_failed(report_id: str) -> None:
    try:
        factory = get_session_factory()
        async with factory() as session:
            await session.execute(
                update(Report)
                .where(Report.id == uuid.UUID(report_id))
                .values(status=ReportStatus.draft)
            )
            await session.commit()
    except Exception as exc:
        logger.error("report.mark_failed_error", error=str(exc))


async def _mark_document_failed_async(
    document_id: uuid.UUID | str,
    error_message: str | None = None,
) -> None:
    """Inside-the-event-loop version. Use this from _run_pipeline_async."""
    try:
        factory = get_session_factory()
        async with factory() as session:
            doc_uuid = document_id if isinstance(document_id, uuid.UUID) else uuid.UUID(document_id)
            values: dict[str, Any] = {"status": DocumentStatus.failed}
            if error_message is not None:
                values["error_message"] = error_message
            await session.execute(
                update(Document).where(Document.id == doc_uuid).values(**values)
            )
            await session.commit()
    except Exception as exc:
        logger.error("pipeline.mark_failed_error", error=str(exc))


async def _mark_document_failed(
    document_id: str,
    error_message: str | None = None,
) -> None:
    """Sync-wrapper-callable: mark document failed (optionally with message)."""
    await _mark_document_failed_async(document_id, error_message)
