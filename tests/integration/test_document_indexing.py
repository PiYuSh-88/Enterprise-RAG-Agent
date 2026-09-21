"""
tests/integration/test_document_indexing.py
-------------------------------------------
End-to-end integration tests for document chunking, embedding, and vector persistence.

Tests execute against:
  - Real PostgreSQL instance (isolated smartpark_test database)
  - Real Qdrant container (rag_documents_test collection)
  - Deterministic offline embedding service (no OpenAI API calls required)
"""

import uuid

import pytest
from httpx import AsyncClient
from qdrant_client import AsyncQdrantClient, models
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document
from app.repositories.document_repository import DocumentRepository
from app.routers.documents import get_embedding_service
from app.schemas.document import DocumentCreate
from app.services.interfaces import IEmbeddingService


class FailingEmbeddingService:
    """Mock embedding service that always raises an error to test failure handling."""

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        raise RuntimeError("OpenAI rate limit / API outage simulated")


@pytest.mark.asyncio
async def test_end_to_end_indexing_flow(
    indexing_integration_client: AsyncClient,
    test_session_factory,
    qdrant_client: AsyncQdrantClient,
    clean_test_collection: str,
):
    """
    Complete flow:
      1. Seed an extracted document in isolated PostgreSQL.
      2. Call POST /documents/{id}/index.
      3. Assert HTTP 200, status='indexed', chunks_indexed > 0.
      4. Assert document in DB has status='indexed'.
      5. Assert vectors and minimal payload stored in Qdrant.
    """
    collection_name = clean_test_collection

    # 1. Seed document in PostgreSQL
    doc_id = uuid.uuid4()
    async with test_session_factory() as session:
        doc = Document(
            id=doc_id,
            filename="user_manual.pdf",
            file_type="pdf",
            file_size_bytes=10240,
            char_count=1200,
            extracted_text=(
                "Section 1: Introduction to SmartPark.\n\n"
                "SmartPark is an enterprise RAG system with agentic reasoning.\n\n"
                "Section 2: Architecture and Design.\n\n"
                "It follows a strict 4-layer architecture: Router -> Service -> Repository -> DB."
            ),
            status="extracted",
        )
        session.add(doc)
        await session.commit()

    # 2. Trigger indexing
    response = await indexing_integration_client.post(f"/documents/{doc_id}/index")
    assert response.status_code == 200
    data = response.json()
    assert data["document_id"] == str(doc_id)
    assert data["status"] == "indexed"
    assert data["chunks_indexed"] >= 1

    chunks_count = data["chunks_indexed"]

    # 3. Verify PostgreSQL status
    async with test_session_factory() as session:
        result = await session.execute(select(Document).where(Document.id == doc_id))
        stored_doc = result.scalar_one_or_none()
        assert stored_doc is not None
        assert stored_doc.status == "indexed"

    # 4. Verify Qdrant points and payloads
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
        with_vectors=True,
    )

    assert len(records) == chunks_count
    for record in records:
        assert len(record.vector) == 1536
        payload = record.payload
        assert payload["document_id"] == str(doc_id)
        assert payload["filename"] == "user_manual.pdf"
        assert payload["file_type"] == "pdf"
        assert payload["char_count"] == len(payload["text"])
        assert "Section" in payload["text"] or "SmartPark" in payload["text"]


@pytest.mark.asyncio
async def test_reindexing_same_document_is_idempotent_no_duplicates(
    indexing_integration_client: AsyncClient,
    test_session_factory,
    qdrant_client: AsyncQdrantClient,
    clean_test_collection: str,
):
    """
    Re-indexing an already-indexed document overwrites points with deterministic IDs
    and does not produce duplicate points.
    """
    collection_name = clean_test_collection
    doc_id = uuid.uuid4()

    async with test_session_factory() as session:
        doc = Document(
            id=doc_id,
            filename="policy.docx",
            file_type="docx",
            file_size_bytes=2048,
            char_count=150,
            extracted_text="Company travel policy rules and guidelines for reimbursement.",
            status="extracted",
        )
        session.add(doc)
        await session.commit()

    # First indexing
    resp1 = await indexing_integration_client.post(f"/documents/{doc_id}/index")
    assert resp1.status_code == 200
    chunks1 = resp1.json()["chunks_indexed"]

    count1 = await qdrant_client.count(
        collection_name=collection_name,
        count_filter=models.Filter(
            must=[
                models.FieldCondition(
                    key="document_id",
                    match=models.MatchValue(value=str(doc_id)),
                )
            ]
        ),
        exact=True,
    )
    assert count1.count == chunks1

    # Second indexing (re-index)
    resp2 = await indexing_integration_client.post(f"/documents/{doc_id}/index")
    assert resp2.status_code == 200
    chunks2 = resp2.json()["chunks_indexed"]
    assert chunks2 == chunks1

    count2 = await qdrant_client.count(
        collection_name=collection_name,
        count_filter=models.Filter(
            must=[
                models.FieldCondition(
                    key="document_id",
                    match=models.MatchValue(value=str(doc_id)),
                )
            ]
        ),
        exact=True,
    )
    # Count must remain exactly the same (no duplicates)
    assert count2.count == chunks1


