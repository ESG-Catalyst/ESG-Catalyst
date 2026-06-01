"""Auth API — register and login for the ESG Catalyst platform.

Iteration 1: minimal stateless JWT auth.  Tokens are HS256 JWTs signed with
``SECRET_KEY`` from settings.  No refresh tokens, no revocation list — both
are Iteration 2+ work.

Admin helpers (``_admin_user``, ``GET /admin/users``,
``PATCH /admin/users/{user_id}/role``) live here alongside auth so all
token-handling logic is in one file.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from uuid import UUID

import bcrypt as _bcrypt_lib
import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.company import Company
from app.models.enums import UserRole
from app.models.user import User

log: structlog.BoundLogger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
admin_router = APIRouter(prefix="/api/v1/admin", tags=["admin"])

ALGORITHM = "HS256"

_bearer = HTTPBearer(auto_error=False)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _hash(password: str) -> str:
    """Return a bcrypt hash of *password*."""
    return _bcrypt_lib.hashpw(password.encode(), _bcrypt_lib.gensalt()).decode()


def _verify(plain: str, hashed: str) -> bool:
    """Return ``True`` when *plain* matches the stored bcrypt hash."""
    return _bcrypt_lib.checkpw(plain.encode(), hashed.encode())


def _make_token(user_id: str, role: str) -> str:
    """Encode a short-lived HS256 JWT for *user_id* / *role*."""
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.access_token_expire_minutes
    )
    return jwt.encode(
        {"sub": user_id, "role": role, "exp": expire},
        settings.secret_key,
        algorithm=ALGORITHM,
    )


def _decode_token(token: str) -> dict:
    """Decode and verify an HS256 JWT.  Raises HTTP 401 on any error."""
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        ) from exc


async def _get_or_create_company(
    db: AsyncSession,
    name: str,
    institution_type: str,
) -> Company:
    """Return an existing company by *name* or create one."""
    result = await db.execute(select(Company).where(Company.name == name))
    company = result.scalar_one_or_none()
    if company is not None:
        return company
    company = Company(name=name, industry=institution_type, country="Egypt")
    db.add(company)
    await db.flush()
    await db.refresh(company)
    return company


# ---------------------------------------------------------------------------
# FastAPI dependency — resolves Bearer JWT to the authenticated User row
# ---------------------------------------------------------------------------


async def get_current_user(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Resolve the Bearer JWT to the authenticated ``User`` row.

    Raises HTTP 401 when:
    - The ``Authorization`` header is absent.
    - The token is malformed or expired.
    - The ``sub`` claim is not a valid UUID.
    - The user no longer exists or is deactivated.

    Used by every per-user endpoint to scope queries to the caller's data.
    """
    if not creds:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    payload = _decode_token(creds.credentials)
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )
    try:
        user_uuid = uuid.UUID(user_id)
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        ) from exc

    result = await db.execute(select(User).where(User.id == user_uuid))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )
    return user


async def _admin_user(current: User = Depends(get_current_user)) -> User:
    """Dependency that enforces admin-only access.  Returns the admin user."""
    if current.role != UserRole.admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------


class RegisterRequest(BaseModel):
    """Body for POST /auth/register."""

    full_name: str
    email: EmailStr
    password: str
    institution_name: str
    institution_type: str = "commercial_bank"


class LoginRequest(BaseModel):
    """Body for POST /auth/login."""

    email: EmailStr
    password: str


class AuthResponse(BaseModel):
    """JWT and minimal user identity returned after login / register."""

    access_token: str
    token_type: str = "bearer"
    user_id: str
    role: str


class UserRecord(BaseModel):
    """Admin-facing user row (no sensitive fields)."""

    id: str
    email: str
    full_name: str
    role: str
    institution_name: str
    institution_type: str
    created_at: str

    model_config = {"from_attributes": True}


class RoleUpdateRequest(BaseModel):
    """Body for PATCH /admin/users/{user_id}/role."""

    role: str


# ---------------------------------------------------------------------------
# POST /auth/register
# ---------------------------------------------------------------------------


