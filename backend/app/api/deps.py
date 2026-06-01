"""Shared FastAPI dependencies for the ESG Catalyst API.

Provides re-usable helpers that enforce the two load-bearing invariants:
  1. All data access is scoped to ``current_user.company_id``.
  2. Cross-company access returns 404 (not 403) so a caller cannot distinguish
     "doesn't exist" from "belongs to another tenant."

Usage example::

    @router.get("/{doc_id}")
    async def get_doc(
        doc_id: UUID,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
    ):
        doc = await require_owned_record(db, Document, doc_id, current_user)
        ...
"""

from __future__ import annotations

from typing import Any, Type, TypeVar
from uuid import UUID

import structlog
from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.database import get_db
from app.models.user import User

log: structlog.BoundLogger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Re-export get_current_user so routers can import from a single deps module.
# ---------------------------------------------------------------------------
__all__ = [
    "get_current_user",
    "get_db",
    "require_company",
    "require_owned_record",
]

# SQLAlchemy ORM model type-var for the generic helper below.
_ORM = TypeVar("_ORM")


def require_company(current_user: User) -> UUID:
    """Return ``current_user.company_id`` or raise HTTP 403.

    Consultants without an assigned company cannot own per-company resources,
    so they receive a 403 with an informative message rather than a silent
    empty list or a confusing 500.

    Args:
        current_user: The resolved authenticated user.

    Returns:
        The user's ``company_id`` UUID.

    Raises:
        HTTPException(403): When ``company_id`` is ``None``.
    """
    if current_user.company_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User has no associated company",
        )
    return current_user.company_id


async def require_owned_record(
    db: AsyncSession,
    model: Type[_ORM],
    record_id: UUID,
    current_user: User,
    *,
    id_col: str = "id",
    company_col: str = "company_id",
    not_found_detail: str = "Record not found",
) -> _ORM:
    """Fetch a company-scoped ORM record or raise HTTP 404.

    Loads *model* by *record_id*, then checks that the returned row's
    *company_col* matches ``current_user.company_id``.  Returns 404 in both
    the "row missing" and "wrong tenant" cases so callers cannot probe for the
    existence of another tenant's data.

    Args:
        db: The current async database session.
        model: The SQLAlchemy ORM class to query.
        record_id: The primary-key UUID to look up.
        current_user: The resolved authenticated user (used for scoping).
        id_col: The attribute name of the PK column (default ``"id"``).
        company_col: The attribute name of the tenant FK column
            (default ``"company_id"``).
        not_found_detail: The detail string for the 404 response.

    Returns:
        The ORM instance that belongs to the caller's company.

    Raises:
        HTTPException(403): When ``current_user.company_id`` is ``None``.
        HTTPException(404): When the row is missing or belongs to another
            tenant.
    """
    company_id = require_company(current_user)
    col = getattr(model, id_col)
    result = await db.execute(select(model).where(col == record_id))
    row: Any = result.scalar_one_or_none()
    if row is None or getattr(row, company_col) != company_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=not_found_detail,
        )
    return row  # type: ignore[return-value]
