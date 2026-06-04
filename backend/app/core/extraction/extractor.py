"""ESG metric extraction — per-indicator ChromaDB retrieval + LLM calls.

Iteration 2: each indicator retrieves its own top-k relevant chunks from
ChromaDB (cosine similarity against the indicator's code + name query),
so the LLM only sees focused context (~1-3 KB) instead of the full 60 KB
document blob.  Falls back to full-document mode if ChromaDB is unreachable.

Usage:
    from app.core.extraction.extractor import extract_metrics

    metrics = await extract_metrics(
        source_file="report.pdf",
        company_id=company_uuid,
        report_id=report_uuid,
    )
"""

from __future__ import annotations

import json
import re
import time
from uuid import UUID

import structlog
from langchain_core.messages import HumanMessage, SystemMessage

from app.config import settings
from app.core.exceptions import LLMUnavailableError
from app.core.extraction.prompts import SYSTEM_PROMPT, build_user_prompt
from app.core.extraction.validator import (
    clamp,
    normalize_currency,
    parse_monetary,
    safe_float,
    safe_int,
)
from app.core.gri.indicators import get_all_indicators, get_indicator
from app.core.llm.router import model_router
from app.core.tracking.mlflow_tracker import (
    log_json_artifact,
    log_metric,
    log_metrics,
    log_params,
    sanitize_metric_key,
    start_extraction_run,
)
from app.models.enums import (
    ExtractionMethod,
    MetricFramework,
    MetricStatus,
    MetricType,
    PillarType,
)
from app.schemas.metric import ExtractedMetricCreate

logger = structlog.get_logger(__name__)

# Truncation guard — full-doc fallback mode (~15k tokens)
_MAX_DOCUMENT_CHARS = 60_000

# ── ChromaDB retrieval helpers ───────────────────────────────────────────
_chroma_client = None


def _get_chroma_client():
    """Lazy singleton for the ChromaDB HTTP client."""
    global _chroma_client
    if _chroma_client is None:
        import chromadb
        _chroma_client = chromadb.HttpClient(
            host=settings.chroma_host, port=settings.chroma_port,
        )
    return _chroma_client


def _build_retrieval_query(indicator: dict) -> str:
    """Build a semantic-search query string from an indicator's metadata.

    Uses the GRI code + name (+ sector ref if present) — these are always
    English so we hardcode lang="en" at embed time.
    """
    parts = [indicator["code"], indicator["name"]]
    ref = indicator.get("sector_standard_ref")
    if ref:
        parts.append(ref)
    return " ".join(parts)


def _retrieve_chunks_for_indicator(
    indicator: dict,
    report_id: str,
    top_k: int,
) -> list[dict]:
    """Retrieve the top-k chunks for one indicator from ChromaDB.

    Queries both ``document_chunks_en`` and ``document_chunks_ar`` collections,
    merges results, deduplicates by text, and sorts by cosine distance (ascending).

    Each collection is queried with a vector from the **matching** embedding
    model (EN → 768-d e5-base, AR → 1024-d bge-m3) to avoid dimension
    mismatch errors.

    Returns a list of dicts: ``{"text": str, "language": str, "distance": float, ...}``.
    Raises on connection error so the caller can fall back to full-doc mode.
    """
    from app.core.nlp.embedder import embed_query

    query_text = _build_retrieval_query(indicator)

    client = _get_chroma_client()
    # Pool across every document in the set: filter by report_id, not a single
    # source_file. Chunks from all docs compete; provenance is recovered per
    # chunk from its "filename" metadata.
    where_filter = {"report_id": report_id}
    include = ["documents", "metadatas", "distances"]

    merged: list[dict] = []
    for coll_name, lang in (("document_chunks_en", "en"), ("document_chunks_ar", "ar")):
        try:
            collection = client.get_collection(name=coll_name)
        except Exception as exc:
            # Collection doesn't exist yet or ChromaDB API mismatch — skip.
            # ChromaDB raises different exception types across versions so
            # we intentionally catch broadly; log at debug to aid diagnosis.
            logger.debug(
                "extractor.collection_not_found",
                collection=coll_name,
                error=str(exc),
            )
            continue

        # Generate query vector with the model that matches this collection's
        # embedding dimension (EN → 768-d e5-base, AR → 1024-d bge-m3).
        query_vec = embed_query(query_text, lang=lang).tolist()

        try:
            results = collection.query(
                query_embeddings=[query_vec],
                n_results=top_k,
                where=where_filter,
                include=include,
            )
        except Exception as exc:
            logger.warning(
                "extractor.chromadb_query_failed",
                collection=coll_name,
                error=str(exc),
            )
            continue

        if results and results.get("ids") and results["ids"][0]:
            for chunk_id, doc, meta, dist in zip(
                results["ids"][0],
                results["documents"][0],
                results["metadatas"][0] or [],
                results["distances"][0],
            ):
                chunk_lang = (meta or {}).get("language", lang)
                merged.append({
                    "chunk_id": chunk_id,
                    "text": doc or "",
                    "language": chunk_lang,
                    "distance": float(dist),
                    "page_number": (meta or {}).get("page_number"),
                    "section_header": (meta or {}).get("section_header"),
                    "source_filename": (meta or {}).get("filename") or (meta or {}).get("source_file"),
                })

    # Deduplicate by text content, keep lowest distance
    seen_texts: dict[str, dict] = {}
    for item in merged:
        txt = item["text"]
        if txt not in seen_texts or item["distance"] < seen_texts[txt]["distance"]:
            seen_texts[txt] = item
    deduped = sorted(seen_texts.values(), key=lambda x: x["distance"])

    return deduped[:top_k]


