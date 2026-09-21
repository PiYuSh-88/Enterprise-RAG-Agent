"""
services/indexing_service.py
----------------------------
Orchestrates document chunking, embedding, and vector persistence.

Flow (NOTES.md & MILESTONE_2.md):
  1. Fetch document from PostgreSQL by ID.
  2. Validate extracted text exists.
  3. Update status to 'indexing'.
  4. Ensure Qdrant collection exists (idempotently).
  5. Chunk text using RecursiveCharacterTextSplitter.
  6. Generate 1536-dimensional embeddings (OpenAI text-embedding-3-small).
  7. Upsert vectors and minimal payload into Qdrant.
  8. Clean up any stale points for this document (re-indexing safety).
  9. Update status to 'indexed'.

If embedding or vector upsert fails, existing Qdrant points are preserved
where practical and the document status is updated to 'error'.
"""

import logging
import uuid

from fastapi import HTTPException

from app.ingestion.chunker import chunk_document
from app.schemas.chunk import IndexDocumentResponse
from app.services.interfaces import (
    IDocumentRepository,
    IEmbeddingService,
    IVectorRepository,
)

logger = logging.getLogger(__name__)


class IndexingService:
    """
    Coordinates chunking, embedding, and Qdrant persistence for a document.
    """

    def __init__(
        self,
        doc_repo: IDocumentRepository,
        vector_repo: IVectorRepository,
        embedding_service: IEmbeddingService,
        collection_name: str,
        chunk_size: int = 1000,
        chunk_overlap: int = 150,
    ) -> None:
        self._doc_repo = doc_repo
        self._vector_repo = vector_repo
        self._embedding_service = embedding_service
        self._collection_name = collection_name
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap

    async def index_document(self, doc_id: uuid.UUID) -> IndexDocumentResponse:
        """
        Chunk, embed, and store an existing document in Qdrant.

        Raises:
            HTTPException(404): If document does not exist.
            HTTPException(422): If document has no extracted text.
            HTTPException(502): If embedding or vector storage fails.
        """
        # 1. Fetch document
        doc = await self._doc_repo.get_by_id(doc_id)
        if doc is None:
            raise HTTPException(status_code=404, detail="Document not found.")

        # 2. Validate extracted text
        if not doc.extracted_text or not doc.extracted_text.strip():
            raise HTTPException(
                status_code=422,
                detail="Document has no extracted text to index.",
            )

        # 3. Update status to 'indexing'
        await self._doc_repo.update_status(doc_id, "indexing")

        # 4. Ensure Qdrant collection exists
        try:
            await self._vector_repo.ensure_collection(self._collection_name)
        except Exception as exc:
            logger.error("Failed to ensure Qdrant collection '%s': %s", self._collection_name, exc)
            await self._doc_repo.update_status(doc_id, "error")
            raise HTTPException(
                status_code=502,
                detail=f"Vector store connection failed: {exc}",
            ) from exc

        # 5. Chunk text
        chunks = chunk_document(
            text=doc.extracted_text,
            document_id=doc.id,
            filename=doc.filename,
            file_type=doc.file_type,
            chunk_size=self._chunk_size,
            chunk_overlap=self._chunk_overlap,
        )

        if not chunks:
            await self._doc_repo.update_status(doc_id, "indexed")
            return IndexDocumentResponse(
                document_id=doc_id,
                status="indexed",
                chunks_indexed=0,
            )

        # 6. Generate embeddings
        try:
            texts = [c.text for c in chunks]
            vectors = await self._embedding_service.embed_texts(texts)
        except Exception as exc:
            logger.error("Embedding generation failed for document %s: %s", doc_id, exc)
            await self._doc_repo.update_status(doc_id, "error")
            raise HTTPException(
                status_code=502,
                detail=f"Embedding generation failed: {exc}",
            ) from exc

        # 7. Upsert vectors to Qdrant
        try:
            await self._vector_repo.upsert_chunks(
                collection_name=self._collection_name,
                chunks=chunks,
                vectors=vectors,
            )
        except Exception as exc:
            logger.error("Vector upsert failed for document %s: %s", doc_id, exc)
            await self._doc_repo.update_status(doc_id, "error")
            raise HTTPException(
                status_code=502,
                detail=f"Vector storage failed: {exc}",
            ) from exc

        # 8. Safe re-indexing: remove stale points no longer part of new chunk set
        try:
            active_point_ids = {c.point_id for c in chunks}
            await self._vector_repo.delete_stale_chunks(
                collection_name=self._collection_name,
                document_id=doc_id,
                active_point_ids=active_point_ids,
            )
        except Exception as exc:
            # Stale cleanup failure is non-fatal to new points, but log warning
            logger.warning(
                "Stale point cleanup encountered an error for document %s: %s",
                doc_id,
                exc,
            )

        # 9. Set PostgreSQL status to 'indexed'
        await self._doc_repo.update_status(doc_id, "indexed")

        return IndexDocumentResponse(
            document_id=doc_id,
            status="indexed",
            chunks_indexed=len(chunks),
        )
