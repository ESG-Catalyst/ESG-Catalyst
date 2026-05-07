"""Companies API — CRUD for company records (auth + scoping applied)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import assert_company_access, get_accessible_company_ids, get_current_user, require_role
from app.database import get_db
from app.models.company import Company
from app.models.enums import UserRole
from app.models.user import User
from app.schemas.company import CompanyCreate, CompanyResponse, CompanyUpdate

router = APIRouter(prefix="/companies", tags=["companies"])


@router.post("/", status_code=status.HTTP_201_CREATED, response_model=CompanyResponse)
async def create_company(
    body: CompanyCreate,
    user: User = Depends(require_role(UserRole.consultant)),
    db: AsyncSession = Depends(get_db),
):
    """Create a new company. Consultant role required."""
    company = Company(name=body.name, industry=body.industry, country=body.country)
    db.add(company)
    await db.flush()
    await db.refresh(company)
    return company


@router.get("/", response_model=list[CompanyResponse])
async def list_companies(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List companies the current user can access."""
    stmt = select(Company).order_by(Company.name)

    allowed = get_accessible_company_ids(user)
    if allowed is not None:
        stmt = stmt.where(Company.id.in_(allowed))

    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/{company_id}", response_model=CompanyResponse)
async def get_company(
    company_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a company by ID."""
    assert_company_access(user, company_id)

    result = await db.execute(select(Company).where(Company.id == company_id))
    company = result.scalar_one_or_none()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return company


@router.patch("/{company_id}", response_model=CompanyResponse)
async def update_company(
    company_id: UUID,
    body: CompanyUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a company."""
    assert_company_access(user, company_id)

    result = await db.execute(select(Company).where(Company.id == company_id))
    company = result.scalar_one_or_none()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(company, field, value)

    await db.flush()
    await db.refresh(company)
    return company


@router.delete("/{company_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_company(
    company_id: UUID,
    user: User = Depends(require_role(UserRole.consultant)),
    db: AsyncSession = Depends(get_db),
):
    """Delete a company. Consultant role required."""
    assert_company_access(user, company_id)

    result = await db.execute(select(Company).where(Company.id == company_id))
    company = result.scalar_one_or_none()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    await db.delete(company)
