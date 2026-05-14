"""ESG relevance + pillar classifier — Architecture B (parallel ensemble).

This module is the production landing of the C3 classifier shootout
(``scripts/experiments/classification_*.py``). It replaces the
ClimateBERT-only baseline that was previously a known bias source for
Social and Governance content.

Architecture (verified in MLflow experiment ``m2-classification-experiments``):

    Three independent transformer voters, run in parallel on every chunk:
      1. ClimateBERT  (climatebert/distilroberta-base-climate-detector)
      2. FinBERT-ESG  (yiyanghkust/finbert-esg-9-categories)
      3. ESG-BERT     (nbroad/ESG-BERT, 26 SASB topics)

    Per-voter "is this chunk ESG-relevant?" signal:
      - ClimateBERT : P(yes) > threshold
      - FinBERT-ESG : sum of P over the 8 ESG categories > threshold
      - ESG-BERT    : argmax-class confidence > threshold

    A chunk passes (esg_relevant=True) iff at least 2 of 3 voters agree.

    Pillar = majority among passing voters' argmax pillar; ClimateBERT
    can only vote "E" (its single signal); ties broken by summed vote
    confidence.

    Topic = FinBERT-ESG's argmax category if available, else ESG-BERT's
    argmax SASB topic. None when the chunk is not relevant.

Bias-audit reference: ``scripts/experiments/results/multi_arch.json``
Decision record: ``ESG_Catalyst_Wiki/wiki/decisions/classification-architecture.md``

Usage:
    from app.core.nlp.classifier import classify_chunks

    results = classify_chunks(chunks, threshold=0.3)
    relevant = [r for r in results if r.esg_relevant]
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

import structlog

from app.core.nlp.chunker import Chunk

logger = structlog.get_logger(__name__)

# ── Lazy-loaded HF pipelines ────────────────────────────────────────────
_climatebert_pipeline = None
_finbert_esg_pipeline = None
_esgbert_pipeline = None

_DEFAULT_THRESHOLD = 0.3            # validated in C2/C3 experiments
_MAX_TEXT_CHARS = 2000              # send first 2000 chars to each model
_BATCH_SIZE = 16


# ── Keyword fallback (use_climate_model=False) ──────────────────────────
# Kept verbatim from the previous classifier so the no-LLM path is
# unchanged behaviour-wise. Used only when caller explicitly opts out of
# the transformer ensemble.
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
_KEYWORD_THRESHOLD = 2


# ── Native-label → pillar maps ──────────────────────────────────────────
# Verified against actual HF model outputs during the C2 shootout — see
# ``scripts/experiments/classification_shootout.py`` for the audit trail.
_FINBERT_ESG_PILLAR: dict[str, str] = {
    "climate change": "E",
    "natural capital": "E",
    "pollution & waste": "E",
    "pollution and waste": "E",
    "human capital": "S",
    "product liability": "S",
    "community relations": "S",
    "corporate governance": "G",
    "business ethics & values": "G",
    "business ethics and values": "G",
    # "Non-ESG" falls through to None (not in map)
}

_ESGBERT_PILLAR: dict[str, str] = {
    # E
    "climate_change": "E", "ghg_emissions": "E", "air_quality": "E",
    "energy_management": "E", "fuel_management": "E",
    "water_and_wastewater_management": "E",
    "waste_and_hazardous_materials_management": "E",
    "ecological_impacts": "E", "natural_capital": "E",
    "physical_impacts_of_climate_change": "E",
    # S
    "human_rights_and_community_relations": "S",
    "labor_practices": "S", "employee_health_and_safety": "S",
    "employee_engagement_inclusion_and_diversity": "S",
    "customer_welfare": "S", "customer_privacy": "S",
    "data_security": "S", "access_and_affordability": "S",
    "product_quality_and_safety": "S",
    "selling_practices_and_product_labeling": "S",
    # G
    "business_ethics": "G", "competitive_behavior": "G",
    "management_of_legal_and_regulatory_framework": "G",
    "critical_incident_risk_management": "G",
    "systemic_risk_management": "G", "supply_chain_management": "G",
    "business_model_resilience": "G",
    "materials_sourcing_and_efficiency": "G",
    "product_design_and_lifecycle_management": "G",
    "director_removal": "G",
}


# ── Data class ──────────────────────────────────────────────────────────
@dataclass
class ClassifiedChunk:
    """A chunk annotated with ESG relevance + pillar + topic.

    New fields introduced with the arch-B ensemble (C3 decision record):
      - ``esg_relevant`` — mirrors ``is_relevant`` for the post-C3
        public contract. Both are kept; downstream code may read either.
      - ``topic`` — fine-grained category from the pillar classifiers
        (e.g. "climate change", "employee_health_and_safety"). ``None``
        when the chunk is not relevant.
      - ``pillar`` is now ``Optional[str]`` — None on non-relevant chunks
        (was the string "none" previously).
    """

    chunk: Chunk
    climate_score: float     # 0.0–1.0 from ClimateBERT (E pillar)
    social_score: float      # 0.0–1.0  — pillar-S confidence (ensemble or keyword)
    governance_score: float  # 0.0–1.0  — pillar-G confidence (ensemble or keyword)
    esg_score: float         # max pillar confidence  (primary "esg_score" per public spec)
    is_relevant: bool        # legacy field — same value as ``esg_relevant``
    esg_relevant: bool       # new canonical field
    pillar: Optional[str]    # "E" | "S" | "G" | None
    topic: Optional[str]     # fine-grained category | None
    votes_for: int = 0       # how many of the 3 voters flagged ESG-relevant
    ensemble: bool = True    # False when the keyword-only fallback was used


# ── Model loading ───────────────────────────────────────────────────────
def _load_pipeline(name: str):
    """Lazy hf_pipeline loader. Raises on first call if model not cached."""
    from transformers import pipeline as hf_pipeline

    return hf_pipeline(
        "text-classification",
        model=name,
        top_k=None,                 # return all class scores
        truncation=True,
        max_length=512,
    )


def _get_climatebert():
    global _climatebert_pipeline
    if _climatebert_pipeline is None:
        logger.info("classifier.loading_model", model="climatebert")
        _climatebert_pipeline = _load_pipeline(
            "climatebert/distilroberta-base-climate-detector"
        )
        logger.info("classifier.model_loaded", model="climatebert")
    return _climatebert_pipeline


def _get_finbert_esg():
    global _finbert_esg_pipeline
    if _finbert_esg_pipeline is None:
        logger.info("classifier.loading_model", model="finbert-esg")
        _finbert_esg_pipeline = _load_pipeline(
            "yiyanghkust/finbert-esg-9-categories"
        )
        logger.info("classifier.model_loaded", model="finbert-esg")
    return _finbert_esg_pipeline


def _get_esgbert():
    global _esgbert_pipeline
    if _esgbert_pipeline is None:
        logger.info("classifier.loading_model", model="esgbert")
        _esgbert_pipeline = _load_pipeline("nbroad/ESG-BERT")
        logger.info("classifier.model_loaded", model="esgbert")
    return _esgbert_pipeline


# ── Per-model batched scoring ───────────────────────────────────────────
def _climatebert_scores(texts: list[str]) -> list[float]:
    """P(yes) per chunk from ClimateBERT."""
    clf = _get_climatebert()
    raw = clf([t[:_MAX_TEXT_CHARS] for t in texts], batch_size=_BATCH_SIZE)
    out: list[float] = []
    for row in raw:
        scores = {d["label"]: d["score"] for d in row}
        out.append(scores.get("yes", 0.0))
    return out


def _finbert_esg_predict(texts: list[str]) -> list[dict]:
    """Per chunk: {'esg_mass': float, 'pillar': str|None, 'topic': str|None,
    'pillar_mass': {'E': f, 'S': f, 'G': f}}."""
    clf = _get_finbert_esg()
    raw = clf([t[:_MAX_TEXT_CHARS] for t in texts], batch_size=_BATCH_SIZE)
    out: list[dict] = []
    for row in raw:
        pmass = {"E": 0.0, "S": 0.0, "G": 0.0}
        best_label, best_score = None, -1.0
        for d in row:
            lbl, sc = d["label"], d["score"]
            pillar = _FINBERT_ESG_PILLAR.get(lbl.lower().strip())
            if pillar:
                pmass[pillar] += sc
                if sc > best_score:
                    best_label, best_score = lbl, sc
        esg_mass = sum(pmass.values())
        pillar = max(pmass, key=pmass.get) if esg_mass > 0 else None
        topic = best_label if esg_mass > 0 else None
        out.append({"esg_mass": esg_mass, "pillar": pillar, "topic": topic,
                    "pillar_mass": pmass})
    return out


def _esgbert_predict(texts: list[str]) -> list[dict]:
    """Per chunk: {'raw_score': argmax-confidence, 'pillar': str|None,
    'topic': str|None, 'pillar_mass': {'E': f, 'S': f, 'G': f}}."""
    clf = _get_esgbert()
    raw = clf([t[:_MAX_TEXT_CHARS] for t in texts], batch_size=_BATCH_SIZE)
    out: list[dict] = []
    for row in raw:
        # argmax across all 26 SASB topics
        best = max(row, key=lambda d: d["score"])
        # pillar mass aggregated across all mapped labels
        pmass = {"E": 0.0, "S": 0.0, "G": 0.0}
        for d in row:
            pillar = _ESGBERT_PILLAR.get(d["label"].lower().strip())
            if pillar:
                pmass[pillar] += d["score"]
        argmax_pillar = _ESGBERT_PILLAR.get(best["label"].lower().strip())
        topic = best["label"] if argmax_pillar else None
        out.append({"raw_score": best["score"], "pillar": argmax_pillar,
                    "topic": topic, "pillar_mass": pmass})
    return out


# ── Keyword fallback ────────────────────────────────────────────────────
def _keyword_score(text: str, pattern: re.Pattern) -> float:
    """0.0–1.0 keyword-density score. Saturates at ~10 distinct hits."""
    matches = pattern.findall(text)
    unique_hits = len(set(m.lower() for m in matches))
    if unique_hits < _KEYWORD_THRESHOLD:
        return 0.0
    return min(1.0, unique_hits / 10)


def _classify_keyword_only(
    chunks: list[Chunk], threshold: float
) -> list[ClassifiedChunk]:
    """No-LLM path. Same logic the old classifier had for use_climate_model=False."""
    results: list[ClassifiedChunk] = []
    for chunk in chunks:
        s = _keyword_score(chunk.text, _SOCIAL_KEYWORDS)
        g = _keyword_score(chunk.text, _GOVERNANCE_KEYWORDS)
        esg = max(s, g)
        relevant = esg >= threshold
        scores = {"S": s, "G": g}
        pillar = max(scores, key=scores.get) if relevant and esg > 0 else None
        results.append(ClassifiedChunk(
            chunk=chunk,
            climate_score=0.0,
            social_score=s,
            governance_score=g,
            esg_score=esg,
            is_relevant=relevant,
            esg_relevant=relevant,
            pillar=pillar,
            topic=None,
            votes_for=0,
            ensemble=False,
        ))
    return results


# ── Public API ──────────────────────────────────────────────────────────
def classify_chunks(
    chunks: list[Chunk],
    threshold: float = _DEFAULT_THRESHOLD,
    use_climate_model: bool = True,
) -> list[ClassifiedChunk]:
    """Score each chunk for ESG relevance + pillar using the arch-B ensemble.

    Args:
        chunks: Output of ``chunk_document()``.
        threshold: Minimum per-voter signal for that voter to flag the chunk
            as ESG-relevant. A chunk is classified as relevant when **at
            least 2 of 3 voters** clear the threshold. Default 0.3
            (validated in C2/C3 — see decisions record).
        use_climate_model: If False, fall back to the legacy keyword-only
            path (no transformer models loaded). Retained for back-compat
            with callers that cannot afford the model RAM/latency.

    Returns:
        List of ``ClassifiedChunk`` in the same order as input. Each item
        carries the new ``esg_relevant`` / ``pillar`` / ``topic`` fields
        defined in the post-C3 public contract, plus the legacy
        ``is_relevant`` / per-pillar scores for backwards compatibility.
    """
    if not chunks:
        return []

    if not use_climate_model:
        results = _classify_keyword_only(chunks, threshold)
        logger.info(
            "classifier.done",
            mode="keyword-only",
            total=len(results),
            relevant=sum(1 for r in results if r.esg_relevant),
            threshold=threshold,
        )
        return results

    texts = [c.text for c in chunks]
    cb_scores = _climatebert_scores(texts)
    fe_preds = _finbert_esg_predict(texts)
    eb_preds = _esgbert_predict(texts)

    results: list[ClassifiedChunk] = []
    for chunk, cb, fe, eb in zip(chunks, cb_scores, fe_preds, eb_preds):
        cb_vote = cb > threshold
        fe_vote = fe["esg_mass"] > threshold
        eb_vote = eb["raw_score"] > threshold
        votes = int(cb_vote) + int(fe_vote) + int(eb_vote)
        relevant = votes >= 2

        # Pillar majority among passing voters, tie-break by sum of confidences.
        # ClimateBERT can only vote "E" (its sole signal).
        pillar: Optional[str] = None
        topic: Optional[str] = None
        if relevant:
            tally: dict[str, list[float]] = {}
            if cb_vote:
                tally.setdefault("E", []).append(cb)
            if fe_vote and fe["pillar"]:
                tally.setdefault(fe["pillar"], []).append(
                    fe["pillar_mass"].get(fe["pillar"], fe["esg_mass"])
                )
            if eb_vote and eb["pillar"]:
                tally.setdefault(eb["pillar"], []).append(
                    eb["pillar_mass"].get(eb["pillar"], eb["raw_score"])
                )
            if tally:
                max_count = max(len(v) for v in tally.values())
                cands = [p for p, v in tally.items() if len(v) == max_count]
                pillar = max(cands, key=lambda p: sum(tally[p]))
            # Topic preference: finbert-esg (9-cat) is more discriminative for
            # E/S/G than esgbert (which over-classifies into G). Fall back to
            # esgbert when finbert-esg returned no ESG mass.
            topic = fe["topic"] or eb["topic"]

        # Per-pillar scores exposed for backwards compatibility — combine
        # the two pillar-aware models' per-pillar masses; ClimateBERT
        # contributes to E only.
        e_mass = max(cb, fe["pillar_mass"]["E"], eb["pillar_mass"]["E"])
        s_mass = max(fe["pillar_mass"]["S"], eb["pillar_mass"]["S"])
        g_mass = max(fe["pillar_mass"]["G"], eb["pillar_mass"]["G"])
        esg_score = max(e_mass, s_mass, g_mass)

        results.append(ClassifiedChunk(
            chunk=chunk,
            climate_score=cb,
            social_score=s_mass,
            governance_score=g_mass,
            esg_score=esg_score,
            is_relevant=relevant,
            esg_relevant=relevant,
            pillar=pillar,
            topic=topic,
            votes_for=votes,
            ensemble=True,
        ))

    relevant_n = sum(1 for r in results if r.esg_relevant)
    by_pillar = {"E": 0, "S": 0, "G": 0}
    for r in results:
        if r.esg_relevant and r.pillar in by_pillar:
            by_pillar[r.pillar] += 1
    logger.info(
        "classifier.done",
        mode="ensemble-arch-B",
        total=len(results),
        relevant=relevant_n,
        filtered=len(results) - relevant_n,
        threshold=threshold,
        pct_E=round(100.0 * by_pillar["E"] / max(1, relevant_n), 2),
        pct_S=round(100.0 * by_pillar["S"] / max(1, relevant_n), 2),
        pct_G=round(100.0 * by_pillar["G"] / max(1, relevant_n), 2),
    )
    return results