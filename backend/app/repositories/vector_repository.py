"""
repositories/vector_repository.py
----------------------------------
Qdrant vector-store repository.

Architecture note (NOTES.md):
  Vector DB access is wrapped here and NEVER called directly from service
  or router layers. Services depend on IVectorRepository (the Protocol),
  not this concrete class — so tests can inject a mock without touching Qdrant.

Milestone 0: ping()
Milestone 2: ensure_collection(), upsert_chunks(), delete_stale_chunks(),
             delete_by_document_id(), count_by_document_id()
"""

import logging
import uuid

from qdrant_client import AsyncQdrantClient, models
from qdrant_client.http.exceptions import UnexpectedResponse

from app.core.config import Settings, get_settings
from app.schemas.chunk import DocumentChunk

logger = logging.getLogger(__name__)

# NOTES.md: embedding dimensions MUST be 1536 (text-embedding-3-small).
# Any mismatch causes every Qdrant insert to fail.
EMBEDDING_DIMENSIONS = 1536


class QdrantVectorRepository:
    """
    Concrete implementation of IVectorRepository backed by Qdrant.

    The client is injected via __init__ rather than created internally so
    that tests can pass a mock or test client without network access.
    """

    def __init__(self, client: AsyncQdrantClient) -> None:
        self._client = client

    async def ping(self) -> bool:
        """
        Return True if Qdrant is reachable.

        Uses get_collections() as the liveness probe — it is the lightest
        API call that requires a real network round-trip to Qdrant.
        Never raises; returns False on any error so the health endpoint
        can report degraded status instead of 500.
        """
        try:
            await self._client.get_collections()
            return True
        except (UnexpectedResponse, ConnectionError, OSError, Exception) as exc:
            logger.warning("Qdrant ping failed: %s", exc)
            return False

    async def ensure_collection(
        self, collection_name: str, vector_size: int = EMBEDDING_DIMENSIONS
    ) -> None:
        """
        Ensure the collection exists with the specified vector size and Cosine metric.
        Safely idempotent: creates only if collection does not exist.
        """
        exists = await self._client.collection_exists(collection_name=collection_name)
        if not exists:
            await self._client.create_collection(
                collection_name=collection_name,
                vectors_config=models.VectorParams(
                    size=vector_size,
                    distance=models.Distance.COSINE,
                ),
            )
            # Create payload index on document_id for fast filtering/scrolling
            await self._client.create_payload_index(
                collection_name=collection_name,
                field_name="document_id",
                field_schema=models.PayloadSchemaType.KEYWORD,
            )
            logger.info(
                "Created Qdrant collection '%s' (size=%d, distance=Cosine)",
                collection_name,
                vector_size,
            )

    async def upsert_chunks(
        self,
        collection_name: str,
        chunks: list[DocumentChunk],
        vectors: list[list[float]],
    ) -> None:
        """
        Store chunk vectors and minimal metadata in the specified collection.
        Uses deterministic point_ids to overwrite matching points on re-indexing.
        """
        if not chunks:
            return

        if len(chunks) != len(vectors):
            raise ValueError(
                f"Mismatch: {len(chunks)} chunks provided but {len(vectors)} vectors."
            )

        points = [
            models.PointStruct(
                id=str(chunk.point_id),
                vector=vector,
                payload={
                    "document_id": str(chunk.document_id),
                    "chunk_index": chunk.chunk_index,
                    "text": chunk.text,
                    "char_start": chunk.char_start,
                    "char_end": chunk.char_end,
                    "char_count": chunk.char_count,
                    "filename": chunk.filename,
                    "file_type": chunk.file_type,
                },
            )
            for chunk, vector in zip(chunks, vectors)
        ]

        await self._client.upsert(
            collection_name=collection_name,
            points=points,
            wait=True,
        )

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
        filter_ = models.Filter(
            must=[
                models.FieldCondition(
                    key="document_id",
                    match=models.MatchValue(value=str(document_id)),
                )
            ]
        )

        stale_point_ids: list[str] = []
        active_str_ids = {str(pid) for pid in active_point_ids}
        offset = None

        while True:
            records, next_offset = await self._client.scroll(
                collection_name=collection_name,
                scroll_filter=filter_,
                limit=100,
                with_payload=False,
                with_vectors=False,
                offset=offset,
            )
            for record in records:
                if str(record.id) not in active_str_ids:
                    stale_point_ids.append(str(record.id))

            if next_offset is None:
                break
            offset = next_offset

        if stale_point_ids:
            await self._client.delete(
                collection_name=collection_name,
                points_selector=models.PointIdsList(points=stale_point_ids),
                wait=True,
            )

        return len(stale_point_ids)

    async def delete_by_document_id(
        self, collection_name: str, document_id: uuid.UUID
    ) -> None:
        """
        Delete all points for a given document_id.
        """
        await self._client.delete(
            collection_name=collection_name,
            points_selector=models.FilterSelector(
                filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="document_id",
                            match=models.MatchValue(value=str(document_id)),
                        )
                    ]
                )
            ),
            wait=True,
        )

    async def count_by_document_id(
        self, collection_name: str, document_id: uuid.UUID
    ) -> int:
        """
        Count the number of points belonging to document_id in the collection.
        """
        res = await self._client.count(
            collection_name=collection_name,
            count_filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="document_id",
                        match=models.MatchValue(value=str(document_id)),
                    )
                ]
            ),
            exact=True,
        )
        return res.count


def build_qdrant_client(settings: Settings | None = None) -> AsyncQdrantClient:
    """
    Factory that builds an AsyncQdrantClient from application settings.

    Kept separate from the repository class so main.py can call it during
    lifespan setup without importing the repository directly.
    """
    s = settings or get_settings()
    return AsyncQdrantClient(
        host=s.qdrant_host,
        port=s.qdrant_port,
        api_key=s.qdrant_api_key or None,  # None means no auth (local dev)
    )
