"""
tests/integration/test_vector_repository.py
-------------------------------------------
Integration tests for QdrantVectorRepository against a real Qdrant container.
"""

import uuid

import pytest
from qdrant_client import models

from app.ingestion.chunker import chunk_document
from app.services.embedding_service import DeterministicTestEmbeddingService


@pytest.mark.asyncio
async def test_qdrant_ping(vector_repo):
    assert await vector_repo.ping() is True


@pytest.mark.asyncio
async def test_ensure_collection_creates_and_is_idempotent(
    vector_repo, qdrant_client, clean_test_collection
):
    collection_name = clean_test_collection

    # Initial creation
    await vector_repo.ensure_collection(collection_name, vector_size=1536)
    assert await qdrant_client.collection_exists(collection_name) is True

    # Verify parameters
    info = await qdrant_client.get_collection(collection_name)
    assert info.config.params.vectors.size == 1536
    assert info.config.params.vectors.distance == models.Distance.COSINE

    # Second call should be safe and idempotent
    await vector_repo.ensure_collection(collection_name, vector_size=1536)
    assert await qdrant_client.collection_exists(collection_name) is True


@pytest.mark.asyncio
async def test_upsert_and_verify_payload_metadata(
    vector_repo, qdrant_client, clean_test_collection
):
    collection_name = clean_test_collection
    await vector_repo.ensure_collection(collection_name)

    doc_id = uuid.uuid4()
    text = "First paragraph text.\n\nSecond paragraph text."
    chunks = chunk_document(
        text=text,
        document_id=doc_id,
        filename="notes.pdf",
        file_type="pdf",
        chunk_size=50,
        chunk_overlap=10,
    )

    embedder = DeterministicTestEmbeddingService(dimensions=1536)
    vectors = await embedder.embed_texts([c.text for c in chunks])

    await vector_repo.upsert_chunks(collection_name, chunks, vectors)

    count = await vector_repo.count_by_document_id(collection_name, doc_id)
    assert count == len(chunks)

    # Scroll points and check minimal payload fields
    records, _ = await qdrant_client.scroll(
        collection_name=collection_name,
        scroll_filter=models.Filter(
            must=[
                models.FieldCondition(
                    key="document_id",
                    match=models.MatchValue(value=str(doc_id)),
                )
            ]
        ),
        with_payload=True,
    )

    assert len(records) == len(chunks)
    expected_keys = {
        "document_id",
        "chunk_index",
        "text",
        "char_start",
        "char_end",
        "char_count",
        "filename",
        "file_type",
    }

    for record in records:
        assert set(record.payload.keys()) == expected_keys
        assert record.payload["document_id"] == str(doc_id)
        assert record.payload["filename"] == "notes.pdf"
        assert record.payload["file_type"] == "pdf"


@pytest.mark.asyncio
async def test_reindex_and_delete_stale_chunks(
    vector_repo, qdrant_client, clean_test_collection
):
    collection_name = clean_test_collection
    await vector_repo.ensure_collection(collection_name)

    doc_id = uuid.uuid4()
    embedder = DeterministicTestEmbeddingService(dimensions=1536)

    # Initial indexing: 3 chunks
    text_long = "Paragraph 1 is here.\n\nParagraph 2 is here.\n\nParagraph 3 is here."
    chunks_v1 = chunk_document(
        text=text_long,
        document_id=doc_id,
        filename="doc.pdf",
        file_type="pdf",
        chunk_size=30,
        chunk_overlap=5,
    )
    assert len(chunks_v1) >= 3
    vectors_v1 = await embedder.embed_texts([c.text for c in chunks_v1])
    await vector_repo.upsert_chunks(collection_name, chunks_v1, vectors_v1)

    initial_count = await vector_repo.count_by_document_id(collection_name, doc_id)
    assert initial_count == len(chunks_v1)

    # Re-indexing with shorter text: fewer chunks (e.g. 1 chunk)
    text_short = "Only one short paragraph now."
    chunks_v2 = chunk_document(
        text=text_short,
        document_id=doc_id,
        filename="doc.pdf",
        file_type="pdf",
        chunk_size=500,
        chunk_overlap=50,
    )
    assert len(chunks_v2) == 1
    vectors_v2 = await embedder.embed_texts([c.text for c in chunks_v2])

    # 1. Upsert new points (overwrites chunk_index 0)
    await vector_repo.upsert_chunks(collection_name, chunks_v2, vectors_v2)

    # 2. Delete stale points
    active_ids = {c.point_id for c in chunks_v2}
    stale_deleted = await vector_repo.delete_stale_chunks(
        collection_name, doc_id, active_ids
    )
    assert stale_deleted == initial_count - len(chunks_v2)

    # Final count should match exactly the new chunk count (no duplicates or stale points)
    final_count = await vector_repo.count_by_document_id(collection_name, doc_id)
    assert final_count == len(chunks_v2)
