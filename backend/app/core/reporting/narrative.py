"""Narrative generation — LLM drafts factual narrative per report section.

Uses ``ModelRouter("report")`` for all LLM calls.
Output is English only, references specific values, notes what is missing.
"""

from __future__ import annotations

import asyncio

import structlog
from langchain_core.messages import HumanMessage, SystemMessage

from app.core.llm.router import model_router
from app.core.reporting.builder import ReportSection

logger = structlog.get_logger(__name__)


_NARRATIVE_SYSTEM_PROMPT = """\
You are a senior ESG report writer drafting a section of a sustainability report.

Rules:
1. Write in clear, factual, professional English. Do NOT invent values.
2. Reference the specific numbers and units provided in the data.
3. If a metric is missing, ambiguous, or low-confidence, state that explicitly.
4. Aim for 2–4 short paragraphs (150–250 words total).
5. Do not include section headings — only the body prose.
6. Never speculate beyond the data provided.
"""


async def generate_narratives(sections: list[ReportSection]) -> list[ReportSection]:
    """Draft LLM narratives for each section in parallel.

    Args:
        sections: Output of ``build_report_sections()``.

    Returns:
        Same sections with ``narrative`` field populated.
    """
    if not sections:
        return sections

    llm = model_router.get_model("report")
    tasks = [_narrate_section(llm, s) for s in sections]
    narratives = await asyncio.gather(*tasks, return_exceptions=True)

    for section, narrative in zip(sections, narratives):
        if isinstance(narrative, Exception):
            logger.error("narrative.section_failed", topic=section.gri_topic, error=str(narrative))
            section.narrative = _fallback_narrative(section, error=str(narrative))
        else:
            section.narrative = narrative

    logger.info("narrative.done", sections=len(sections))
    return sections


async def _narrate_section(llm, section: ReportSection) -> str:
    """Generate a single section narrative via the LLM."""
    messages = [
        SystemMessage(content=_NARRATIVE_SYSTEM_PROMPT),
        HumanMessage(content=_build_user_prompt(section)),
    ]
    response = await llm.ainvoke(messages)
    return response.content.strip()


def _build_user_prompt(section: ReportSection) -> str:
    lines = [
        f"Section: {section.title}",
        f"ESG Pillar: {section.pillar}",
        "",
        "Metrics in this section:",
    ]
    for m in section.metrics:
        status = m.status.value if hasattr(m.status, "value") else str(m.status)
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
    if metric.value is not None and metric.unit:
        return f"{metric.value} {metric.unit}"
    if metric.original_value:
        unit = metric.original_unit or ""
        return f"{metric.original_value} {unit}".strip()
    return "(no value)"


def _fallback_narrative(section: ReportSection, error: str) -> str:
    """Deterministic narrative used when the LLM call fails."""
    if not section.metrics:
        return (
            f"No metrics were reported for {section.title}. "
            "This represents a gap in the disclosure scope."
        )

    lines = [f"This section covers {len(section.metrics)} indicator(s) under {section.title}."]
    for m in section.metrics:
        status = m.status.value if hasattr(m.status, "value") else str(m.status)
        value_str = _format_value(m)
        if status in ("extracted", "approved") and m.value is not None:
            lines.append(
                f"{m.label} ({m.gri_code}) was reported as {value_str} "
                f"with confidence {m.confidence:.0%}."
            )
        elif status == "ambiguous":
            lines.append(
                f"{m.label} ({m.gri_code}) was identified but the value is ambiguous "
                "and requires reviewer attention."
            )
        else:
            lines.append(f"{m.label} ({m.gri_code}) is not currently disclosed.")

    lines.append(f"(Note: narrative generated without LLM due to: {error[:120]})")
    return " ".join(lines)
