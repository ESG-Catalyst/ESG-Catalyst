"""ESG metric extraction — LLM calls per GRI indicator via ModelRouter.

For each indicator in scope, builds a prompt from ``gri_indicators.json``,
sends it through ``ModelRouter.get_model("extraction")``, and parses the
structured JSON response into ``ExtractedMetricCreate`` objects.

Phase 1.5 hooks (corrections_store few-shot injection) are stubbed but
clearly marked so they can be wired once the correction loop is live.

Usage:
    from app.core.pipeline.extractor import extract_metrics

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
from app.core.gri.indicators import get_all_indicators, get_indicator
from app.core.models.router import model_router
from app.models.enums import ExtractionMethod, MetricStatus
from app.schemas.metric import ExtractedMetricCreate

logger = structlog.get_logger(__name__)

# ── Truncation guard — keep document text within LLM context limits ──────
_MAX_DOCUMENT_CHARS = 60_000  # ~15k tokens; leaves room for prompt + response

# ── System prompt ────────────────────────────────────────────────────────
_SYSTEM_PROMPT = """\
You are an expert ESG data extraction specialist. Your task is to extract \
specific ESG metrics from company documents.

Rules:
1. Extract ONLY what is explicitly stated in the document. Never infer or \
calculate values unless the document provides the components and the \
indicator requires calculation.
2. Preserve original values and units exactly as found in the document.
3. Also provide normalized values when unit conversion is needed.
4. For Arabic documents, translate extracted labels to English but preserve \
original Arabic values in the original_value field.
5. Rate your confidence from 0.0 to 1.0:
   - 1.0: Value is explicitly and clearly stated
   - 0.8-0.9: Value is clearly stated but requires minor interpretation
   - 0.5-0.7: Value requires significant interpretation or is partially stated
   - 0.1-0.4: Value is ambiguous or uncertain
   - 0.0: Value is not found in the document
6. If you cannot find the metric, return status "missing" with confidence 0.0.

Respond ONLY with valid JSON matching this exact schema:
{
  "value": <float or null>,
  "unit": "<normalized unit or null>",
  "original_value": "<value exactly as in document or null>",
  "original_unit": "<unit exactly as in document or null>",
  "confidence": <float 0.0-1.0>,
  "status": "<extracted|ambiguous|missing>",
  "evidence": "<exact text passage that contains the value>",
  "source_page": <int or null>,
  "note": "<any additional context, sub-values, or calculation details>"
}
"""


# ── Public API ───────────────────────────────────────────────────────────
async def extract_metrics(
    document_text: str,
    company_id: UUID,
    report_id: UUID,
    source_file: str | None = None,
    indicator_codes: list[str] | None = None,
) -> list[ExtractedMetricCreate]:
    """Extract ESG metrics from document text for specified GRI indicators.

    Args:
        document_text: Full text content of the document.
        company_id: UUID of the company being evaluated.
        report_id: UUID of the report being generated.
        source_file: Name of the source document file.
        indicator_codes: Specific codes to extract. ``None`` → all 13.

    Returns:
        List of ``ExtractedMetricCreate`` ready for database persistence.
    """
    indicators = (
        get_all_indicators()
        if indicator_codes is None
        else [get_indicator(code) for code in indicator_codes]
    )

    # Truncate very long documents to stay within context limits
    doc_text = document_text[:_MAX_DOCUMENT_CHARS]
    if len(document_text) > _MAX_DOCUMENT_CHARS:
        logger.warning(
            "extractor.truncated",
            original=len(document_text),
            kept=_MAX_DOCUMENT_CHARS,
        )

    llm = model_router.get_model("extraction")
    metrics: list[ExtractedMetricCreate] = []

    for indicator in indicators:
        try:
            metric = await _extract_single(
                llm=llm,
                indicator=indicator,
                document_text=doc_text,
                company_id=company_id,
                report_id=report_id,
                source_file=source_file,
            )
            metrics.append(metric)
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

    extracted = sum(1 for m in metrics if m.status == MetricStatus.extracted)
    ambiguous = sum(1 for m in metrics if m.status == MetricStatus.ambiguous)
    missing = sum(1 for m in metrics if m.status == MetricStatus.missing)
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
    llm,
    indicator: dict,
    document_text: str,
    company_id: UUID,
    report_id: UUID,
    source_file: str | None,
) -> ExtractedMetricCreate:
    """Send one indicator prompt to the LLM and parse the response."""

    # ── Phase 1.5 stub: inject few-shot corrections here ─────────────
    # corrections_context = await _fetch_corrections(indicator["code"])
    corrections_context = ""

    user_prompt = (
        f"Extract the following ESG indicator from the document below.\n\n"
        f"Indicator: {indicator['code']} — {indicator['name']}\n"
        f"Expected unit: {indicator.get('expected_unit') or 'N/A'}\n\n"
        f"Extraction instructions:\n{indicator['extraction_prompt']}\n"
    )

    if corrections_context:
        user_prompt += f"\nPast corrections for reference:\n{corrections_context}\n"

    user_prompt += (
        f"\n--- DOCUMENT TEXT ---\n"
        f"{document_text}\n"
        f"--- END DOCUMENT ---\n\n"
        f"Respond with JSON only."
    )

    messages = [
        SystemMessage(content=_SYSTEM_PROMPT),
        HumanMessage(content=user_prompt),
    ]

    response = await llm.ainvoke(messages)
    parsed = _parse_llm_json(response.content)

    # Map status string → enum
    status = _map_status(parsed.get("status", "missing"))
    confidence = _clamp(float(parsed.get("confidence", 0.0)), 0.0, 1.0)

    # Downgrade low-confidence extractions to ambiguous
    if status == MetricStatus.extracted and confidence < settings.confidence_threshold:
        status = MetricStatus.ambiguous

    return ExtractedMetricCreate(
        company_id=company_id,
        report_id=report_id,
        gri_code=indicator["code"],
        fra_code=indicator.get("fra_code"),
        sasb_code=indicator.get("sasb_code"),
        label=indicator["name"],
        value=_safe_float(parsed.get("value")),
        unit=parsed.get("unit"),
        original_value=parsed.get("original_value"),
        original_unit=parsed.get("original_unit"),
        confidence=confidence,
        status=status,
        source_file=source_file,
        source_page=_safe_int(parsed.get("source_page")),
        evidence_chunk=parsed.get("evidence"),
        extraction_method=ExtractionMethod.llm,
        note=parsed.get("note"),
    )


# ── Response parsing ─────────────────────────────────────────────────────
def _parse_llm_json(raw: str) -> dict:
    """Extract a JSON object from the LLM response, tolerating markdown fences."""
    # 1. Direct parse
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # 2. Strip markdown code fences
    fence = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", raw, re.DOTALL)
    if fence:
        try:
            return json.loads(fence.group(1))
        except json.JSONDecodeError:
            pass

    # 3. Find the first { … } block
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
    )


def _safe_float(val) -> float | None:  # noqa: ANN001
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _safe_int(val) -> int | None:  # noqa: ANN001
    if val is None:
        return None
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))
