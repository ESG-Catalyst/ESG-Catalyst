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


_ROADMAP_SYSTEM_PROMPT = """\
You are a senior ESG advisor (SASB-FSA credentialed) building a practical, prioritized \
improvement roadmap for an Egyptian financial institution's ESG disclosure, aligned with \
GRI Standards, SASB, and the Financial Regulatory Authority (FRA) of Egypt.

You are given two inputs:
A) GAPS — material indicators that are NOT yet disclosed (or are ambiguous).
B) DISCLOSED — indicators already reported, with their value, confidence, and whether \
they carry a unit / page citation / evidence.

### Write the roadmap as follows
- Open with one short framing sentence naming the company, its sector, and its current \
overall score and tier.
- Then "Priority actions to close gaps:" — a numbered list. For each high/medium-priority \
gap give: (a) the specific data to collect, (b) the concrete internal source/owner to get \
it from (utility bills, HR system, compliance/AML logs, loan-book/treasury, board secretariat, \
etc.), and (c) the framework it satisfies. Be specific to a bank's operations, not generic.
- Then "Strengthen existing disclosures:" — for disclosed metrics that are weak (low \
confidence, missing unit, or no citation), say exactly what would raise their quality \
(add the measurement unit, cite the source page, obtain third-party assurance, add the \
sector breakdown the standard requires).
- Close with one sentence on the single highest-leverage move to lift the score next cycle.

### Rules
- Plain prose + numbered lists only. No markdown headers (##), no bold (**), no tables.
- Be concrete and actionable; reference the actual indicator codes and the company's sector.
- Do NOT invent values. Do NOT use ESG boilerplate ("committed to sustainability", etc.).
- Keep it under 350 words.
"""


async def generate_roadmap(bundle) -> str:
    """Generate a company-specific ESG improvement roadmap for the report.

    Covers both undisclosed material indicators (how to start reporting them)
    and already-disclosed but weak metrics (how to raise their quality). Uses
    the ``report`` model with credit fallback; on failure returns a clean
    deterministic roadmap built from the gap recommendations.

    Args:
        bundle: ``ReportBundle`` with ``company``, ``score`` (incl. ``gaps``),
            and ``sections``.

    Returns:
        Roadmap prose string (English).
    """
    try:
        messages = [
            SystemMessage(content=_ROADMAP_SYSTEM_PROMPT),
            HumanMessage(content=_build_roadmap_prompt(bundle)),
        ]
        response = await model_router.ainvoke_with_fallback("report", messages)
        text = response.content.strip()
        if text:
            return text
    except Exception as exc:  # noqa: BLE001 — report must still render
        logger.error("roadmap.failed", error=str(exc)[:300])
    return _fallback_roadmap(bundle)


def _build_roadmap_prompt(bundle) -> str:
    company = bundle.company
    score = bundle.score
    lines = [
        f"Company: {company.name}",
        f"Sector: {company.sector}",
        f"Overall score: {score.total_score} / 100 (tier: {score.benchmark_tier}); "
        f"E={score.environmental_score} S={score.social_score} G={score.governance_score}.",
        "",
        "A) GAPS (material indicators not yet disclosed / ambiguous):",
    ]
    gaps = list(getattr(score, "gaps", []) or [])
    if gaps:
        for g in gaps:
            lines.append(
                f"  - [{g.priority}] {g.code} ({g.name}) — status={g.status}; "
                f"why it matters: {getattr(g, 'why_it_matters', '')}"
            )
    else:
        lines.append("  (none — all in-scope indicators disclosed)")

    lines.append("")
    lines.append("B) DISCLOSED indicators (raise quality where weak):")
    for s in bundle.sections:
        for m in s.metrics:
            if not _is_disclosed(m):
                continue
            quality_flags = []
            if m.confidence < 0.70:
                quality_flags.append("low confidence")
            if m.value is not None and not m.unit:
                quality_flags.append("no unit")
            if not getattr(m, "source_page", None):
                quality_flags.append("no page citation")
            flag = f" [{', '.join(quality_flags)}]" if quality_flags else ""
            lines.append(
                f"  - {m.gri_code} ({m.label}): {_format_value(m)} "
                f"[confidence={m.confidence:.2f}]{flag}"
            )
    lines.append("")
    lines.append("Write the improvement roadmap.")
    return "\n".join(lines)


def _fallback_roadmap(bundle) -> str:
    """Deterministic roadmap when the LLM is unavailable."""
    score = bundle.score
    gaps = list(getattr(score, "gaps", []) or [])
    parts = [
        f"{bundle.company.name} currently scores {score.total_score}/100 "
        f"({score.benchmark_tier}). Priority actions to close gaps:"
    ]
    if gaps:
        ordered = sorted(
            gaps,
            key=lambda g: {"high": 0, "medium": 1, "low": 2}.get(g.priority, 3),
        )
        for i, g in enumerate(ordered, 1):
            parts.append(
                f"{i}. {g.code} ({g.name}) — {getattr(g, 'recommendation', '')}".strip()
            )
    else:
        parts.append("All in-scope indicators are disclosed; focus on assurance and trend reporting.")
    parts.append(
        "Strengthen existing disclosures by adding measurement units, citing the "
        "source page for each figure, and obtaining third-party assurance where feasible."
    )
    return "\n".join(parts)


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


def _format_value(metric: object) -> str:
    """Best human-readable rendering of a metric's value.

    Falls back through: normalized → original → ``"(no value)"``.

    Args:
        metric: An extracted-metric object exposing ``value``, ``unit``,
                ``original_value``, and ``original_unit``.

    Returns:
        Human-readable value string.
    """
    if metric.value is not None and metric.unit:  # type: ignore[attr-defined]
        return f"{metric.value} {metric.unit}"  # type: ignore[attr-defined]
    if metric.value is not None:  # type: ignore[attr-defined]
        return f"{metric.value}"  # type: ignore[attr-defined]
    if metric.original_value:  # type: ignore[attr-defined]
        unit = metric.original_unit or ""  # type: ignore[attr-defined]
        return f"{metric.original_value} {unit}".strip()  # type: ignore[attr-defined]
    return "(no value)"


def _status_str(status: object) -> str:
    """Return the string value of a MetricStatus enum or a plain string."""
    return status.value if hasattr(status, "value") else str(status)  # type: ignore[attr-defined]


def _is_disclosed(metric: object) -> bool:
    """Return True if a metric has a disclosed value and is not rejected/missing.

    Args:
        metric: Extracted-metric object with ``status``, ``value``, and
                ``original_value`` attributes.

    Returns:
        True when the metric has a numeric or original value and is not
        explicitly in a missing or rejected state.
    """
    status = metric.status  # type: ignore[attr-defined]
    if status in (MetricStatus.missing, MetricStatus.rejected):
        return False
    return metric.value is not None or bool(metric.original_value)  # type: ignore[attr-defined]


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