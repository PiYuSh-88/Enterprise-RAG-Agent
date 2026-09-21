"""
routers/documents.py
--------------------
HTTP endpoints for document ingestion and indexing.

Architecture:
  This router is intentionally thin. It:
    1. Receives the HTTP request and extracts FastAPI-typed parameters.
    2. Delegates to DocumentService / IndexingService for business logic.
    3. Converts the service result to an HTTP response.

  No validation, extraction, chunking, or database logic belongs here.

Endpoints:
  POST /documents/upload        — Upload and ingest a PDF or DOCX file (M1).
  GET  /documents/{doc_id}      — Retrieve document metadata by id (M1).
  POST /documents/{doc_id}/index — Chunk, embed, and store vectors in Qdrant (M2).
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.repositories.document_repository import DocumentRepository
from app.schemas.chunk import IndexDocumentResponse
from app.schemas.document import DocumentResponse
from app.services.document_service import DocumentService
from app.services.embedding_service import OpenAIEmbeddingService
from app.services.indexing_service import IndexingService
from app.services.interfaces import IEmbeddingService, IVectorRepository

router = APIRouter(prefix="/documents", tags=["Documents"])


# ── Dependencies ──────────────────────────────────────────────────────────────


def get_document_service(
    db: AsyncSession = Depends(get_db),
) -> DocumentService:
    """Dependency that wires DocumentRepository → DocumentService."""
    repository = DocumentRepository(db)
    return DocumentService(repository)


def get_embedding_service(
    settings: Settings = Depends(get_settings),
) -> IEmbeddingService:
    """Dependency that instantiates the production OpenAI embedding service."""
    return OpenAIEmbeddingService(
        api_key=settings.openai_api_key,
        model=settings.openai_embedding_model,
        dimensions=settings.embedding_dimensions,
    )


def get_indexing_service(
    request: Request,
    db: AsyncSession = Depends(get_db),
    embedding_service: IEmbeddingService = Depends(get_embedding_service),
    settings: Settings = Depends(get_settings),
) -> IndexingService:
    """Dependency that wires repositories and embedding service into IndexingService."""
    doc_repo = DocumentRepository(db)
    vector_repo: IVectorRepository = request.app.state.vector_repository
    return IndexingService(
        doc_repo=doc_repo,
        vector_repo=vector_repo,
        embedding_service=embedding_service,
        collection_name=settings.qdrant_collection_name,
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
    )


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


@router.post(
    "/{doc_id}/index",
    response_model=IndexDocumentResponse,
    status_code=200,
    summary="Index document chunks into Qdrant",
    description=(
        "Reads extracted text of an existing document, splits into chunks, "
        "generates 1536-dimensional embeddings, stores vectors in Qdrant, "
        "and updates document status to 'indexed'."
    ),
)
async def index_document(
    doc_id: uuid.UUID,
    service: IndexingService = Depends(get_indexing_service),
) -> IndexDocumentResponse:
    """Chunk, embed, and store an existing document in Qdrant."""
    return await service.index_document(doc_id)
