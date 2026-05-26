"""Documents API — upload PDFs and read document metadata.

All endpoints are scoped to the authenticated user's company. Cross-company
lookups return 404 (not 403) so a caller cannot probe for the existence of
documents that belong to another tenant.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.config import settings
from app.core.ingestion.parser import SUPPORTED_EXTENSIONS, is_supported_extension
from app.database import get_db
from app.models.document import Document
from app.models.enums import DocumentStatus
from app.models.user import User
from app.schemas.document import DocumentSchema

router = APIRouter(prefix="/api/v1/documents", tags=["documents"])

UPLOAD_ROOT = Path("data/uploads")


class DocumentUploadResponse(BaseModel):
    """Minimal response per Iteration 1 spec."""

    document_id: UUID
    filename: str
    status: DocumentStatus


def _require_company(user: User) -> UUID:
    """Return the caller's company_id or raise 403 if they have none.

    Consultants without an assigned company can't own per-company documents,
    so they get a 403 with a clear message instead of a silent empty list.
    """
    if user.company_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User has no associated company",
        )
    return user.company_id


@router.post(
    "/upload",
    status_code=status.HTTP_201_CREATED,
    response_model=DocumentUploadResponse,
)
async def upload_document(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DocumentUploadResponse:
    """Accept a multipart PDF and persist it under the caller's company."""
    try:
        company_id = _require_company(current_user)

        # Validate against the same set parser.py dispatches on — single
        # source of truth.
        ext = Path(file.filename or "").suffix.lower()
        if not file.filename or not is_supported_extension(ext):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "Unsupported file format. Accepted: "
                    + ", ".join(SUPPORTED_EXTENSIONS)
                ),
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
        # Preserve the real extension on disk so parser.py dispatches
        # correctly (the dispatcher reads path.suffix).
        safe_name = f"{uuid.uuid4().hex}{ext}"
        dest_path = company_dir / safe_name
        dest_path.write_bytes(content)

        doc = Document(
            company_id=company_id,
            uploaded_by=current_user.id,
            filename=file.filename,
            file_path=str(dest_path),
            file_type=ext.lstrip("."),
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


@router.get("/", response_model=list[DocumentSchema])
async def list_documents(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[Document]:
    """Return the caller's company's documents, newest first."""
    try:
        company_id = _require_company(current_user)
        result = await db.execute(
            select(Document)
            .where(Document.company_id == company_id)
            .order_by(Document.created_at.desc())
        )
        return list(result.scalars().all())
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"List failed: {exc}",
        ) from exc


@router.get("/{document_id}", response_model=DocumentSchema)
async def get_document(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Document:
    """Return current metadata + status for a document the caller owns."""
    try:
        company_id = _require_company(current_user)
        result = await db.execute(select(Document).where(Document.id == document_id))
        doc = result.scalar_one_or_none()
        # 404 (not 403) on cross-company so a probe can't distinguish
        # "doesn't exist" from "belongs to someone else".
        if doc is None or doc.company_id != company_id:
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
