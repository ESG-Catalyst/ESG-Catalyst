"""Extraction prompt templates for ESG metric extraction.

All LLM prompts for metric extraction live here.  Extractor.py calls
``build_user_prompt()`` for each indicator.
"""

from __future__ import annotations

SYSTEM_PROMPT = """\
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


def build_user_prompt(
    indicator: dict,
    document_text: str,
    corrections_context: str = "",
) -> str:
    """Build the user-turn prompt for a single GRI indicator extraction.

    Args:
        indicator: Indicator dict from ``gri_indicators.json``.
        document_text: The (possibly truncated) document text.
        corrections_context: Optional few-shot corrections from the corrections store.

    Returns:
        Formatted user prompt string.
    """
    prompt = (
        f"Extract the following ESG indicator from the document below.\n\n"
        f"Indicator: {indicator['code']} — {indicator['name']}\n"
        f"Expected unit: {indicator.get('expected_unit') or 'N/A'}\n\n"
        f"Extraction instructions:\n{indicator['extraction_prompt']}\n"
    )

    if corrections_context:
        prompt += f"\nPast corrections for reference:\n{corrections_context}\n"

    prompt += (
        f"\n--- DOCUMENT TEXT ---\n"
        f"{document_text}\n"
        f"--- END DOCUMENT ---\n\n"
        f"Respond with JSON only."
    )

    return prompt
