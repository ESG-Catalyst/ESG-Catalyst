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
    """Shape of the extracted value — drives prompt + parsing.

    quantitative — plain number (counts, volumes, weights). value is a float.
    monetary     — number with a currency. value is a float, currency is set.
    rate         — ratio or percentage. value is the ratio; breakdown holds numerator + denominator.
    qualitative  — narrative disclosure (SASB "Discussion and Analysis"). value is None; evidence_chunk holds the summary.
    activity     — SASB activity metric quantifying scale (e.g., # accounts, # policies). value is a count.
    """

    quantitative = "quantitative"
    monetary = "monetary"
    rate = "rate"
    qualitative = "qualitative"
    activity = "activity"


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