def _format_retrieved_chunks(chunks: list[dict]) -> str:
    """Format retrieved chunks into the prompt string."""
    parts: list[str] = []
    for i, chunk in enumerate(chunks, 1):
        lang = chunk.get("language", "en").upper()
        parts.append(f"[Chunk {i} — {lang}]\n{chunk['text']}")
    return "\n\n".join(parts)


# ── Public API ───────────────────────────────────────────────────────────
async def extract_metrics(
    company_id: UUID,
    report_id: UUID,
    source_file: str | None = None,
    indicator_codes: list[str] | None = None,
    document_id: UUID | None = None,
    n_chunks_processed: int | None = None,
    document_text: str | None = None,
) -> list[ExtractedMetricCreate]:
    """Extract ESG metrics via per-indicator ChromaDB retrieval + LLM calls.

    Each indicator builds a semantic query from its code + name, retrieves
    the top-k most relevant chunks from ChromaDB, and sends only those
    focused chunks to the LLM.  If ChromaDB is unreachable, falls back to
    the full ``document_text`` blob (Iteration 1 behavior).

    Args:
        company_id: UUID of the company being evaluated.
        report_id: UUID of the report being generated.
        source_file: Name of the source document file (used for ChromaDB filtering).
        indicator_codes: Specific codes to extract. ``None`` → all indicators.
        document_id: UUID of the uploaded document.
        n_chunks_processed: Total chunks processed (for MLflow logging).
        document_text: Optional full document text — used as fallback when
            ChromaDB is unreachable or empty.

    Returns:
        List of ``ExtractedMetricCreate`` ready for database persistence.
    """
    indicators = (
        get_all_indicators()
        if indicator_codes is None
        else [get_indicator(code) for code in indicator_codes]
    )

    # Prepare full-doc fallback text (truncated)
    fallback_text: str | None = None
    if document_text:
        fallback_text = document_text[:_MAX_DOCUMENT_CHARS]
        if len(document_text) > _MAX_DOCUMENT_CHARS:
            logger.warning(
                "extractor.truncated",
                original=len(document_text),
                kept=_MAX_DOCUMENT_CHARS,
            )

    # Test ChromaDB reachability once up front
    chromadb_available = False
    if report_id:
        try:
            _get_chroma_client().heartbeat()
            chromadb_available = True
        except Exception as exc:
            logger.warning(
                "extractor.chromadb_unreachable_falling_back_to_full_doc",
                error=str(exc),
            )

    metrics: list[ExtractedMetricCreate] = []
    raw_responses: dict[str, str] = {}
    chunks_retrieved_counts: list[int] = []

    model_name = settings.models.get("extraction", "unknown")

    with start_extraction_run(
        run_name=f"extract-{str(document_id)[:8] if document_id else 'adhoc'}"
    ):
        log_params({
            "document_id": str(document_id) if document_id else "",
            "report_id": str(report_id),
            "company_id": str(company_id),
            "source_file": source_file or "",
            "model_name": model_name,
            "n_chunks_processed": n_chunks_processed if n_chunks_processed is not None else "",
            "n_indicators_attempted": len(indicators),
            "extraction_mode": "retrieval" if chromadb_available else "full_doc_fallback",
            "extraction_top_k": settings.extraction_top_k,
        })

        # ── Per-indicator extraction — sequential ────────────────────────────
        # Sequential dispatch keeps per-indicator timing in the logs accurate
        # and avoids hammering the remote LLM provider; bumping concurrency is
        # a future change (extraction_concurrency is reserved for it).
        logger.info(
            "extractor.batch_start",
            n_indicators=len(indicators),
        )

        for indicator in indicators:
            try:
                indicator_text: str | None = None
                n_retrieved = 0
                prov_source: str | None = None  # winning chunk's source document
                prov_page: int | None = None     # winning chunk's page

                if chromadb_available:
                    try:
                        retrieved = _retrieve_chunks_for_indicator(
                            indicator=indicator,
                            report_id=str(report_id),
                            top_k=settings.extraction_top_k,
                        )
                        n_retrieved = len(retrieved)
                        if n_retrieved >= settings.extraction_min_chunks:
                            indicator_text = _format_retrieved_chunks(retrieved)
                            # Provenance: the top-ranked chunk is the most
                            # relevant evidence — attribute the metric to its
                            # source document + page.
                            top_chunk = retrieved[0]
                            prov_source = top_chunk.get("source_filename")
                            prov_page = safe_int(top_chunk.get("page_number"))
                        else:
                            logger.warning(
                                "extractor.no_chunks_retrieved",
                                gri_code=indicator["code"],
                                retrieved=n_retrieved,
                                min_required=settings.extraction_min_chunks,
                            )
                    except Exception as exc:
                        logger.warning(
                            "extractor.retrieval_failed_for_indicator",
                            gri_code=indicator["code"],
                            error=str(exc),
                        )

                # Fall back to full-doc if no retrieved text
                if indicator_text is None:
                    if fallback_text:
                        indicator_text = fallback_text
                    else:
                        metrics.append(_missing_metric(
                            indicator, company_id, report_id, None,
                            Exception("No chunks retrieved and no fallback text"),
                        ))
                        raw_responses[indicator["code"]] = "<no_chunks>"
                        continue

                metric, raw = await _extract_single(
                    indicator=indicator,
                    document_text=indicator_text,
                    company_id=company_id,
                    report_id=report_id,
                    source_file=None,
                    n_chunks=n_retrieved,
                )
                # Stamp per-metric provenance from the winning evidence chunk —
                # which document + page the value was actually found in.
                if prov_source:
                    metric.source_file = prov_source
                    if prov_page is not None:
                        metric.source_page = prov_page
                metrics.append(metric)
                raw_responses[indicator["code"]] = raw
                if n_retrieved > 0:
                    chunks_retrieved_counts.append(n_retrieved)
                logger.info(
                    "extractor.indicator_ok",
                    code=indicator["code"],
                    status=metric.status.value,
                    confidence=metric.confidence,
                )
            except LLMUnavailableError:
                # Both primary and fallback LLM failed — the whole run is doomed,
                # so propagate to the Celery task handler (which marks the
                # document failed) instead of silently marking every remaining
                # indicator "missing" and "completing" with zero metrics.
                raise
            except Exception as exc:
                logger.error(
                    "extractor.indicator_failed",
                    code=indicator["code"],
                    error=str(exc),
                )
                metrics.append(_missing_metric(indicator, company_id, report_id, source_file, exc))
                raw_responses[indicator["code"]] = f"<error: {exc}>"


        extracted = sum(1 for m in metrics if m.status == MetricStatus.extracted)
        ambiguous = sum(1 for m in metrics if m.status == MetricStatus.ambiguous)
        missing = sum(1 for m in metrics if m.status == MetricStatus.missing)

        confidences = [m.confidence for m in metrics]
        avg_conf = sum(confidences) / len(confidences) if confidences else 0.0
        n_high = sum(1 for c in confidences if c > 0.80)
        n_low = len(confidences) - n_high
        avg_chunks = (
            sum(chunks_retrieved_counts) / len(chunks_retrieved_counts)
            if chunks_retrieved_counts else 0.0
        )

        log_metrics({
            "n_metrics_extracted": float(extracted),
            "n_metrics_ambiguous": float(ambiguous),
            "n_metrics_missing": float(missing),
            "n_metrics_total": float(len(metrics)),
            "avg_confidence": float(avg_conf),
            "n_high_confidence": float(n_high),
            "n_low_confidence": float(n_low),
            "avg_chunks_retrieved_per_indicator": float(avg_chunks),
        })

        for m in metrics:
            log_metric(f"confidence.{sanitize_metric_key(m.gri_code)}", m.confidence)

        log_json_artifact(
            "raw_llm_responses.json",
            {
                "model_name": model_name,
                "document_id": str(document_id) if document_id else None,
                "report_id": str(report_id),
                "extraction_mode": "retrieval" if chromadb_available else "full_doc_fallback",
                "responses": raw_responses,
            },
        )

        logger.info(
            "extractor.complete",
            total=len(metrics),
            extracted=extracted,
            ambiguous=ambiguous,
            missing=missing,
            avg_chunks_per_indicator=round(avg_chunks, 1),
            mode="retrieval" if chromadb_available else "full_doc_fallback",
        )
    return metrics


