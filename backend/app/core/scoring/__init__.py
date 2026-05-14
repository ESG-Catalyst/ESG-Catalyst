from app.core.scoring.scorer import (
    ScoringResult,
    score_composite,
    score_document,
    score_metric,
    score_pillar,
    score_report,
    score_topic,
)
from app.core.scoring.fra_compliance import (
    FRA_KPI_REGISTRY,
    FRA_GATE_SCORE_CAP,
    FRA_COVERAGE_THRESHOLD,
    MANDATORY_FRA_KPIS,
    check_fra_gate,
    extract_fra_results_from_scores,
    get_fra_compliance_report,
)
from app.core.scoring.materiality import (
    FINANCIAL_WEIGHTS,
    MANUFACTURING_WEIGHTS,
    get_weight_registry,
)
from app.core.scoring.gap_analysis import generate_gap_analysis

__all__ = [
    # Core scoring functions
    "score_document",
    "score_metric",
    "score_topic",
    "score_pillar",
    "score_composite",
    # Legacy
    "ScoringResult",
    "score_report",
    # FRA gate
    "check_fra_gate",
    "extract_fra_results_from_scores",
    "get_fra_compliance_report",
    "FRA_KPI_REGISTRY",
    "MANDATORY_FRA_KPIS",
    "FRA_GATE_SCORE_CAP",
    "FRA_COVERAGE_THRESHOLD",
    # Weight Brain
    "get_weight_registry",
    "FINANCIAL_WEIGHTS",
    "MANUFACTURING_WEIGHTS",
    # Gap analysis
    "generate_gap_analysis",
]

