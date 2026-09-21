"""
repositories/vector_repository.py
----------------------------------
Qdrant vector-store repository.

Architecture note (NOTES.md):
  Vector DB access is wrapped here and NEVER called directly from service
  or router layers.  Services depend on IVectorRepository (the Protocol),
  not this concrete class — so tests can inject a mock without touching Qdrant.

Milestone 0: only ping() is implemented.
Milestone 1+: add upsert_vectors(), search(), delete_by_document_id() etc.
"""

import logging

from qdrant_client import AsyncQdrantClient
from qdrant_client.http.exceptions import UnexpectedResponse

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

# NOTES.md: embedding dimensions MUST be 1536 (text-embedding-3-small).
# Any mismatch causes every Qdrant insert to fail.
EMBEDDING_DIMENSIONS = 1536


class QdrantVectorRepository:
    """
    Concrete implementation of IVectorRepository backed by Qdrant.

    The client is injected via __init__ rather than created internally so
    that tests can pass a mock without network access.
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
