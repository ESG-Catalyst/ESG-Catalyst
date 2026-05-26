"""Auth API — register and login for the ESG Catalyst platform.

Iteration 1: minimal JWT auth. Tokens are stateless HS256 JWTs signed with
SECRET_KEY from settings. No refresh tokens, no revocation list — both are
Iteration 2+ work.

The API was previously auth-free (CLAUDE.md: "no auth in first pass"). This
module adds auth as a thin layer so the React frontend can obtain a token and
the AuthGuard works. Existing endpoints remain unguarded for now — adding
per-route auth guards is scoped to Iteration 2.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Optional

import bcrypt as _bcrypt_lib
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

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
admin_router = APIRouter(prefix="/api/v1/admin", tags=["admin"])

ALGORITHM = "HS256"


# ── helpers ────────────────────────────────────────────────────────────────────

def _hash(password: str) -> str:
    return _bcrypt_lib.hashpw(password.encode(), _bcrypt_lib.gensalt()).decode()


def _verify(plain: str, hashed: str) -> bool:
    return _bcrypt_lib.checkpw(plain.encode(), hashed.encode())


def _make_token(user_id: str, role: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.access_token_expire_minutes
    )
    return jwt.encode(
        {"sub": user_id, "role": role, "exp": expire},
        settings.secret_key,
        algorithm=ALGORITHM,
    )


async def _get_or_create_company(
    db: AsyncSession,
    name: str,
    institution_type: str,
) -> Company:
    result = await db.execute(select(Company).where(Company.name == name))
    company = result.scalar_one_or_none()
    if company is not None:
        return company
    company = Company(name=name, industry=institution_type, country="Egypt")
    db.add(company)
    await db.flush()
    await db.refresh(company)
    return company


# ── schemas ────────────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    full_name: str
    email: EmailStr
    password: str
    institution_name: str
    institution_type: str = "commercial_bank"


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    role: str


# ── POST /auth/register ────────────────────────────────────────────────────────

@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    response_model=AuthResponse,
)
async def register(
    body: RegisterRequest,
    db: AsyncSession = Depends(get_db),
) -> AuthResponse:
    """Create a new user + company and return a JWT."""
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

        token = _make_token(str(user.id), user.role.value)
        return AuthResponse(
            access_token=token,
            user_id=str(user.id),
            role=user.role.value,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Registration failed: {exc}",
        ) from exc


# ── POST /auth/login ───────────────────────────────────────────────────────────

@router.post("/login", response_model=AuthResponse)
async def login(
    body: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> AuthResponse:
    """Verify credentials and return a JWT."""
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

        token = _make_token(str(user.id), user.role.value)
        return AuthResponse(
            access_token=token,
            user_id=str(user.id),
            role=user.role.value,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Login failed: {exc}",
        ) from exc


# ── Admin helpers ──────────────────────────────────────────────────────────────

def _decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
    except JWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc

_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Resolve the Bearer JWT to the authenticated User row.

    Raises 401 if the header is missing, the token is malformed/expired, the
    subject is not a valid UUID, or the user no longer exists / is deactivated.
    Used by every per-user endpoint to scope queries to the caller's data.
    """
    if not creds:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    payload = _decode_token(creds.credentials)
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    try:
        user_uuid = uuid.UUID(user_id)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc

    result = await db.execute(select(User).where(User.id == user_uuid))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    return user


async def _admin_user(
    current: User = Depends(get_current_user),
) -> User:
    if current.role != UserRole.admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return current


# ── Admin schemas ──────────────────────────────────────────────────────────────

class UserRecord(BaseModel):
    id: str
    email: str
    full_name: str
    role: str
    institution_name: str
    institution_type: str
    created_at: str

    model_config = {"from_attributes": True}


class RoleUpdateRequest(BaseModel):
    role: str


# ── GET /admin/users ───────────────────────────────────────────────────────────

@admin_router.get("/users", response_model=List[UserRecord])
async def list_users(
    _admin: User = Depends(_admin_user),
    db: AsyncSession = Depends(get_db),
) -> List[UserRecord]:
    result = await db.execute(select(User, Company).outerjoin(Company, User.company_id == Company.id))
    rows = result.all()
    out = []
    for user, company in rows:
        out.append(UserRecord(
            id=str(user.id),
            email=user.email,
            full_name="",
            role=user.role.value,
            institution_name=company.name if company else "",
            institution_type=company.industry if company else "",
            created_at=user.created_at.isoformat(),
        ))
    return out


# ── PATCH /admin/users/{user_id}/role ─────────────────────────────────────────

@admin_router.patch("/users/{user_id}/role", response_model=UserRecord)
async def update_user_role(
    user_id: str,
    body: RoleUpdateRequest,
    _admin: User = Depends(_admin_user),
    db: AsyncSession = Depends(get_db),
) -> UserRecord:
    try:
        new_role = UserRole(body.role)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Unknown role: {body.role}")

    result = await db.execute(select(User, Company).outerjoin(Company, User.company_id == Company.id).where(User.id == uuid.UUID(user_id)))
    row = result.one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="User not found")

    user, company = row
    user.role = new_role
    await db.flush()
    await db.refresh(user)

    return UserRecord(
        id=str(user.id),
        email=user.email,
        full_name="",
        role=user.role.value,
        institution_name=company.name if company else "",
        institution_type=company.industry if company else "",
        created_at=user.created_at.isoformat(),
    )