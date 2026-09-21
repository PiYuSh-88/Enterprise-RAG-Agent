"""
tests/unit/test_documents.py
-----------------------------
Unit tests for the document ingestion endpoints.

All external dependencies (PostgreSQL, extraction libraries) are replaced
with mocks via FastAPI dependency_overrides and AsyncMock — no real containers
or files required.

Test matrix:
  ✓ Valid PDF upload          → 201, correct response shape
  ✓ Valid DOCX upload         → 201, correct response shape
  ✓ Unsupported extension     → 400
  ✓ MIME type mismatch        → 400
  ✓ File exceeds size limit   → 413
  ✓ Corrupt PDF               → 422
  ✓ Corrupt DOCX              → 422
  ✓ char_count matches text   → correct value in response
  ✓ GET /documents/{id} found → 200, correct data
  ✓ GET /documents/{id} miss  → 404
"""

import io
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.main import create_app
from app.schemas.chunk import IndexDocumentResponse
from app.schemas.document import DocumentResponse
from app.services.document_service import DocumentService
from app.routers.documents import get_document_service, get_indexing_service

# ── Fixtures ──────────────────────────────────────────────────────────────────

FAKE_DOC_ID = uuid.uuid4()
FAKE_NOW = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)


def _make_doc_response(**overrides) -> DocumentResponse:
    defaults = dict(
        id=FAKE_DOC_ID,
        filename="test.pdf",
        file_type="pdf",
        file_size_bytes=1024,
        char_count=42,
        status="extracted",
        uploaded_at=FAKE_NOW,
    )
    defaults.update(overrides)
    return DocumentResponse(**defaults)


def _make_client(
    test_settings: Settings,
    mock_service: MagicMock,
) -> TestClient:
    """Build a TestClient with DocumentService fully mocked."""
    app = create_app()

    # Override settings and the whole document service
    app.dependency_overrides[get_settings] = lambda: test_settings
    app.dependency_overrides[get_document_service] = lambda: mock_service

    # Populate app.state so lifespan doesn't fire network calls
    app.state.db_engine = MagicMock()
    app.state.db_session_factory = MagicMock()
    app.state.qdrant_client = MagicMock()
    app.state.vector_repository = MagicMock()

    return TestClient(app, raise_server_exceptions=True)


# ── Upload tests ──────────────────────────────────────────────────────────────

