# Import all models here so Alembic's autogenerate can discover them.
from app.models.company import Company
from app.models.document import Document
from app.models.metric import ExtractedMetric
from app.models.report import Report
from app.models.user import User

__all__ = ["Company", "User", "Document", "Report", "ExtractedMetric"]