# ── Single indicator extraction ──────────────────────────────────────────
async def _extract_single(
    indicator: dict,
    document_text: str,
    company_id: UUID,
    report_id: UUID,
    source_file: str | None,
    n_chunks: int = 0,
) -> tuple[ExtractedMetricCreate, str]:
    """Send one indicator prompt to the LLM and parse the response.

    Returns the parsed metric and the raw LLM response text (for tracking).
    """

    # Phase 1.5 stub: inject few-shot corrections here
    # corrections_context = await _fetch_corrections(indicator["code"])
    corrections_context = ""

    user_prompt = build_user_prompt(indicator, document_text, corrections_context)

    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=user_prompt),
    ]

    t0 = time.perf_counter()
    response = await model_router.ainvoke_with_fallback("extraction", messages)
    elapsed = time.perf_counter() - t0

    logger.info(
        "indicator_extracted",
        gri_code=indicator["code"],
        n_chunks_retrieved=n_chunks,
        elapsed_sec=round(elapsed, 1),
    )

    raw_content = response.content if isinstance(response.content, str) else str(response.content)
    parsed = _parse_llm_json(raw_content)

    status = _map_status(parsed.get("status", "missing"))
    confidence = clamp(float(parsed.get("confidence", 0.0)), 0.0, 1.0)

    if status == MetricStatus.extracted and confidence < settings.confidence_threshold:
        status = MetricStatus.ambiguous

    framework = _coerce_framework(indicator.get("framework"))
    raw_metric_type = str(indicator.get("metric_type") or "").strip().lower()
    metric_type = _coerce_metric_type(indicator.get("metric_type"))

    # For monetary metrics, prefer the LLM's structured currency; fall back to
    # parsing the original_value string (handles "EGP 1.2 billion" etc.).
    value = safe_float(parsed.get("value"))
    currency = normalize_currency(parsed.get("currency"))
    if raw_metric_type == "monetary":
        raw_original = parsed.get("original_value")
        parsed_val, parsed_curr = parse_monetary(raw_original) if isinstance(raw_original, str) else (None, None)
        if value is None and parsed_val is not None:
            value = parsed_val
        if currency is None and parsed_curr is not None:
            currency = parsed_curr

    breakdown = parsed.get("breakdown")
    if isinstance(breakdown, str):
        # Some LLMs return a JSON-encoded string instead of a nested object.
        try:
            breakdown = json.loads(breakdown)
        except json.JSONDecodeError:
            breakdown = {"raw": breakdown}
    elif breakdown is not None and not isinstance(breakdown, dict):
        breakdown = {"raw": breakdown}

    reporting_start = _parse_iso_date(parsed.get("reporting_period_start"))
    reporting_end = _parse_iso_date(parsed.get("reporting_period_end"))

    metric = ExtractedMetricCreate(
        company_id=company_id,
        report_id=report_id,
        gri_code=indicator["code"],
        fra_code=indicator.get("fra_code"),
        sasb_code=indicator.get("sasb_code"),
        label=indicator["name"],
        value=value,
        unit=parsed.get("unit"),
        original_value=parsed.get("original_value"),
        original_unit=parsed.get("original_unit"),
        confidence=confidence,
        status=status,
        source_file=source_file,
        source_page=safe_int(parsed.get("source_page")),
        evidence_chunk=parsed.get("evidence"),
        extraction_method=ExtractionMethod.llm,
        note=parsed.get("note"),
        framework=framework,
        metric_type=metric_type,
        sector_standard_ref=indicator.get("sector_standard_ref"),
        currency=currency,
        reporting_period_start=reporting_start,
        reporting_period_end=reporting_end,
        breakdown=breakdown,
        pillar=_coerce_pillar(indicator.get("pillar")),
        topic=_derive_topic(indicator["code"]),
    )
    return metric, raw_content


