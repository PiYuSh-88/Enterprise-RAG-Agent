"""
tests/unit/test_indexing_service.py
-----------------------------------
Unit tests for IndexingService orchestration using mocks.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.models.document import Document
from app.services.indexing_service import IndexingService


@pytest.fixture
def mock_doc_repo():
    return AsyncMock()


@pytest.fixture
def mock_vector_repo():
    repo = AsyncMock()
    repo.ensure_collection = AsyncMock()
    repo.upsert_chunks = AsyncMock()
    repo.delete_stale_chunks = AsyncMock(return_value=0)
    return repo


@pytest.fixture
def mock_embedding_service():
    service = AsyncMock()
    # Return dummy 1536-dim vector per input text
    service.embed_texts = AsyncMock(
        side_effect=lambda texts: [[0.01] * 1536 for _ in texts]
    )
    return service


@pytest.fixture
def indexing_service(mock_doc_repo, mock_vector_repo, mock_embedding_service):
    return IndexingService(
        doc_repo=mock_doc_repo,
        vector_repo=mock_vector_repo,
        embedding_service=mock_embedding_service,
        collection_name="test_collection",
        chunk_size=500,
        chunk_overlap=50,
    )


@pytest.mark.asyncio
async def test_index_nonexistent_document_raises_404(indexing_service, mock_doc_repo):
    mock_doc_repo.get_by_id.return_value = None
    doc_id = uuid.uuid4()

    with pytest.raises(HTTPException) as exc_info:
        await indexing_service.index_document(doc_id)

    assert exc_info.value.status_code == 404
    assert "Document not found" in exc_info.value.detail


@pytest.mark.asyncio
async def test_index_empty_extracted_text_raises_422(indexing_service, mock_doc_repo):
    doc_id = uuid.uuid4()
    mock_doc = MagicMock(spec=Document)
    mock_doc.id = doc_id
    mock_doc.extracted_text = "   "
    mock_doc_repo.get_by_id.return_value = mock_doc

    with pytest.raises(HTTPException) as exc_info:
        await indexing_service.index_document(doc_id)

    assert exc_info.value.status_code == 422
    assert "no extracted text" in exc_info.value.detail


@pytest.mark.asyncio
async def test_index_document_success(
    indexing_service, mock_doc_repo, mock_vector_repo, mock_embedding_service
):
    doc_id = uuid.uuid4()
    mock_doc = MagicMock(spec=Document)
    mock_doc.id = doc_id
    mock_doc.filename = "report.pdf"
    mock_doc.file_type = "pdf"
    mock_doc.extracted_text = "This is a comprehensive test document with enough text to index."
    mock_doc_repo.get_by_id.return_value = mock_doc

    resp = await indexing_service.index_document(doc_id)

    assert resp.document_id == doc_id
    assert resp.status == "indexed"
    assert resp.chunks_indexed == 1

    # Verify status progression
    assert mock_doc_repo.update_status.call_args_list[0].args == (doc_id, "indexing")
    assert mock_doc_repo.update_status.call_args_list[1].args == (doc_id, "indexed")

    # Verify vector repo called
    mock_vector_repo.ensure_collection.assert_awaited_once_with("test_collection")
    mock_vector_repo.upsert_chunks.assert_awaited_once()
    mock_vector_repo.delete_stale_chunks.assert_awaited_once()


@pytest.mark.asyncio
async def test_index_document_embedding_failure_sets_status_error(
    indexing_service, mock_doc_repo, mock_embedding_service
):
    doc_id = uuid.uuid4()
    mock_doc = MagicMock(spec=Document)
    mock_doc.id = doc_id
    mock_doc.filename = "test.docx"
    mock_doc.file_type = "docx"
    mock_doc.extracted_text = "Some extracted text content."
    mock_doc_repo.get_by_id.return_value = mock_doc

    mock_embedding_service.embed_texts.side_effect = RuntimeError("OpenAI rate limit exceeded")

    with pytest.raises(HTTPException) as exc_info:
        await indexing_service.index_document(doc_id)

    assert exc_info.value.status_code == 502
    assert "Embedding generation failed" in exc_info.value.detail

    # Document status must be updated to 'error'
    mock_doc_repo.update_status.assert_any_await(doc_id, "error")


@pytest.mark.asyncio
async def test_index_document_upsert_failure_sets_status_error(
    indexing_service, mock_doc_repo, mock_vector_repo
):
    doc_id = uuid.uuid4()
    mock_doc = MagicMock(spec=Document)
    mock_doc.id = doc_id
    mock_doc.filename = "test.pdf"
    mock_doc.file_type = "pdf"
    mock_doc.extracted_text = "Some extracted text content."
    mock_doc_repo.get_by_id.return_value = mock_doc

    mock_vector_repo.upsert_chunks.side_effect = ConnectionError("Qdrant connection dropped")

    with pytest.raises(HTTPException) as exc_info:
        await indexing_service.index_document(doc_id)

    assert exc_info.value.status_code == 502
    assert "Vector storage failed" in exc_info.value.detail

    # Document status must be updated to 'error'
    mock_doc_repo.update_status.assert_any_await(doc_id, "error")
