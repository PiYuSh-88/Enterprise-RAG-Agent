"""
tests/integration/test_document_upload.py
------------------------------------------
Integration tests for the document upload → validate → extract flow.

These tests run against a real PostgreSQL instance (the isolated
`smartpark_test` database created in conftest.py).  No mocks are used
for the database layer — real SQL is executed.

Requirements:
  docker compose up -d must be running before these tests execute.

Run:
  pytest tests/integration/ -v
"""

import uuid

import pytest
from httpx import AsyncClient

# ── Helpers ───────────────────────────────────────────────────────────────────

PDF_MIME = "application/pdf"
DOCX_MIME = (
    "application/vnd.openxmlformats-officedocument"
    ".wordprocessingml.document"
)


# ── Upload tests ──────────────────────────────────────────────────────────────


class TestDocumentUploadIntegration:

    @pytest.mark.asyncio
    async def test_valid_pdf_upload_returns_201(
        self,
        integration_client: AsyncClient,
        sample_pdf_bytes: bytes,
    ):
        """Real PDF → 201 Created with correct metadata."""
        response = await integration_client.post(
            "/documents/upload",
            files={"file": ("sample.pdf", sample_pdf_bytes, PDF_MIME)},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["filename"] == "sample.pdf"
        assert data["file_type"] == "pdf"
        assert data["file_size_bytes"] == len(sample_pdf_bytes)
        assert data["status"] == "extracted"
        assert "id" in data
        assert "uploaded_at" in data
        assert "extracted_text" not in data

    @pytest.mark.asyncio
    async def test_valid_docx_upload_returns_201(
        self,
        integration_client: AsyncClient,
        sample_docx_bytes: bytes,
    ):
        """Real DOCX → 201 Created with extracted text character count."""
        response = await integration_client.post(
            "/documents/upload",
            files={"file": ("sample.docx", sample_docx_bytes, DOCX_MIME)},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["filename"] == "sample.docx"
        assert data["file_type"] == "docx"
        assert data["char_count"] > 0          # DOCX has text content
        assert "extracted_text" not in data

    @pytest.mark.asyncio
    async def test_pdf_char_count_is_integer(
        self,
        integration_client: AsyncClient,
        sample_pdf_bytes: bytes,
    ):
        """char_count is an integer (0 for blank PDF — no text layer)."""
        response = await integration_client.post(
            "/documents/upload",
            files={"file": ("blank.pdf", sample_pdf_bytes, PDF_MIME)},
        )
        assert response.status_code == 201
        assert isinstance(response.json()["char_count"], int)

    @pytest.mark.asyncio
    async def test_uploaded_document_persisted_in_db(
        self,
        integration_client: AsyncClient,
        sample_docx_bytes: bytes,
    ):
        """
        Verify the document row actually exists in Postgres after upload.
        Fetches via GET /documents/{id} — not by querying the DB directly
        so the test stays at the API boundary.
        """
        upload_resp = await integration_client.post(
            "/documents/upload",
            files={"file": ("persist_test.docx", sample_docx_bytes, DOCX_MIME)},
        )
        assert upload_resp.status_code == 201
        doc_id = upload_resp.json()["id"]

        get_resp = await integration_client.get(f"/documents/{doc_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["id"] == doc_id
        assert get_resp.json()["filename"] == "persist_test.docx"

    @pytest.mark.asyncio
    async def test_unsupported_file_type_returns_400(
        self,
        integration_client: AsyncClient,
    ):
        """Uploading .txt → 400, no DB row created."""
        response = await integration_client.post(
            "/documents/upload",
            files={"file": ("notes.txt", b"some text", "text/plain")},
        )
        assert response.status_code == 400
        assert "Unsupported file type" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_oversized_file_returns_413(
        self,
        integration_client: AsyncClient,
        oversized_pdf_bytes: bytes,
    ):
        """File > 50 MB → 413, no DB row created."""
        response = await integration_client.post(
            "/documents/upload",
            files={"file": ("big.pdf", oversized_pdf_bytes, PDF_MIME)},
        )
        assert response.status_code == 413
        assert "limit" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_corrupt_pdf_returns_422(
        self,
        integration_client: AsyncClient,
        corrupt_pdf_bytes: bytes,
    ):
        """Bytes that cannot be parsed as PDF → 422, no DB row."""
        response = await integration_client.post(
            "/documents/upload",
            files={"file": ("corrupt.pdf", corrupt_pdf_bytes, PDF_MIME)},
        )
        assert response.status_code == 422
        assert "extraction failed" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_corrupt_docx_returns_422(
        self,
        integration_client: AsyncClient,
        corrupt_docx_bytes: bytes,
    ):
        """Bytes that cannot be parsed as DOCX → 422, no DB row."""
        response = await integration_client.post(
            "/documents/upload",
            files={"file": ("corrupt.docx", corrupt_docx_bytes, DOCX_MIME)},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_path_traversal_filename_sanitised(
        self,
        integration_client: AsyncClient,
        sample_pdf_bytes: bytes,
    ):
        """Path traversal in filename → stored filename is safe (basename only)."""
        response = await integration_client.post(
            "/documents/upload",
            files={"file": ("../../etc/passwd.pdf", sample_pdf_bytes, PDF_MIME)},
        )
        assert response.status_code == 201
        assert response.json()["filename"] == "passwd.pdf"


# ── GET endpoint tests ────────────────────────────────────────────────────────


class TestGetDocumentIntegration:

    @pytest.mark.asyncio
    async def test_get_existing_document(
        self,
        integration_client: AsyncClient,
        sample_docx_bytes: bytes,
    ):
        """Upload then GET → returns same metadata."""
        upload = await integration_client.post(
            "/documents/upload",
            files={"file": ("get_test.docx", sample_docx_bytes, DOCX_MIME)},
        )
        doc_id = upload.json()["id"]

        get = await integration_client.get(f"/documents/{doc_id}")
        assert get.status_code == 200
        assert get.json()["id"] == doc_id
        assert "extracted_text" not in get.json()

    @pytest.mark.asyncio
    async def test_get_nonexistent_document_returns_404(
        self,
        integration_client: AsyncClient,
    ):
        """GET /documents/{random_id} → 404."""
        response = await integration_client.get(f"/documents/{uuid.uuid4()}")
        assert response.status_code == 404
