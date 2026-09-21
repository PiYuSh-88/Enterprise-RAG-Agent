"""
tests/unit/test_embedding_service.py
------------------------------------
Unit tests for embedding services (OpenAI and deterministic test implementation).
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from openai import RateLimitError

from app.services.embedding_service import (
    DeterministicTestEmbeddingService,
    OpenAIEmbeddingService,
)


@pytest.mark.asyncio
async def test_deterministic_embedder_dimension_and_repeatability():
    service = DeterministicTestEmbeddingService(dimensions=1536)
    texts = ["first chunk", "second chunk", "first chunk"]

    vectors = await service.embed_texts(texts)

    assert len(vectors) == 3
    assert len(vectors[0]) == 1536
    assert len(vectors[1]) == 1536

    # Repeatability
    assert vectors[0] == vectors[2]
    assert vectors[0] != vectors[1]


@pytest.mark.asyncio
async def test_deterministic_embedder_empty_list():
    service = DeterministicTestEmbeddingService(dimensions=1536)
    assert await service.embed_texts([]) == []


@pytest.mark.asyncio
async def test_openai_embedder_missing_api_key():
    service = OpenAIEmbeddingService(api_key="")
    with pytest.raises(RuntimeError, match="OpenAI API key is not configured"):
        await service.embed_texts(["hello world"])


@pytest.mark.asyncio
async def test_openai_embedder_batching_and_mock():
    service = OpenAIEmbeddingService(api_key="sk-test", batch_size=2, dimensions=1536)

    # Mock OpenAI client
    mock_client = AsyncMock()

    def fake_create(input, model, dimensions):
        mock_resp = MagicMock()
        mock_resp.data = [MagicMock(embedding=[0.1] * 1536) for _ in input]
        return mock_resp

    mock_client.embeddings.create.side_effect = fake_create
    service._client = mock_client

    texts = ["text1", "text2", "text3", "text4", "text5"]
    vectors = await service.embed_texts(texts)

    assert len(vectors) == 5
    assert all(len(v) == 1536 for v in vectors)
    # 5 items with batch_size=2 -> 3 calls
    assert mock_client.embeddings.create.call_count == 3


@pytest.mark.asyncio
async def test_openai_embedder_dimension_mismatch_raises():
    service = OpenAIEmbeddingService(api_key="sk-test", dimensions=1536)
    mock_client = AsyncMock()

    mock_resp = MagicMock()
    # Return wrong dimension (512 instead of 1536)
    mock_resp.data = [MagicMock(embedding=[0.1] * 512)]
    mock_client.embeddings.create.return_value = mock_resp
    service._client = mock_client

    with pytest.raises(ValueError, match="Expected vector dimension 1536"):
        await service.embed_texts(["text"])
