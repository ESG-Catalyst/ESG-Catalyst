"""Narrative generation — LLM drafts factual narrative per report section.

Uses ``ModelRouter("report")`` with credit-error fallback. Output is English only,
references the specific values provided, and explicitly notes anything missing
or ambiguous. If the LLM is unavailable, a deterministic fallback narrative is
produced from the metric data — without leaking raw error details into the
finished report.
"""

from __future__ import annotations

import asyncio

import structlog
from langchain_core.messages import HumanMessage, SystemMessage

from app.core.llm.router import model_router
from app.core.reporting.builder import ReportSection
from app.models.enums import MetricStatus

logger = structlog.get_logger(__name__)


_NARRATIVE_SYSTEM_PROMPT = """\
You are a senior ESG analyst writing a section of a formal sustainability disclosure report \
for an Egyptian financial institution regulated by the Financial Regulatory Authority (FRA).

### Output format — follow exactly
- Write 2 to 4 short paragraphs of plain prose. 200 words maximum.
- Do NOT use markdown: no headers (##), no bullet points (-), no bold (**), no tables.
- Do NOT add a section title or label at the start.
- Output ONLY the narrative paragraphs. Nothing else before or after.

### Content rules — non-negotiable
1. Use ONLY the metric values, units, confidence scores, and evidence text given to you.
   Do NOT invent, estimate, or extrapolate any number or fact that is not in the input.
2. Quote exact figures with their units (e.g. "960 tCO2e", "42 GJ", "15%").
3. If a metric has status "missing" or "ambiguous", state clearly that the data was \
not available or requires clarification — do not skip it silently.
4. If a metric has confidence below 0.70, flag it as requiring reviewer verification.
5. Evidence chunks may contain Arabic text — treat them as factual source material \
and reference what they show (you do not need to quote Arabic directly).
6. Frame the narrative in the context of GRI Standards and FRA ESG disclosure requirements \
relevant to the Egyptian banking sector. Keep the tone professional and factual.
7. Never use filler phrases like "it is important to note", "in conclusion", \
"the company is committed to", or generic ESG boilerplate.
"""


async def generate_narratives(sections: list[ReportSection]) -> list[ReportSection]:
    """Draft LLM narratives for each section in parallel.

    Args:
        sections: Output of ``build_report_sections()``.

    Returns:
        Same sections with ``narrative`` field populated. On LLM failure, the
        fallback narrative is used and the error is logged (not embedded in
        the report).
    """
    if not sections:
        return sections

    tasks = [_narrate_section(s) for s in sections]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    for section, result in zip(sections, results):
        if isinstance(result, Exception):
            logger.error(
                "narrative.section_failed",
                topic=section.gri_topic,
                error=str(result)[:300],
            )
            section.narrative = _fallback_narrative(section)
        else:
            section.narrative = result

    logger.info("narrative.done", sections=len(sections))
    return sections


async def _narrate_section(section: ReportSection) -> str:
    """Generate a single section narrative via the LLM (with credit fallback)."""
    messages = [
        SystemMessage(content=_NARRATIVE_SYSTEM_PROMPT),
        HumanMessage(content=_build_user_prompt(section)),
    ]
    response = await model_router.ainvoke_with_fallback("report", messages)
    return response.content.strip()


def _build_user_prompt(section: ReportSection) -> str:
    lines = [
        f"Section: {section.title}",
        f"ESG Pillar: {section.pillar}",
        "",
        "Metrics in this section:",
    ]
    for m in section.metrics:
        status = _status_str(m.status)
        value_str = _format_value(m)
        evidence = (getattr(m, "evidence_chunk", None) or "").strip()[:200]
        lines.append(
            f"  - {m.gri_code} ({m.label}): {value_str} "
            f"[status={status}, confidence={m.confidence:.2f}]"
        )
        if evidence:
            lines.append(f'      Evidence: "{evidence}"')
    lines.append("")
    lines.append("Draft the narrative for this section.")
    return "\n".join(lines)


def _format_value(metric) -> str:
    """Best human-readable rendering of a metric's value, falling back through
    normalized → original → none-disclosed."""
    if metric.value is not None and metric.unit:
        return f"{metric.value} {metric.unit}"
    if metric.value is not None:
        return f"{metric.value}"
    if metric.original_value:
        unit = metric.original_unit or ""
        return f"{metric.original_value} {unit}".strip()
    return "(no value)"


def _status_str(status) -> str:
    return status.value if hasattr(status, "value") else str(status)


def _is_disclosed(metric) -> bool:
    """A metric is 'disclosed' if a value (normalized or original) is present
    and the status is not explicitly missing/rejected."""
    status = metric.status
    if status in (MetricStatus.missing, MetricStatus.rejected):
        return False
    return metric.value is not None or bool(metric.original_value)


def _fallback_narrative(section: ReportSection) -> str:
    """Deterministic narrative used when the LLM call fails.

    Produces clean factual prose; never embeds error details — those are
    logged separately so the published report stays presentable.
    """
    if not section.metrics:
        return (
            f"No metrics were reported for {section.title}. "
            "This represents a gap in the disclosure scope and should be "
            "addressed in the next reporting cycle."
        )

    disclosed: list[str] = []
    ambiguous: list[str] = []
    missing: list[str] = []

    for m in section.metrics:
        status = m.status
        value_str = _format_value(m)
        if status == MetricStatus.ambiguous:
            ambiguous.append(f"{m.label} ({m.gri_code})")
        elif _is_disclosed(m):
            disclosed.append(
                f"{m.label} ({m.gri_code}) is reported as {value_str} "
                f"with {m.confidence:.0%} confidence"
            )
        else:
            missing.append(f"{m.label} ({m.gri_code})")

    paragraphs: list[str] = [
        f"This section covers {len(section.metrics)} indicator(s) "
        f"under {section.title}."
    ]

    if disclosed:
        paragraphs.append(". ".join(disclosed) + ".")
    if ambiguous:
        paragraphs.append(
            "The following indicator(s) were identified but the reported "
            "value is ambiguous and requires reviewer attention: "
            + ", ".join(ambiguous) + "."
        )
    if missing:
        paragraphs.append(
            "The following indicator(s) are not currently disclosed and "
            "represent gaps for future reporting: "
            + ", ".join(missing) + "."
        )

    return " ".join(paragraphs)