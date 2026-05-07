"""JWT authentication + authorization helpers.

Provides:
    - Password hashing (bcrypt via passlib)
    - JWT token creation / verification
    - ``get_current_user`` FastAPI dependency
    - ``require_role`` dependency factory for role-based access
    - ``get_accessible_company_ids`` for company-scoped queries

Usage:
    from app.core.auth import get_current_user, require_role

    @router.get("/protected")
    async def protected(user: User = Depends(get_current_user)):
        ...

    @router.post("/admin-only")
    async def admin(user: User = Depends(require_role(UserRole.consultant))):
        ...
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

import structlog
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.enums import UserRole
from app.models.user import User

logger = structlog.get_logger(__name__)

# ── Password hashing ─────────────────────────────────────────────────────
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """Hash a plaintext password."""
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a plaintext password against its hash."""
    return pwd_context.verify(plain, hashed)


# ── JWT tokens ────────────────────────────────────────────────────────────
_ALGORITHM = "HS256"

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def create_access_token(
    user_id: UUID,
    role: UserRole,
    company_id: Optional[UUID] = None,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """Create a signed JWT access token."""
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.access_token_expire_minutes)
    )
    payload = {
        "sub": str(user_id),
        "role": role.value,
        "exp": expire,
    }
    if company_id:
        payload["company_id"] = str(company_id)
    return jwt.encode(payload, settings.secret_key, algorithm=_ALGORITHM)


def create_refresh_token(user_id: UUID) -> str:
    """Create a long-lived refresh token (7 days)."""
    expire = datetime.now(timezone.utc) + timedelta(days=7)
    payload = {
        "sub": str(user_id),
        "type": "refresh",
        "exp": expire,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=_ALGORITHM)


def decode_token(token: str) -> dict:
    """Decode and validate a JWT token. Raises HTTPException on failure."""
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[_ALGORITHM])
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


# ── FastAPI dependencies ──────────────────────────────────────────────────
async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Dependency: extract and validate the current user from the JWT token."""
    payload = decode_token(token)

    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )

    result = await db.execute(select(User).where(User.id == UUID(user_id)))
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is deactivated",
        )

    return user


def require_role(*allowed_roles: UserRole):
    """Dependency factory: require the current user to have one of the given roles.

    Usage:
        @router.post("/admin-only")
        async def endpoint(user: User = Depends(require_role(UserRole.consultant))):
            ...
    """

    async def _check(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires role: {', '.join(r.value for r in allowed_roles)}",
            )
        return user

    return _check


# ── Company scoping ───────────────────────────────────────────────────────
def get_accessible_company_ids(user: User) -> Optional[list[UUID]]:
    """Return the company IDs a user is allowed to access.

    - Consultants: ``None`` (access all companies — they manage multiple clients)
    - Company users / reviewers: ``[user.company_id]`` (single company only)

    Returns ``None`` to mean "no filter" (full access).
    Raises 403 if a company_user has no company_id assigned.
    """
    if user.role == UserRole.consultant:
        return None  # full access

    if user.company_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User has no company assigned. Contact your administrator.",
        )

    return [user.company_id]


def assert_company_access(user: User, company_id: UUID) -> None:
    """Raise 403 if the user cannot access the given company_id."""
    allowed = get_accessible_company_ids(user)
    if allowed is not None and company_id not in allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this company",
        )
