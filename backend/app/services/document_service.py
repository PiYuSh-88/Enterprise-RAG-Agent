"""
services/document_service.py
-----------------------------
Orchestrates the upload → validate → extract → persist flow.

Architecture (NOTES.md):
  Router calls DocumentService.
  DocumentService calls extractor (pure functions) and IDocumentRepository.
  DocumentService never touches SQLAlchemy sessions directly.

Validation order (cheapest checks first):
  1. File extension (no I/O — just string parsing)
  2. File size   (read bytes, count length)
  3. MIME type   (check Content-Type header if provided)
  4. Extraction  (calls pypdf / python-docx)
  5. Persistence (repository.create)
"""

import uuid

from fastapi import HTTPException, UploadFile

from app.ingestion.extractor import (
    ALLOWED_EXTENSIONS,
    MIME_BY_EXTENSION,
    ExtractionError,
    extract_docx,
    extract_pdf,
    get_extension,
    sanitise_filename,
)
from app.models.document import Document
from app.schemas.document import DocumentCreate, DocumentResponse
from app.services.interfaces import IDocumentRepository


class DocumentService:
    """
    Coordinates document ingestion: validate → extract → persist.

    The repository is injected so it can be replaced with a mock in unit tests
    without any FastAPI machinery.
    """

    def __init__(self, repository: IDocumentRepository) -> None:
        self._repo = repository

    # ── Public API ────────────────────────────────────────────────────────────

    async def upload(
        self,
        file: UploadFile,
        max_size_mb: int,
    ) -> DocumentResponse:
        """
        Validate, extract, persist, and return metadata for an uploaded file.

        Raises HTTPException for all user-correctable errors so the router
        does not need any error-handling logic.
        """
        safe_name = sanitise_filename(file.filename or "untitled")
        ext = get_extension(safe_name)

        # ── 1. Extension validation ──────────────────────────────────────────
        if ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Unsupported file type '.{ext}'. "
                    f"Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
                ),
            )

        # ── 2. Read bytes + size validation ─────────────────────────────────
        content: bytes = await file.read()
        max_bytes = max_size_mb * 1024 * 1024
        if len(content) > max_bytes:
            raise HTTPException(
                status_code=413,
                detail=(
                    f"File size {len(content):,} bytes exceeds the "
                    f"{max_size_mb} MB limit ({max_bytes:,} bytes)."
                ),
            )

        # ── 3. MIME validation (only if client sends a specific Content-Type) ─
        if file.content_type and file.content_type not in (
            "application/octet-stream",
            "",
        ):
            expected_mime = MIME_BY_EXTENSION[ext]
            if file.content_type != expected_mime:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Content-Type '{file.content_type}' does not match "
                        f"the expected type for '.{ext}' "
                        f"(expected: '{expected_mime}')."
                    ),
                )

        # ── 4. Text extraction ───────────────────────────────────────────────
        try:
            if ext == "pdf":
                text = extract_pdf(content)
            else:
                text = extract_docx(content)
        except ExtractionError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        # ── 5. Persist ───────────────────────────────────────────────────────
        data = DocumentCreate(
            filename=safe_name,
            file_type=ext,
            file_size_bytes=len(content),
            char_count=len(text),
            extracted_text=text,
            status="extracted",
        )
        doc: Document = await self._repo.create(data)
        return DocumentResponse.model_validate(doc)

    async def get_by_id(self, doc_id: uuid.UUID) -> DocumentResponse | None:
        """
        Retrieve a document's metadata by id.

        Returns None when not found — the router decides the HTTP status.
        """
        doc = await self._repo.get_by_id(doc_id)
        if doc is None:
            return None
        return DocumentResponse.model_validate(doc)
