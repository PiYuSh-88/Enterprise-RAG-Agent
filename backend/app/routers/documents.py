"""
routers/documents.py
--------------------
HTTP endpoints for document ingestion.

Architecture:
  This router is intentionally thin.  It:
    1. Receives the HTTP request and extracts FastAPI-typed parameters.
    2. Delegates to DocumentService for all business logic.
    3. Converts the service result to an HTTP response.

  No validation, extraction, or database logic belongs here.

Endpoints (Milestone 1):
  POST /documents/upload    — Upload and ingest a PDF or DOCX file.
  GET  /documents/{doc_id}  — Retrieve document metadata by id.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.repositories.document_repository import DocumentRepository
from app.schemas.document import DocumentResponse
from app.services.document_service import DocumentService

router = APIRouter(prefix="/documents", tags=["Documents"])


# ── Dependency ────────────────────────────────────────────────────────────────


def get_document_service(
    db: AsyncSession = Depends(get_db),
) -> DocumentService:
    """
    Dependency that wires DocumentRepository → DocumentService.

    Kept as a plain (non-async) dependency factory — DocumentRepository
    construction is synchronous, only its methods are async.
    """
    repository = DocumentRepository(db)
    return DocumentService(repository)


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post(
    "/upload",
    response_model=DocumentResponse,
    status_code=201,
    summary="Upload and ingest a document",
    description=(
        "Upload a PDF or DOCX file. "
        "The file is validated (type and size), text is extracted, "
        "and document metadata is stored in PostgreSQL. "
        "Returns document metadata — the extracted text is stored internally "
        "for use by the chunking/embedding pipeline (Milestone 2) but is not "
        "included in the response."
    ),
)
async def upload_document(
    file: UploadFile,
    settings: Settings = Depends(get_settings),
    service: DocumentService = Depends(get_document_service),
) -> DocumentResponse:
    """Validate, extract, and persist an uploaded document."""
    return await service.upload(file, settings.max_upload_size_mb)


@router.get(
    "/{doc_id}",
    response_model=DocumentResponse,
    summary="Get document metadata",
    description="Retrieve metadata for a previously uploaded document by its UUID.",
)
async def get_document(
    doc_id: uuid.UUID,
    service: DocumentService = Depends(get_document_service),
) -> DocumentResponse:
    """Fetch document metadata by id."""
    doc = await service.get_by_id(doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    return doc
