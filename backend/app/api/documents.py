"""Documents API — upload, list, and manage uploaded files (auth + scoping)."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.auth import assert_company_access, get_accessible_company_ids, get_current_user
from app.database import get_db
from app.models.document import Document
from app.models.enums import DocumentStatus
from app.models.user import User

router = APIRouter(prefix="/documents", tags=["documents"])

# Persistent upload directory (created on first use)
_UPLOAD_DIR = Path("uploads")


# ── Response schema ───────────────────────────────────────────────────────
class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    company_id: UUID
    report_id: Optional[UUID] = None
    filename: str
    file_path: str
    file_type: str
    status: DocumentStatus
    page_count: Optional[int] = None
    language: Optional[str] = None


# ── POST /documents/upload ────────────────────────────────────────────────
@router.post("/upload", status_code=status.HTTP_201_CREATED, response_model=DocumentResponse)
async def upload_document(
    file: UploadFile = File(...),
    company_id: UUID = Query(...),
    report_id: Optional[UUID] = Query(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Upload a document file and create a database record.

    The file is saved to disk under ``uploads/<company_id>/``.
    User must have access to the target company.
    """
    assert_company_access(user, company_id)

    max_bytes = settings.max_upload_size_mb * 1024 * 1024

    # Validate extension
    suffix = Path(file.filename or "unknown").suffix.lower()
    allowed = {".pdf", ".xlsx", ".xls", ".csv", ".png", ".jpg", ".jpeg", ".tiff", ".tif"}
    if suffix not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type {suffix!r}. Allowed: {sorted(allowed)}",
        )

    # Save file to disk
    company_dir = _UPLOAD_DIR / str(company_id)
    company_dir.mkdir(parents=True, exist_ok=True)

    safe_name = f"{uuid.uuid4().hex}{suffix}"
    dest_path = company_dir / safe_name

    content = await file.read()
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds {settings.max_upload_size_mb} MB limit",
        )

    dest_path.write_bytes(content)

    doc = Document(
        company_id=company_id,
        report_id=report_id,
        filename=file.filename or "unknown",
        file_path=str(dest_path),
        file_type=suffix.lstrip("."),
        status=DocumentStatus.pending,
        uploaded_by=user.id,
    )
    db.add(doc)
    await db.flush()
    await db.refresh(doc)

    return doc


# ── GET /documents/ ───────────────────────────────────────────────────────
@router.get("/", response_model=list[DocumentResponse])
async def list_documents(
    company_id: Optional[UUID] = Query(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List documents. Automatically scoped to user's accessible companies."""
    stmt = select(Document).order_by(Document.created_at.desc())

    if company_id:
        # Explicit filter — verify access
        assert_company_access(user, company_id)
        stmt = stmt.where(Document.company_id == company_id)
    else:
        # Auto-scope by user's access
        allowed = get_accessible_company_ids(user)
        if allowed is not None:
            stmt = stmt.where(Document.company_id.in_(allowed))

    result = await db.execute(stmt)
    return result.scalars().all()


# ── GET /documents/{document_id} ──────────────────────────────────────────
@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a single document by ID."""
    result = await db.execute(select(Document).where(Document.id == document_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    assert_company_access(user, doc.company_id)
    return doc


# ── DELETE /documents/{document_id} ───────────────────────────────────────
@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a document record and its file from disk."""
    result = await db.execute(select(Document).where(Document.id == document_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    assert_company_access(user, doc.company_id)

    file_path = Path(doc.file_path)
    if file_path.exists():
        file_path.unlink()

    await db.delete(doc)