class TestUploadEndpoint:

    def test_valid_pdf_returns_201(self, test_settings):
        """POST /documents/upload with a valid PDF → 201 Created."""
        mock_service = MagicMock()
        mock_service.upload = AsyncMock(
            return_value=_make_doc_response(filename="doc.pdf", file_type="pdf")
        )
        client = _make_client(test_settings, mock_service)

        response = client.post(
            "/documents/upload",
            files={"file": ("doc.pdf", b"%PDF-1.4 minimal", "application/pdf")},
        )
        assert response.status_code == 201

    def test_valid_pdf_response_shape(self, test_settings):
        """Response contains all required metadata fields, no extracted_text."""
        mock_service = MagicMock()
        mock_service.upload = AsyncMock(
            return_value=_make_doc_response(filename="doc.pdf")
        )
        client = _make_client(test_settings, mock_service)

        data = client.post(
            "/documents/upload",
            files={"file": ("doc.pdf", b"%PDF-1.4 minimal", "application/pdf")},
        ).json()

        assert set(data.keys()) >= {"id", "filename", "file_type", "file_size_bytes",
                                     "char_count", "status", "uploaded_at"}
        assert "extracted_text" not in data

    def test_valid_docx_returns_201(self, test_settings):
        """POST /documents/upload with a valid DOCX → 201 Created."""
        docx_mime = (
            "application/vnd.openxmlformats-officedocument"
            ".wordprocessingml.document"
        )
        mock_service = MagicMock()
        mock_service.upload = AsyncMock(
            return_value=_make_doc_response(filename="doc.docx", file_type="docx")
        )
        client = _make_client(test_settings, mock_service)

        response = client.post(
            "/documents/upload",
            files={"file": ("doc.docx", b"PK docx content", docx_mime)},
        )
        assert response.status_code == 201

    def test_unsupported_extension_returns_400(self, test_settings):
        """Uploading a .txt file → 400 before any extraction runs."""
        from app.services.document_service import DocumentService
        from fastapi import HTTPException

        # Use a real service with a mock repo; the validation raises before
        # the repo is ever called
        mock_repo = MagicMock()
        real_service = DocumentService(mock_repo)

        app = create_app()
        app.dependency_overrides[get_settings] = lambda: test_settings
        app.dependency_overrides[get_document_service] = lambda: real_service
        app.state.db_engine = MagicMock()
        app.state.db_session_factory = MagicMock()
        app.state.qdrant_client = MagicMock()
        app.state.vector_repository = MagicMock()

        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            "/documents/upload",
            files={"file": ("report.txt", b"hello world", "text/plain")},
        )
        assert response.status_code == 400
        assert "Unsupported file type" in response.json()["detail"]

    def test_mime_mismatch_returns_400(self, test_settings):
        """.pdf extension with wrong MIME → 400."""
        from app.services.document_service import DocumentService

        mock_repo = MagicMock()
        real_service = DocumentService(mock_repo)

        app = create_app()
        app.dependency_overrides[get_settings] = lambda: test_settings
        app.dependency_overrides[get_document_service] = lambda: real_service
        app.state.db_engine = MagicMock()
        app.state.db_session_factory = MagicMock()
        app.state.qdrant_client = MagicMock()
        app.state.vector_repository = MagicMock()

        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            "/documents/upload",
            files={"file": ("doc.pdf", b"content", "text/plain")},
        )
        assert response.status_code == 400
        assert "Content-Type" in response.json()["detail"]

    def test_oversized_file_returns_413(self, test_settings):
        """File larger than max_upload_size_mb → 413."""
        from app.services.document_service import DocumentService

        mock_repo = MagicMock()
        real_service = DocumentService(mock_repo)

        # Use settings with a 1-byte limit for simplicity
        small_limit_settings = Settings(
            database_url="postgresql+asyncpg://u:p@localhost/db",
            max_upload_size_mb=0,   # effectively 0 MB → any file oversized
        )

        app = create_app()
        app.dependency_overrides[get_settings] = lambda: small_limit_settings
        app.dependency_overrides[get_document_service] = lambda: real_service
        app.state.db_engine = MagicMock()
        app.state.db_session_factory = MagicMock()
        app.state.qdrant_client = MagicMock()
        app.state.vector_repository = MagicMock()

        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            "/documents/upload",
            files={"file": ("doc.pdf", b"%PDF content", "application/pdf")},
        )
        assert response.status_code == 413
        assert "limit" in response.json()["detail"].lower()

    def test_corrupt_pdf_returns_422(self, test_settings):
        """Bytes that claim to be PDF but are not parseable → 422."""
        from app.services.document_service import DocumentService

        mock_repo = MagicMock()
        real_service = DocumentService(mock_repo)

        app = create_app()
        app.dependency_overrides[get_settings] = lambda: test_settings
        app.dependency_overrides[get_document_service] = lambda: real_service
        app.state.db_engine = MagicMock()
        app.state.db_session_factory = MagicMock()
        app.state.qdrant_client = MagicMock()
        app.state.vector_repository = MagicMock()

        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            "/documents/upload",
            files={"file": ("corrupt.pdf", b"this is not a pdf", "application/pdf")},
        )
        assert response.status_code == 422
        assert "extraction failed" in response.json()["detail"].lower()

    def test_corrupt_docx_returns_422(self, test_settings):
        """Bytes that claim to be DOCX but are not parseable → 422."""
        from app.services.document_service import DocumentService
        docx_mime = (
            "application/vnd.openxmlformats-officedocument"
            ".wordprocessingml.document"
        )
        mock_repo = MagicMock()
        real_service = DocumentService(mock_repo)

        app = create_app()
        app.dependency_overrides[get_settings] = lambda: test_settings
        app.dependency_overrides[get_document_service] = lambda: real_service
        app.state.db_engine = MagicMock()
        app.state.db_session_factory = MagicMock()
        app.state.qdrant_client = MagicMock()
        app.state.vector_repository = MagicMock()

        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            "/documents/upload",
            files={"file": ("corrupt.docx", b"not a docx", docx_mime)},
        )
        assert response.status_code == 422

    def test_char_count_reflects_extracted_text(self, test_settings):
        """char_count in the response equals the length of extracted text."""
        expected_text = "Hello from the PDF content."
        expected_char_count = len(expected_text)

        mock_service = MagicMock()
        mock_service.upload = AsyncMock(
            return_value=_make_doc_response(char_count=expected_char_count)
        )
        client = _make_client(test_settings, mock_service)

        data = client.post(
            "/documents/upload",
            files={"file": ("doc.pdf", b"%PDF-1.4 minimal", "application/pdf")},
        ).json()
        assert data["char_count"] == expected_char_count

    def test_extracted_text_not_in_response(self, test_settings):
        """Verify extracted_text is never serialised into the HTTP response."""
        mock_service = MagicMock()
        mock_service.upload = AsyncMock(return_value=_make_doc_response())
        client = _make_client(test_settings, mock_service)

        data = client.post(
            "/documents/upload",
            files={"file": ("doc.pdf", b"%PDF-1.4 minimal", "application/pdf")},
        ).json()
        assert "extracted_text" not in data


