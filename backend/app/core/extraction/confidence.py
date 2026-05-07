"""Confidence scoring logic for extracted ESG metrics.

Confidence starts at 1.0 and is reduced for factors that introduce uncertainty.
Threshold < 0.80 → flag for human review (CONFIDENCE_THRESHOLD in .env).
"""

from __future__ import annotations


def adjust_confidence(
    base_confidence: float,
    *,
    is_ocr: bool = False,
    is_approximate: bool = False,
    unit_ambiguous: bool = False,
    single_source: bool = False,
    indirect_language: bool = False,
) -> float:
    """Apply penalty factors to a base confidence score.

    Args:
        base_confidence: Initial confidence from LLM (0.0–1.0).
        is_ocr: Text came from OCR; character errors possible.
        is_approximate: Value uses approximate language ("approximately", "circa", "~").
        unit_ambiguous: Unit is unclear or could be interpreted multiple ways.
        single_source: Only one text passage supports the value.
        indirect_language: Value implied rather than explicitly stated.

    Returns:
        Adjusted confidence clamped to [0.0, 1.0].
    """
    score = base_confidence

    if indirect_language:
        score *= 0.7
    if is_approximate:
        score *= 0.85
    if unit_ambiguous:
        score *= 0.85
    if is_ocr:
        score *= 0.9
    if single_source:
        score *= 0.95

    return max(0.0, min(1.0, score))


APPROXIMATE_TERMS = frozenset([
    "approximately", "approx", "circa", "around", "roughly", "about",
    "~", "≈", "nearly", "almost", "estimated",
])


def has_approximate_language(text: str) -> bool:
    """Return True if the evidence text contains hedging language."""
    lower = text.lower()
    return any(term in lower for term in APPROXIMATE_TERMS)