# ── Response parsing ─────────────────────────────────────────────────────
def _parse_llm_json(raw: str) -> dict:
    """Extract a JSON object from the LLM response, tolerating markdown fences."""
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    fence = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", raw, re.DOTALL)
    if fence:
        try:
            return json.loads(fence.group(1))
        except json.JSONDecodeError:
            pass

    brace = re.search(r"\{.*\}", raw, re.DOTALL)
    if brace:
        try:
            return json.loads(brace.group(0))
        except json.JSONDecodeError:
            pass

    logger.warning("extractor.json_parse_failed", preview=raw[:200])
    return {
        "status": "missing",
        "confidence": 0.0,
        "note": f"LLM response was not valid JSON: {raw[:500]}",
    }


# ── Helpers ──────────────────────────────────────────────────────────────
def _map_status(raw: str) -> MetricStatus:
    mapping = {
        "extracted": MetricStatus.extracted,
        "ambiguous": MetricStatus.ambiguous,
        "missing": MetricStatus.missing,
    }
    return mapping.get(raw.lower().strip(), MetricStatus.missing)


def _missing_metric(
    indicator: dict,
    company_id: UUID,
    report_id: UUID,
    source_file: str | None,
    exc: Exception,
) -> ExtractedMetricCreate:
    """Create a placeholder metric when extraction fails entirely."""
    return ExtractedMetricCreate(
        company_id=company_id,
        report_id=report_id,
        gri_code=indicator["code"],
        fra_code=indicator.get("fra_code"),
        sasb_code=indicator.get("sasb_code"),
        label=indicator["name"],
        confidence=0.0,
        status=MetricStatus.missing,
        extraction_method=ExtractionMethod.llm,
        source_file=source_file,
        note=f"Extraction failed: {exc}",
        framework=_coerce_framework(indicator.get("framework")),
        metric_type=_coerce_metric_type(indicator.get("metric_type")),
        sector_standard_ref=indicator.get("sector_standard_ref"),
        pillar=_coerce_pillar(indicator.get("pillar")),
        topic=_derive_topic(indicator["code"]),
    )