@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    response_model=AuthResponse,
)
async def register(
    body: RegisterRequest,
    db: AsyncSession = Depends(get_db),
) -> AuthResponse:
    """Create a new user + company and return a JWT.

    Returns 409 when the email is already registered.
    """
    try:
        exists = (
            await db.execute(select(User).where(User.email == body.email))
        ).scalar_one_or_none()
        if exists is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An account with this email already exists",
            )

        company = await _get_or_create_company(
            db, body.institution_name, body.institution_type
        )

        user = User(
            email=body.email,
            hashed_password=_hash(body.password),
            role=UserRole.company_admin,
            company_id=company.id,
        )
        db.add(user)
        await db.flush()
        await db.refresh(user)

        log.info("auth.registered", user_id=str(user.id), email=body.email)
        token = _make_token(str(user.id), user.role.value)
        return AuthResponse(
            access_token=token,
            user_id=str(user.id),
            role=user.role.value,
        )
    except HTTPException:
        raise
    except Exception as exc:
        log.exception("auth.register_error", email=body.email, error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Registration failed due to an unexpected server error",
        ) from exc


# ---------------------------------------------------------------------------
# POST /auth/login
# ---------------------------------------------------------------------------


@router.post("/login", response_model=AuthResponse)
async def login(
    body: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> AuthResponse:
    """Verify credentials and return a JWT.

    Returns 401 for unknown email or wrong password (deliberately vague to
    avoid user-enumeration).
    """
    try:
        result = await db.execute(select(User).where(User.email == body.email))
        user: Optional[User] = result.scalar_one_or_none()

        if user is None or not _verify(body.password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
            )
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account is deactivated",
            )

        log.info("auth.login", user_id=str(user.id))
        token = _make_token(str(user.id), user.role.value)
        return AuthResponse(
            access_token=token,
            user_id=str(user.id),
            role=user.role.value,
        )
    except HTTPException:
        raise
    except Exception as exc:
        log.exception("auth.login_error", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Login failed due to an unexpected server error",
        ) from exc


# ---------------------------------------------------------------------------
# GET /admin/users
# ---------------------------------------------------------------------------


@admin_router.get("/users", response_model=List[UserRecord])
async def list_users(
    _admin: User = Depends(_admin_user),
    db: AsyncSession = Depends(get_db),
) -> List[UserRecord]:
    """Return all user rows with their associated company names (admin only)."""
    result = await db.execute(
        select(User, Company).outerjoin(Company, User.company_id == Company.id)
    )
    rows = result.all()
    return [
        UserRecord(
            id=str(user.id),
            email=user.email,
            full_name="",
            role=user.role.value,
            institution_name=company.name if company else "",
            institution_type=company.industry if company else "",
            created_at=user.created_at.isoformat(),
        )
        for user, company in rows
    ]


# ---------------------------------------------------------------------------
# PATCH /admin/users/{user_id}/role
# ---------------------------------------------------------------------------


@admin_router.patch("/users/{user_id}/role", response_model=UserRecord)
async def update_user_role(
    user_id: str,
    body: RoleUpdateRequest,
    _admin: User = Depends(_admin_user),
    db: AsyncSession = Depends(get_db),
) -> UserRecord:
    """Update the role for *user_id* (admin only).

    Returns 422 when *role* is not a valid ``UserRole`` value and 404 when the
    user does not exist.
    """
    try:
        new_role = UserRole(body.role)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unknown role: {body.role}",
        )

    try:
        target_uuid = UUID(user_id)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="user_id is not a valid UUID",
        )

    result = await db.execute(
        select(User, Company)
        .outerjoin(Company, User.company_id == Company.id)
        .where(User.id == target_uuid)
    )
    row = result.one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    user, company = row
    user.role = new_role
    await db.flush()
    await db.refresh(user)

    log.info("admin.role_updated", target_user_id=user_id, new_role=body.role, admin_id=str(_admin.id))
    return UserRecord(
        id=str(user.id),
        email=user.email,
        full_name="",
        role=user.role.value,
        institution_name=company.name if company else "",
        institution_type=company.industry if company else "",
        created_at=user.created_at.isoformat(),
    )
