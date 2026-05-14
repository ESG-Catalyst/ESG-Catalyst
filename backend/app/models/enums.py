import enum


class MetricStatus(str, enum.Enum):
    extracted = "extracted"
    ambiguous = "ambiguous"
    missing = "missing"
    rejected = "rejected"
    approved = "approved"


class UserRole(str, enum.Enum):
    consultant = "consultant"
    company_admin = "company_admin"
    reviewer = "reviewer"


class DocumentStatus(str, enum.Enum):
    uploaded = "uploaded"
    pending = "pending"
    processing = "processing"
    processed = "processed"
    failed = "failed"


class ReportStatus(str, enum.Enum):
    draft = "draft"
    in_review = "in_review"
    approved = "approved"
    published = "published"


class ExtractionMethod(str, enum.Enum):
    llm = "llm"
    questionnaire = "questionnaire"
    manual = "manual"


class MetricType(str, enum.Enum):
    """Scoring-function type for a metric — matches spec §2.1.

    BINARY      — yes/no disclosure; scored by score_binary().
    QUANTITATIVE — numeric value; scored by score_quantitative() with optional
                  benchmark and direction.
    QUALITATIVE  — narrative disclosure; scored by score_qualitative() against
                  a completeness_criteria list.
    Q_PLUS_QL   — blended: numeric + narrative; scored by score_q_plus_ql()
                  with configurable q_weight / ql_weight (default 0.6 / 0.4).
    """

    BINARY = "binary"
    QUANTITATIVE = "quantitative"
    QUALITATIVE = "qualitative"
    Q_PLUS_QL = "q_plus_ql"


class MetricFramework(str, enum.Enum):
    """Which framework an extracted metric originates from.

    Kept as a free-string-style enum so adding FN-CB / FN-IB / FN-AC later
    is a one-line change. Persisted as the canonical framework tag for an
    ExtractedMetric, separate from the gri_code / sasb_code identifier.
    """

    GRI = "GRI"
    SASB_FN_CB = "SASB-FN-CB"
    SASB_FN_IB = "SASB-FN-IB"
    SASB_FN_AC = "SASB-FN-AC"
    SASB_FN_IN = "SASB-FN-IN"
    SASB_FN_CF = "SASB-FN-CF"
    SASB_FN_MF = "SASB-FN-MF"
    FRA = "FRA"


# ---------------------------------------------------------------------------
# Scoring-engine enums — added for spec §1–2 compliance
# ---------------------------------------------------------------------------

class SectorType(str, enum.Enum):
    """Which sector's weight table and topic hierarchy to apply.

    FINANCIAL     — Egyptian NBFIs (banks, leasing, microfinance, insurance).
                    Pillar weights: E=25%, S=40%, G=35%.
    MANUFACTURING — Egyptian manufacturers (chemicals, food, metals, textiles).
                    Pillar weights: E=45%, S=30%, G=25%.
    """

    FINANCIAL = "financial"
    MANUFACTURING = "manufacturing"


class FrameworkType(str, enum.Enum):
    """Top-level framework source for a metric or scoring rule.

    GRI       — GRI Universal or Sector Standards.
    SASB      — SASB sector-specific standards (FN-CF, FN-IN, EM-MM, etc.).
    FRA       — Egyptian FRA Stage 1 KPIs.
    COMPOSITE — metric blends two or more frameworks (e.g. FRA + GRI 305).
    """

    GRI = "GRI"
    SASB = "SASB"
    FRA = "FRA"
    COMPOSITE = "composite"


class PillarType(str, enum.Enum):
    """ESG pillar — used for pillar-level aggregation and weight lookup."""

    ENVIRONMENTAL = "E"
    SOCIAL = "S"
    GOVERNANCE = "G"


class MetricDirection(str, enum.Enum):
    """Scoring direction for QUANTITATIVE metrics (spec §2.1 score_quantitative).

    HIGHER_BETTER — higher value → better score (e.g. % renewable energy).
    LOWER_BETTER  — lower value → better score (e.g. GHG intensity, injury rate).
    NEUTRAL       — any disclosed value earns full existence score regardless
                    of magnitude (e.g. headcount, waste volume).
    """

    HIGHER_BETTER = "higher_better"
    LOWER_BETTER = "lower_better"
    NEUTRAL = "neutral"


class GradeLevel(str, enum.Enum):
    """Letter grade mapped from composite ESG score (spec §2.4 score_to_grade).

    A — score >= 85
    B — score >= 70
    C — score >= 55
    D — score >= 40
    F — score <  40
    """

    A = "A"   # >= 85
    B = "B"   # >= 70
    C = "C"   # >= 55
    D = "D"   # >= 40
    F = "F"   # <  40
