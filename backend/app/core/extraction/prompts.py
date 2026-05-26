"""Extraction prompt templates for ESG metric extraction.

All LLM prompts for metric extraction live here. ``extractor.py`` calls
``build_user_prompt()`` for each indicator. Each indicator declares its
``framework`` (GRI / SASB-FN-CF / SASB-FN-MF / SASB-FN-IN / FRA) and
``metric_type`` (quantitative / monetary / rate / qualitative / activity)
in ``data/gri_indicators.json``; this module emits a slightly different
JSON schema and field-level guidance for each combination.

Note (Iteration 2): ``document_text`` is now the focused, per-indicator
retrieved chunks from ChromaDB (typically 3-5 chunks, ~1-3 KB), not the
full 60 KB document blob.  The prompt structure is unchanged — the LLM
just receives less noise and more signal.
"""

from __future__ import annotations

SYSTEM_PROMPT = """\
You are an expert ESG data extraction specialist. Your task is to extract \
specific ESG metrics from company documents.

Rules:
1. Extract ONLY what is explicitly stated in the document. Never infer or \
calculate values unless the document provides the components and the \
indicator instructions ask for a calculation.
2. Preserve original values and units exactly as found in the document. \
Also provide normalized values where the indicator specifies a target unit.
3. For Arabic documents, translate extracted labels to English but preserve \
original Arabic values in the original_value field. Convert Arabic-Indic \
digits (٠١٢٣٤٥٦٧٨٩) to Western digits.
4. Rate your confidence from 0.0 to 1.0:
   - 1.0: Value is explicitly and clearly stated
   - 0.8-0.9: Value is clearly stated but requires minor interpretation
   - 0.5-0.7: Value requires significant interpretation or is partially stated
   - 0.1-0.4: Value is ambiguous or uncertain
   - 0.0: Value is not found
5. If you cannot find the metric, return status "missing" with confidence 0.0.
6. Return zero EXPLICITLY (value=0, status=extracted) when the document \
clearly states zero incidents / zero losses / zero contributions — these \
are valid data points, not missing data.

Respond ONLY with valid JSON matching this schema (use null for unused \
fields — never omit a key):
{
  "value": <float or null>,
  "unit": "<normalized unit or null>",
  "original_value": "<value exactly as in document or null>",
  "original_unit": "<unit exactly as in document or null>",
  "currency": "<ISO-4217 code (USD, EGP, EUR, ...) or null — required for monetary metrics>",
  "breakdown": <object or null — sub-values keyed as instructed per indicator>,
  "confidence": <float 0.0-1.0>,
  "status": "<extracted|ambiguous|missing>",
  "evidence": "<exact text passage that contains the value>",
  "source_page": <int or null>,
  "reporting_period_start": "<YYYY-MM-DD or null>",
  "reporting_period_end": "<YYYY-MM-DD or null>",
  "note": "<calculation details, methodology, data gaps, etc.>"
}
"""


# Per-metric-type guidance appended to the user prompt. Keeps SYSTEM_PROMPT
# stable while tuning the LLM's emphasis indicator by indicator.
_METRIC_TYPE_GUIDANCE: dict[str, str] = {
    "quantitative": (
        "This is a QUANTITATIVE metric. Set `value` to a single float (the headline number). "
        "Set `unit` to the normalized unit named under 'Expected unit'. "
        "Leave `currency` as null."
    ),
    "monetary": (
        "This is a MONETARY metric. Set `value` to the numeric amount (a float). "
        "Set `currency` to the ISO-4217 code found in the document (USD, EGP, EUR, GBP, ...). "
        "Set `unit` to null (the currency field replaces it). "
        "If the document writes 'EGP 1.2 billion', set value=1.2e9 and currency='EGP'. "
        "If the document writes 'USD 540 million', set value=5.4e8 and currency='USD'. "
        "Preserve the raw spelling in original_value and original_unit (e.g., '1.2 billion', 'EGP million')."
    ),
    "rate": (
        "This is a RATE/RATIO metric. Set `value` to the ratio itself (e.g., 12.5 for '12.5 per 1,000' or 65.0 for '65%'). "
        "Set `unit` to the rate basis ('percent', 'per_1000_claims', 'per_million_hours_worked', 'GJ_per_million_EGP', etc.). "
        "Put numerator and denominator components in `breakdown` so reviewers can recompute."
    ),
    "qualitative": (
        "This is a QUALITATIVE disclosure (SASB 'Discussion and Analysis'). Leave `value` and `unit` as null. "
        "Write a 2-4 sentence factual summary of the disclosure in the `evidence` field. "
        "Do NOT invent or extrapolate — if the document only addresses the topic briefly, reflect that brevity. "
        "Use `note` for any standards-required sub-points (policies, governance, jurisdictional context) that the document does or does not address."
    ),
    "activity": (
        "This is an ACTIVITY metric (SASB scale indicator: # accounts, # policies, # mortgages, etc.). "
        "Set `value` to the headline total count. Set `unit` to 'count'. "
        "Put the segment / product-line split in `breakdown` exactly as the document presents it."
    ),
}


