"""ClimateBERT ESG relevance filter — scores chunks for ESG content.

Primary model: ``climatebert/distilroberta-base-climate-detector`` (binary:
"yes" / "no" for climate-related text).  Since ClimateBERT only covers the
*Environmental* pillar, a lightweight keyword filter supplements it for
Social (S) and Governance (G) content.

Usage:
    from app.core.pipeline.classifier import classify_chunks

    results = classify_chunks(chunks, threshold=0.5)
    relevant = [r for r in results if r.is_relevant]
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import structlog

from app.core.pipeline.chunker import Chunk

logger = structlog.get_logger(__name__)

_classifier_pipeline = None  # lazy-loaded

# ── S & G keyword sets (ClimateBERT already covers E) ────────────────────
_SOCIAL_KEYWORDS = re.compile(
    r"\b("
    r"employee|employees|workforce|staff|headcount"
    r"|hire[ds]?|hiring|recruitment|turnover|attrition|retention"
    r"|injur(?:y|ies)|fatalit(?:y|ies)|accident|incident|safety|health"
    r"|divers(?:ity|e)|gender|female|male|women|minority|inclusion"
    r"|training|development|human\s*rights|child\s*labour|labor"
    r"|communit(?:y|ies)|stakeholder|social\s*impact|philanthropy"
    r"|privacy|data\s*(?:breach|protection)|complaint|customer"
    r"|wage|compensation|benefit|parental\s*leave"
    r")\b",
    re.IGNORECASE,
)

_GOVERNANCE_KEYWORDS = re.compile(
    r"\b("
    r"board|director|governance|committee|chairman|chairperson"
    r"|independent\s*member|non[\-\s]*executive|executive\s*member"
    r"|audit|compliance|risk\s*management|internal\s*control"
    r"|ethic|anti[\-\s]*corruption|bribery|transparency|disclosure"
    r"|whistleblow|code\s*of\s*conduct|conflict\s*of\s*interest"
    r"|regulat(?:or|ory)|supervisory|fiduciary|shareholder"
    r"|remuneration|nomination"
    r")\b",
    re.IGNORECASE,
)

# Minimum keyword hits to count as relevant
_KEYWORD_THRESHOLD = 2


# ── Data class ───────────────────────────────────────────────────────────
@dataclass
class ClassifiedChunk:
    """A chunk annotated with ESG relevance scores."""

    chunk: Chunk
    climate_score: float     # 0.0–1.0 from ClimateBERT (E pillar)
    social_score: float      # 0.0–1.0 keyword density (S pillar)
    governance_score: float  # 0.0–1.0 keyword density (G pillar)
    esg_score: float         # max of the three pillar scores
    is_relevant: bool
    pillar: str              # dominant pillar: "E", "S", "G", or "none"


# ── Model loading ────────────────────────────────────────────────────────
def _get_classifier():
    """Lazy-load the ClimateBERT pipeline."""
    global _classifier_pipeline
    if _classifier_pipeline is None:
        from transformers import pipeline as hf_pipeline

        logger.info("classifier.loading_model")
        _classifier_pipeline = hf_pipeline(
            "text-classification",
            model="climatebert/distilroberta-base-climate-detector",
            top_k=None,
            truncation=True,
            max_length=512,
        )
        logger.info("classifier.model_loaded")
    return _classifier_pipeline


# ── Public API ───────────────────────────────────────────────────────────
def classify_chunks(
    chunks: list[Chunk],
    threshold: float = 0.5,
    use_climate_model: bool = True,
) -> list[ClassifiedChunk]:
    """Score each chunk for ESG relevance across all three pillars.

    Args:
        chunks: Output of ``chunk_document()``.
        threshold: Minimum ``esg_score`` to be marked ``is_relevant``.
        use_climate_model: If ``False``, skip ClimateBERT and use keywords only
            (useful when the model is unavailable or for fast testing).

    Returns:
        List of ``ClassifiedChunk`` in the same order as input.
    """
    if not chunks:
        return []

    # ── Climate scores (E pillar) via ClimateBERT ────────────────────
    if use_climate_model:
        climate_scores = _batch_climate_scores([c.text for c in chunks])
    else:
        climate_scores = [0.0] * len(chunks)

    # ── Keyword scores (S + G pillars) ───────────────────────────────
    results: list[ClassifiedChunk] = []

    for chunk, c_score in zip(chunks, climate_scores):
        s_score = _keyword_score(chunk.text, _SOCIAL_KEYWORDS)
        g_score = _keyword_score(chunk.text, _GOVERNANCE_KEYWORDS)
        esg_score = max(c_score, s_score, g_score)

        # Determine dominant pillar
        scores = {"E": c_score, "S": s_score, "G": g_score}
        pillar = max(scores, key=scores.get) if esg_score > 0 else "none"

        results.append(ClassifiedChunk(
            chunk=chunk,
            climate_score=c_score,
            social_score=s_score,
            governance_score=g_score,
            esg_score=esg_score,
            is_relevant=esg_score >= threshold,
            pillar=pillar,
        ))

    relevant = sum(1 for r in results if r.is_relevant)
    logger.info(
        "classifier.done",
        total=len(results),
        relevant=relevant,
        filtered=len(results) - relevant,
        threshold=threshold,
    )
    return results


# ── Climate model scoring ────────────────────────────────────────────────
def _batch_climate_scores(texts: list[str]) -> list[float]:
    """Run ClimateBERT on a batch of texts and return P(yes) scores."""
    clf = _get_classifier()

    # ClimateBERT has a 512-token limit; truncate long texts
    truncated = [t[:2000] for t in texts]

    raw_results = clf(truncated, batch_size=16)

    scores: list[float] = []
    for result in raw_results:
        # result is a list of dicts: [{"label": "yes", "score": 0.9}, {"label": "no", ...}]
        label_scores = {d["label"]: d["score"] for d in result}
        scores.append(label_scores.get("yes", 0.0))

    return scores


# ── Keyword scoring ──────────────────────────────────────────────────────
def _keyword_score(text: str, pattern: re.Pattern) -> float:
    """Compute a 0.0–1.0 relevance score based on keyword density.

    Returns 0 when fewer than ``_KEYWORD_THRESHOLD`` matches are found.
    Saturates at 1.0 when ≥ 10 distinct keyword matches appear.
    """
    matches = pattern.findall(text)
    unique_hits = len(set(m.lower() for m in matches))

    if unique_hits < _KEYWORD_THRESHOLD:
        return 0.0

    # Saturating scale: 2 hits → 0.3, 5 → 0.6, 10+ → 1.0
    return min(1.0, unique_hits / 10)
