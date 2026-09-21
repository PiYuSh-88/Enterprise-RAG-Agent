"""
services/interfaces.py
----------------------
Protocol (interface) definitions for all service and repository dependencies.

Why Protocols instead of ABCs?
  FastAPI's Depends() wires concrete implementations at runtime.
  Protocols allow test code to inject plain mock objects without inheriting
  from anything — as long as the mock has the right method signatures,
  isinstance checks pass and mypy is satisfied.

Rule (NOTES.md): services are wired against these interfaces, not concrete
classes.  This is what makes the test suite mockable without hitting real APIs.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from app.models.document import Document
    from app.schemas.chunk import DocumentChunk
    from app.schemas.document import DocumentCreate


@runtime_checkable
class IVectorRepository(Protocol):
    """
    Interface for vector-store repositories (Qdrant).

    Milestone 0: ping()
    Milestone 2: ensure_collection(), upsert_chunks(), delete_stale_chunks(), count_by_document_id()
    """

    async def ping(self) -> bool:
        """
        Return True if the vector store is reachable, False otherwise.
        Must never raise — swallow exceptions and return False.
        """
        ...

    async def ensure_collection(
        self, collection_name: str, vector_size: int = 1536
    ) -> None:
        """
        Ensure the collection exists with the specified vector size and Cosine metric.
        Must be safely idempotent.
        """
        ...

    async def upsert_chunks(
        self,
        collection_name: str,
        chunks: list[DocumentChunk],
        vectors: list[list[float]],
    ) -> None:
        """
        Store chunk vectors and minimal metadata in the specified collection.
        """
        ...

    async def delete_stale_chunks(
        self,
        collection_name: str,
        document_id: uuid.UUID,
        active_point_ids: set[uuid.UUID],
    ) -> int:
        """
        Remove points for document_id whose point IDs are not in active_point_ids.
        Returns the count of deleted stale points.
        """
        ...

    async def delete_by_document_id(
        self, collection_name: str, document_id: uuid.UUID
    ) -> None:
        """
        Delete all points for a given document_id.
        """
        ...

    async def count_by_document_id(
        self, collection_name: str, document_id: uuid.UUID
    ) -> int:
        """
        Count the number of points belonging to document_id in the collection.
        """
        ...


@runtime_checkable
class IDocumentRepository(Protocol):
    """
    Interface for the document metadata repository (PostgreSQL).

    Milestone 1: create() and get_by_id().
    Milestone 2: update_status().
    """

    async def create(self, data: DocumentCreate) -> Document:
        """
        Persist a new document record and return the ORM instance.
        Must flush so the returned object has a populated id.
        """
        ...

    async def get_by_id(self, doc_id: uuid.UUID) -> Document | None:
        """
        Fetch a document by primary key.
        Returns None if not found; never raises on missing row.
        """
        ...

    async def update_status(self, doc_id: uuid.UUID, status: str) -> Document | None:
        """
        Update the status of a document and return the updated instance.
        Returns None if document does not exist.
        """
        ...


@runtime_checkable
class IEmbeddingService(Protocol):
    """
    Interface for embedding generators.

    Production uses OpenAI text-embedding-3-small (1536 dimensions).
    Tests use mocks or deterministic local generators without external API calls.
    """

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """
        Generate embedding vectors for a list of text strings.
        Must return a list of vectors with the expected dimension (1536).
        """
        ...

