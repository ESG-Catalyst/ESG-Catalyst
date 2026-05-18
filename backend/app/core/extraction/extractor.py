"""ESG metric extraction — LLM calls per GRI indicator via ModelRouter.

For each indicator in scope, builds a prompt from ``gri_indicators.json``,
sends it through ``ModelRouter.get_model("extraction")``, and parses the
structured JSON response into ``ExtractedMetricCreate`` objects.

Usage:
    from app.core.extraction.extractor import extract_metrics

    metrics = await extract_metrics(
        document_text="...",
        company_id=company_uuid,
        report_id=report_uuid,
    )
"""

from __future__ import annotations

import json
import re
from uuid import UUID

import structlog
from langchain_core.messages import HumanMessage, SystemMessage

from app.config import settings
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

# Truncation guard — keep document text within LLM context limits (~15k tokens)
_MAX_DOCUMENT_CHARS = 60_000


# ── Public API ───────────────────────────────────────────────────────────
async def extract_metrics(
    document_text: str,
    company_id: UUID,
    report_id: UUID,
    source_file: str | None = None,
    indicator_codes: list[str] | None = None,
    document_id: UUID | None = None,
    n_chunks_processed: int | None = None,
) -> list[ExtractedMetricCreate]:
    """Extract ESG metrics from document text for specified GRI indicators.

    Args:
        document_text: Full text content of the document.
        company_id: UUID of the company being evaluated.
        report_id: UUID of the report being generated.
        source_file: Name of the source document file.
        indicator_codes: Specific codes to extract. ``None`` → all indicators.

    Returns:
        List of ``ExtractedMetricCreate`` ready for database persistence.
    """
    indicators = (
        get_all_indicators()
        if indicator_codes is None
        else [get_indicator(code) for code in indicator_codes]
    )

    doc_text = document_text[:_MAX_DOCUMENT_CHARS]
    if len(document_text) > _MAX_DOCUMENT_CHARS:
        logger.warning(
            "extractor.truncated",
            original=len(document_text),
            kept=_MAX_DOCUMENT_CHARS,
        )

    metrics: list[ExtractedMetricCreate] = []
    raw_responses: dict[str, str] = {}

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
            "document_chars": len(document_text),
            "document_chars_kept": len(doc_text),
        })

        for indicator in indicators:
            try:
                metric, raw = await _extract_single(
                    indicator=indicator,
                    document_text=doc_text,
                    company_id=company_id,
                    report_id=report_id,
                    source_file=source_file,
                )
                metrics.append(metric)
                raw_responses[indicator["code"]] = raw
                logger.info(
                    "extractor.indicator_ok",
                    code=indicator["code"],
                    status=metric.status.value,
                    confidence=metric.confidence,
                )
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

        log_metrics({
            "n_metrics_extracted": float(extracted),
            "n_metrics_ambiguous": float(ambiguous),
            "n_metrics_missing": float(missing),
            "n_metrics_total": float(len(metrics)),
            "avg_confidence": float(avg_conf),
            "n_high_confidence": float(n_high),
            "n_low_confidence": float(n_low),
        })

        for m in metrics:
            log_metric(f"confidence.{sanitize_metric_key(m.gri_code)}", m.confidence)

        log_json_artifact(
            "raw_llm_responses.json",
            {
                "model_name": model_name,
                "document_id": str(document_id) if document_id else None,
                "report_id": str(report_id),
                "responses": raw_responses,
            },
        )

        logger.info(
            "extractor.complete",
            total=len(metrics),
            extracted=extracted,
            ambiguous=ambiguous,
            missing=missing,
        )
    return metrics


# ── Single indicator extraction ──────────────────────────────────────────
async def _extract_single(
    indicator: dict,
    document_text: str,
    company_id: UUID,
    report_id: UUID,
    source_file: str | None,
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

    response = await model_router.ainvoke_with_fallback("extraction", messages)
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
