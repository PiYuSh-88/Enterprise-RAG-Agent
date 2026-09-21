"""
repositories/document_repository.py
-------------------------------------
Concrete PostgreSQL implementation of IDocumentRepository.

Architecture (NOTES.md):
  Router → Service → THIS REPOSITORY → PostgreSQL
  Raw SQL / ORM operations live here and nowhere else.

The session is injected via __init__ (received from get_db() dependency),
consistent with the DI pattern established in Milestone 0.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document
from app.schemas.document import DocumentCreate


class DocumentRepository:
    """
    Implements IDocumentRepository against PostgreSQL via async SQLAlchemy.

    The session is NOT committed here — commit/rollback is the responsibility
    of the get_db() dependency (core/database.py), which wraps the session
    in a try/commit/except-rollback block around each request.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, data: DocumentCreate) -> Document:
        """
        Insert a new document row and return the ORM instance with its DB id.

        Uses flush() (not commit()) so the returned object has a populated id
        while the transaction remains open for the request lifecycle.
        """
        doc = Document(
            filename=data.filename,
            file_type=data.file_type,
            file_size_bytes=data.file_size_bytes,
            char_count=data.char_count,
            extracted_text=data.extracted_text,
            status=data.status,
        )
        self._session.add(doc)
        await self._session.flush()      # assigns id without committing
        await self._session.refresh(doc) # loads server defaults (uploaded_at)
        return doc

    async def get_by_id(self, doc_id: uuid.UUID) -> Document | None:
        """
        Fetch a document by primary key.

        Returns None if no row with the given id exists.
        """
        result = await self._session.execute(
            select(Document).where(Document.id == doc_id)
        )
        return result.scalar_one_or_none()

    async def update_status(self, doc_id: uuid.UUID, status: str) -> Document | None:
        """
        Update the status of an existing document.

        Returns the updated Document or None if doc_id not found.
        Commits changes immediately so lifecycle transitions (e.g. 'indexing', 'error')
        persist even if downstream exceptions raise HTTPException.
        """
        doc = await self.get_by_id(doc_id)
        if doc is None:
            return None
        doc.status = status
        await self._session.commit()
        await self._session.refresh(doc)
        return doc


