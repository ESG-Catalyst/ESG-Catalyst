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
