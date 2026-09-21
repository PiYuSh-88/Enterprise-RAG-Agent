"""
services/embedding_service.py
-----------------------------
Implementations of IEmbeddingService.

Production:
    OpenAIEmbeddingService calls OpenAI text-embedding-3-small (1536 dims)
    with batching and retries.

Testing:
    DeterministicTestEmbeddingService generates local, normalized 1536-dim
    vectors without network access or API keys.
"""

import asyncio
import logging
import math
import random
from typing import Sequence

import openai
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"
DEFAULT_EMBEDDING_DIMENSIONS = 1536
DEFAULT_BATCH_SIZE = 100


class OpenAIEmbeddingService:
    """
    Production embedding service backed by OpenAI's text-embedding-3-small model.

    Batches requests to stay within OpenAI limits and validates vector dimensions.
    """

    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_EMBEDDING_MODEL,
        dimensions: int = DEFAULT_EMBEDDING_DIMENSIONS,
        batch_size: int = DEFAULT_BATCH_SIZE,
        max_retries: int = 3,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._dimensions = dimensions
        self._batch_size = batch_size
        self._max_retries = max_retries
        self._client: AsyncOpenAI | None = None
        if api_key:
            self._client = AsyncOpenAI(api_key=api_key)

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """
        Generate embeddings for a list of texts in batches.
        """
        if not texts:
            return []

        if not self._client or not self._api_key:
            raise RuntimeError(
                "OpenAI API key is not configured. Set OPENAI_API_KEY to generate embeddings."
            )

        all_embeddings: list[list[float]] = []

        for i in range(0, len(texts), self._batch_size):
            batch = texts[i : i + self._batch_size]
            batch_vectors = await self._embed_batch_with_retry(batch)
            all_embeddings.extend(batch_vectors)

        return all_embeddings

    async def _embed_batch_with_retry(self, batch: Sequence[str]) -> list[list[float]]:
        assert self._client is not None
        delay = 1.0
        for attempt in range(self._max_retries):
            try:
                response = await self._client.embeddings.create(
                    input=list(batch),
                    model=self._model,
                    dimensions=self._dimensions,
                )
                vectors = [item.embedding for item in response.data]

                # Validate dimensions
                for v in vectors:
                    if len(v) != self._dimensions:
                        raise ValueError(
                            f"Expected vector dimension {self._dimensions}, "
                            f"but received {len(v)}."
                        )
                return vectors

            except (openai.RateLimitError, openai.APIConnectionError) as exc:
                if attempt == self._max_retries - 1:
                    logger.error("OpenAI embedding failed after retries: %s", exc)
                    raise
                logger.warning(
                    "OpenAI embedding attempt %d failed (%s). Retrying in %.1fs...",
                    attempt + 1,
                    exc,
                    delay,
                )
                await asyncio.sleep(delay)
                delay *= 2
            except Exception as exc:
                logger.error("Non-retryable OpenAI embedding error: %s", exc)
                raise

        raise RuntimeError("Failed to generate embeddings after max retries.")


class DeterministicTestEmbeddingService:
    """
    Deterministic, offline embedding service for testing.

    Produces normalized 1536-dimensional float vectors seeded by the text content,
    requiring zero network access, zero external dependencies, and zero API keys.
    """

    def __init__(self, dimensions: int = DEFAULT_EMBEDDING_DIMENSIONS) -> None:
        self._dimensions = dimensions

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        results: list[list[float]] = []
        for text in texts:
            rng = random.Random(text)
            raw = [rng.gauss(0, 1) for _ in range(self._dimensions)]
            norm = math.sqrt(sum(x * x for x in raw)) or 1.0
            results.append([x / norm for x in raw])

        return results
