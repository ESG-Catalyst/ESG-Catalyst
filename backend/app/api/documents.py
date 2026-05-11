"""Documents API — upload PDFs and read document metadata.

Iteration 1: no auth. A default company is created on first use so the
upload endpoint can save files under ``data/uploads/{company_id}/``.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.company import Company
from app.models.document import Document
from app.models.enums import DocumentStatus
from app.schemas.document import DocumentSchema

router = APIRouter(prefix="/api/v1/documents", tags=["documents"])

UPLOAD_ROOT = Path("data/uploads")
DEFAULT_COMPANY_NAME = "Default Company"


class DocumentUploadResponse(BaseModel):
    """Minimal response per Iteration 1 spec."""

    document_id: UUID
    filename: str
    status: DocumentStatus


async def _get_or_create_default_company(db: AsyncSession) -> Company:
    result = await db.execute(select(Company).where(Company.name == DEFAULT_COMPANY_NAME))
    company = result.scalar_one_or_none()
    if company is not None:
        return company
    company = Company(
        name=DEFAULT_COMPANY_NAME,
        industry="banking",
        country="Egypt",
    )
    db.add(company)
    await db.flush()
    await db.refresh(company)
    return company


@router.post(
    "/upload",
    status_code=status.HTTP_201_CREATED,
    response_model=DocumentUploadResponse,
)
async def upload_document(
    file: UploadFile = File(...),
    company_id: Optional[UUID] = Form(default=None),
    db: AsyncSession = Depends(get_db),
) -> DocumentUploadResponse:
    """Accept a multipart PDF and persist it to disk + DB."""
    try:
        if file.filename is None or not file.filename.lower().endswith(".pdf"):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Only .pdf uploads are accepted in Iteration 1",
            )

        if company_id is None:
            company = await _get_or_create_default_company(db)
            company_id = company.id
        else:
            result = await db.execute(select(Company).where(Company.id == company_id))
            if result.scalar_one_or_none() is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Company {company_id} not found",
                )

        content = await file.read()
        max_bytes = settings.max_upload_size_mb * 1024 * 1024
        if len(content) > max_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"File exceeds {settings.max_upload_size_mb} MB limit",
            )
        if len(content) == 0:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Uploaded file is empty",
            )

        company_dir = UPLOAD_ROOT / str(company_id)
        company_dir.mkdir(parents=True, exist_ok=True)
        safe_name = f"{uuid.uuid4().hex}.pdf"
        dest_path = company_dir / safe_name
        dest_path.write_bytes(content)

        doc = Document(
            company_id=company_id,
            filename=file.filename,
            file_path=str(dest_path),
            file_type="pdf",
            status=DocumentStatus.uploaded,
        )
        db.add(doc)
        await db.flush()
        await db.refresh(doc)

        return DocumentUploadResponse(
            document_id=doc.id,
            filename=doc.filename,
            status=doc.status,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Upload failed: {exc}",
        ) from exc


@router.get("/{document_id}", response_model=DocumentSchema)
async def get_document(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> Document:
    """Return current metadata + status for a document."""
    try:
        result = await db.execute(select(Document).where(Document.id == document_id))
        doc = result.scalar_one_or_none()
        if doc is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found",
            )
        return doc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Lookup failed: {exc}",
        ) from exc