# Per-framework guidance — what to emphasize given the source standard.
_FRAMEWORK_GUIDANCE: dict[str, str] = {
    "GRI": (
        "Source standard: GRI (Global Reporting Initiative). "
        "Look for explicit GRI Content Index references (e.g., 'GRI 305-1') near the data. "
        "Many GRI disclosures require sector-specific breakdowns — fill `breakdown` per the indicator instructions."
    ),
    "SASB-FN-CF": (
        "Source standard: SASB Consumer Finance (FN-CF, IFRS Foundation, v2023-12). "
        "Disclosure may appear in a SASB Content Index, an ESG report appendix, or a 10-K/annual-report sustainability section. "
        "Activity metrics (FN-CF-000.A/B) quantify customer base scale; accounting metrics describe specific risk exposures. "
        "Monetary losses metrics scope IN civil judgements, regulatory penalties, and criminal actions but EXCLUDE the entity's own defence fees."
    ),
    "SASB-FN-MF": (
        "Source standard: SASB Mortgage Finance (FN-MF, IFRS Foundation, v2023-12). "
        "Mortgage portfolio is reported in the entity's PRESENTATION CURRENCY — capture it. "
        "Loan-to-value (LTV) ratios are weighted-average; preserve the document's jurisdictional LTV calculation basis. "
        "100-year flood zone = ≥1% annual flood probability."
    ),
    "SASB-FN-IN": (
        "Source standard: SASB Insurance (FN-IN, IFRS Foundation, v2025-12 — aligned with IFRS S2 amendments Dec 2025). "
        "Financed emissions (FN-IN-410c.*) cover the insurer's INVESTMENT portfolio, not its own operations. "
        "Catastrophe-loss metrics distinguish modelled vs non-modelled events, and net vs gross of reinsurance."
    ),
    "SASB-FN-CB": (
        "Source standard: SASB Commercial Banks (FN-CB). "
        "Cross-references the GRI 418-1 customer-privacy disclosure (sector ref FN-CB-230a.1)."
    ),
    "FRA": (
        "Source standard: Financial Regulatory Authority of Egypt (FRA) ESG reporting circular. "
        "Egyptian banks typically combine Scope 1 + 2 into a single FRA-36 line. "
        "If the document only reports individual scopes, sum them and set status to ambiguous unless the document also states the combined total."
    ),
}


def build_user_prompt(
    indicator: dict,
    document_text: str,
    corrections_context: str = "",
) -> str:
    """Build the user-turn prompt for a single indicator extraction.

    Args:
        indicator: Indicator dict from ``gri_indicators.json``. Must contain
            ``code``, ``name``, ``extraction_prompt``. May contain ``framework``,
            ``metric_type``, ``sector_standard_ref``, ``expected_unit``,
            ``expected_breakdown`` (Iteration 2 fields).
        document_text: The (possibly truncated) document text.
        corrections_context: Optional few-shot corrections from the corrections store.

    Returns:
        Formatted user prompt string.
    """
    framework = indicator.get("framework", "GRI")
    metric_type = indicator.get("metric_type", "quantitative")
    ref = indicator.get("sector_standard_ref")
    expected_breakdown = indicator.get("expected_breakdown") or []

    header = (
        f"Extract the following ESG indicator from the document below.\n\n"
        f"Indicator: {indicator['code']} — {indicator['name']}\n"
        f"Framework: {framework}"
    )
    if ref:
        header += f" (sector ref {ref})"
    header += (
        f"\nMetric type: {metric_type}\n"
        f"Expected unit: {indicator.get('expected_unit') or 'N/A'}\n"
    )
    if expected_breakdown:
        header += f"Expected breakdown keys: {', '.join(expected_breakdown)}\n"

    framework_guidance = _FRAMEWORK_GUIDANCE.get(framework, "")
    metric_type_guidance = _METRIC_TYPE_GUIDANCE.get(metric_type, _METRIC_TYPE_GUIDANCE["quantitative"])

    prompt = header + "\n"
    if framework_guidance:
        prompt += f"{framework_guidance}\n\n"
    prompt += f"{metric_type_guidance}\n\n"
    prompt += f"Extraction instructions:\n{indicator['extraction_prompt']}\n"

    if corrections_context:
        prompt += f"\nPast corrections for reference:\n{corrections_context}\n"

    prompt += (
        f"\n--- DOCUMENT TEXT ---\n"
        f"{document_text}\n"
        f"--- END DOCUMENT ---\n\n"
        f"Respond with JSON only."
    )

    return prompt