# ── Iteration 2 helpers — coerce string fields from gri_indicators.json ──
def _coerce_framework(raw: object) -> MetricFramework | None:
    if not isinstance(raw, str) or not raw:
        return None
    try:
        return MetricFramework(raw)
    except ValueError:
        logger.warning("extractor.unknown_framework", value=raw)
        return None


# Canonical extraction-shape -> scoring MetricType map. gri_indicators.json
# declares shapes (quantitative/monetary/rate/activity/qualitative); the
# scoring engine's MetricType is the scoring-function selector. monetary/
# rate/activity all score as QUANTITATIVE. Mirrors the identical map in
# core.scoring.gri_scorer / core.scoring.sasb_scorer.
_METRIC_TYPE_MAP: dict[str, MetricType] = {
    "quantitative": MetricType.QUANTITATIVE,
    "monetary":     MetricType.QUANTITATIVE,
    "rate":         MetricType.QUANTITATIVE,
    "activity":     MetricType.QUANTITATIVE,
    "qualitative":  MetricType.QUALITATIVE,
    "binary":       MetricType.BINARY,
    "q_plus_ql":    MetricType.Q_PLUS_QL,
}


def _coerce_metric_type(raw: object) -> MetricType | None:
    """Map a gri_indicators.json metric_type shape to the scoring MetricType.

    monetary/rate/activity are extraction shapes that all score as
    QUANTITATIVE; the scoring MetricType only has BINARY/QUANTITATIVE/
    QUALITATIVE/Q_PLUS_QL. Returns None (with a warning) for unknown shapes.
    """
    if not isinstance(raw, str) or not raw:
        return None
    mt = _METRIC_TYPE_MAP.get(raw.strip().lower())
    if mt is None:
        logger.warning("extractor.unknown_metric_type", value=raw)
    return mt


def _coerce_pillar(raw: object) -> PillarType | None:
    """Coerce a gri_indicators.json pillar string ("E"|"S"|"G") to PillarType."""
    if not isinstance(raw, str) or not raw:
        return None
    try:
        return PillarType(raw.strip().upper())
    except ValueError:
        logger.warning("extractor.unknown_pillar", value=raw)
        return None


def _derive_topic(code: str) -> str | None:
    """Human GRI/FRA topic for a metric, e.g. "GRI 305-1" -> "GRI 305".

    Mirrors core.reporting.builder._topic_of so the review UI and report
    generator group metrics under the same topic label.
    """
    if not isinstance(code, str) or not code:
        return None
    m = re.match(r"(GRI \d+|FRA)", code)
    return m.group(1) if m else None


def _parse_iso_date(raw: object):
    """Parse an ISO YYYY-MM-DD string into a date. Returns None on failure."""
    if not isinstance(raw, str) or not raw:
        return None
    from datetime import date

    try:
        return date.fromisoformat(raw[:10])
    except (ValueError, TypeError):
        return None