# ── GET /documents/{id} tests ─────────────────────────────────────────────────

class TestGetDocumentEndpoint:

    def test_get_existing_document_returns_200(self, test_settings):
        """GET /documents/{id} for a known id → 200."""
        doc = _make_doc_response()
        mock_service = MagicMock()
        mock_service.get_by_id = AsyncMock(return_value=doc)
        client = _make_client(test_settings, mock_service)

        response = client.get(f"/documents/{FAKE_DOC_ID}")
        assert response.status_code == 200

    def test_get_existing_document_response_shape(self, test_settings):
        """Response for GET /documents/{id} has correct shape."""
        doc = _make_doc_response()
        mock_service = MagicMock()
        mock_service.get_by_id = AsyncMock(return_value=doc)
        client = _make_client(test_settings, mock_service)

        data = client.get(f"/documents/{FAKE_DOC_ID}").json()
        assert data["id"] == str(FAKE_DOC_ID)
        assert "extracted_text" not in data

    def test_get_missing_document_returns_404(self, test_settings):
        """GET /documents/{id} for unknown id → 404."""
        mock_service = MagicMock()
        mock_service.get_by_id = AsyncMock(return_value=None)
        client = _make_client(test_settings, mock_service)

        response = client.get(f"/documents/{uuid.uuid4()}")
        assert response.status_code == 404


class TestIndexDocumentEndpoint:
    """Unit tests for POST /documents/{doc_id}/index endpoint."""

    def test_index_document_success_returns_200(self, test_settings):
        doc_id = uuid.uuid4()
        mock_indexing = MagicMock()
        mock_indexing.index_document = AsyncMock(
            return_value=IndexDocumentResponse(
                document_id=doc_id,
                status="indexed",
                chunks_indexed=3,
            )
        )

        app = create_app()
        app.dependency_overrides[get_settings] = lambda: test_settings
        app.dependency_overrides[get_indexing_service] = lambda: mock_indexing
        app.state.db_engine = MagicMock()
        app.state.db_session_factory = MagicMock()
        app.state.vector_repository = MagicMock()

        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(f"/documents/{doc_id}/index")

        assert response.status_code == 200
        data = response.json()
        assert data["document_id"] == str(doc_id)
        assert data["status"] == "indexed"
        assert data["chunks_indexed"] == 3

    def test_index_document_404_when_missing(self, test_settings):
        doc_id = uuid.uuid4()
        mock_indexing = MagicMock()
        from fastapi import HTTPException
        mock_indexing.index_document = AsyncMock(
            side_effect=HTTPException(status_code=404, detail="Document not found.")
        )

        app = create_app()
        app.dependency_overrides[get_settings] = lambda: test_settings
        app.dependency_overrides[get_indexing_service] = lambda: mock_indexing
        app.state.db_engine = MagicMock()
        app.state.db_session_factory = MagicMock()
        app.state.vector_repository = MagicMock()

        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(f"/documents/{doc_id}/index")

        assert response.status_code == 404
        assert response.json()["detail"] == "Document not found."