@pytest.mark.asyncio
async def test_index_nonexistent_document_returns_404(
    indexing_integration_client: AsyncClient,
):
    missing_id = uuid.uuid4()
    response = await indexing_integration_client.post(f"/documents/{missing_id}/index")
    assert response.status_code == 404
    assert response.json()["detail"] == "Document not found."


@pytest.mark.asyncio
async def test_index_empty_extracted_text_returns_422(
    indexing_integration_client: AsyncClient,
    test_session_factory,
):
    doc_id = uuid.uuid4()
    async with test_session_factory() as session:
        doc = Document(
            id=doc_id,
            filename="empty.pdf",
            file_type="pdf",
            file_size_bytes=100,
            char_count=0,
            extracted_text="",
            status="extracted",
        )
        session.add(doc)
        await session.commit()

    response = await indexing_integration_client.post(f"/documents/{doc_id}/index")
    assert response.status_code == 422
    assert "no extracted text" in response.json()["detail"]


@pytest.mark.asyncio
async def test_failed_embedding_preserves_existing_vectors_and_sets_status_error(
    indexing_integration_client: AsyncClient,
    test_session_factory,
    qdrant_client: AsyncQdrantClient,
    clean_test_collection: str,
):
    """
    If embedding fails during re-indexing:
      - Document status in PostgreSQL transitions to 'error'
      - Previously indexed vectors in Qdrant are preserved
    """
    collection_name = clean_test_collection
    doc_id = uuid.uuid4()

    async with test_session_factory() as session:
        doc = Document(
            id=doc_id,
            filename="handbook.pdf",
            file_type="pdf",
            file_size_bytes=5000,
            char_count=300,
            extracted_text="Employee handbook standard procedures.",
            status="extracted",
        )
        session.add(doc)
        await session.commit()

    # Initial successful index
    resp1 = await indexing_integration_client.post(f"/documents/{doc_id}/index")
    assert resp1.status_code == 200

    count_before = await qdrant_client.count(
        collection_name=collection_name,
        count_filter=models.Filter(
            must=[
                models.FieldCondition(
                    key="document_id",
                    match=models.MatchValue(value=str(doc_id)),
                )
            ]
        ),
        exact=True,
    )
    assert count_before.count > 0

    # Override embedding service to fail on subsequent call
    app = indexing_integration_client._transport.app  # type: ignore
    app.dependency_overrides[get_embedding_service] = lambda: FailingEmbeddingService()

    # Second index attempt -> should fail with 502
    resp2 = await indexing_integration_client.post(f"/documents/{doc_id}/index")
    assert resp2.status_code == 502
    assert "Embedding generation failed" in resp2.json()["detail"]

    # PostgreSQL status must be 'error'
    async with test_session_factory() as session:
        result = await session.execute(select(Document).where(Document.id == doc_id))
        stored_doc = result.scalar_one_or_none()
        assert stored_doc is not None
        assert stored_doc.status == "error"

    # Previously indexed vectors in Qdrant must still be preserved
    count_after = await qdrant_client.count(
        collection_name=collection_name,
        count_filter=models.Filter(
            must=[
                models.FieldCondition(
                    key="document_id",
                    match=models.MatchValue(value=str(doc_id)),
                )
            ]
        ),
        exact=True,
    )
    assert count_after.count == count_before.count
