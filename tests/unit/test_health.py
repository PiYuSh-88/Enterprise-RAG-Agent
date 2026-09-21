"""
tests/unit/test_health.py
-------------------------
Unit tests for GET /health.

All external dependencies (Postgres, Qdrant, settings) are replaced with
mocks via FastAPI dependency_overrides — no real containers required.

Test matrix:
  - Both services up     → HTTP 200, overall status "ok"
  - Postgres down        → HTTP 503, overall status "error"
  - Qdrant down          → HTTP 503, overall status "error"
  - Both down            → HTTP 503, overall status "error"
  - Response shape       → all expected fields present
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock

from app.core.config import Settings
from app.main import create_app
from app.schemas.health import HealthStatus


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_client(
    test_settings: Settings,
    db_mock: AsyncMock,
    vector_repo_mock: MagicMock,
) -> TestClient:
    """
    Build a TestClient with all external deps overridden.
    Extracted as a helper so each test can compose its own combination.
    """
    from app.core.database import get_db
    from app.routers.health import get_vector_repository

    app = create_app()
    app.dependency_overrides[get_settings_dep] = lambda: test_settings
    app.dependency_overrides[get_db] = lambda: db_mock
    app.dependency_overrides[get_vector_repository] = lambda: vector_repo_mock
    app.state.vector_repository = vector_repo_mock
    app.state.qdrant_client = MagicMock()
    return TestClient(app, raise_server_exceptions=True)


# Import the real get_settings so we can override it
from app.core.config import get_settings as get_settings_dep


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestHealthEndpoint:

    def test_both_services_up_returns_200(
        self,
        test_settings: Settings,
        mock_db_ok: AsyncMock,
        mock_vector_repo_ok: MagicMock,
    ):
        """When Postgres and Qdrant are both reachable, return HTTP 200."""
        client = _make_client(test_settings, mock_db_ok, mock_vector_repo_ok)
        response = client.get("/health")
        assert response.status_code == 200

    def test_both_services_up_overall_status_ok(
        self,
        test_settings: Settings,
        mock_db_ok: AsyncMock,
        mock_vector_repo_ok: MagicMock,
    ):
        """Overall status field is 'ok' when both services are up."""
        client = _make_client(test_settings, mock_db_ok, mock_vector_repo_ok)
        data = client.get("/health").json()
        assert data["status"] == HealthStatus.ok.value

    def test_both_services_up_postgres_ok(
        self,
        test_settings: Settings,
        mock_db_ok: AsyncMock,
        mock_vector_repo_ok: MagicMock,
    ):
        client = _make_client(test_settings, mock_db_ok, mock_vector_repo_ok)
        data = client.get("/health").json()
        assert data["postgres"]["status"] == HealthStatus.ok.value

    def test_both_services_up_qdrant_ok(
        self,
        test_settings: Settings,
        mock_db_ok: AsyncMock,
        mock_vector_repo_ok: MagicMock,
    ):
        client = _make_client(test_settings, mock_db_ok, mock_vector_repo_ok)
        data = client.get("/health").json()
        assert data["qdrant"]["status"] == HealthStatus.ok.value

    def test_postgres_down_returns_503(
        self,
        test_settings: Settings,
        mock_db_down: AsyncMock,
        mock_vector_repo_ok: MagicMock,
    ):
        """When Postgres is unreachable, return HTTP 503."""
        client = _make_client(test_settings, mock_db_down, mock_vector_repo_ok)
        response = client.get("/health")
        assert response.status_code == 503

    def test_postgres_down_overall_status_error(
        self,
        test_settings: Settings,
        mock_db_down: AsyncMock,
        mock_vector_repo_ok: MagicMock,
    ):
        client = _make_client(test_settings, mock_db_down, mock_vector_repo_ok)
        data = client.get("/health").json()
        assert data["status"] == HealthStatus.error.value
        assert data["postgres"]["status"] == HealthStatus.error.value

    def test_qdrant_down_returns_503(
        self,
        test_settings: Settings,
        mock_db_ok: AsyncMock,
        mock_vector_repo_down: MagicMock,
    ):
        """When Qdrant is unreachable, return HTTP 503."""
        client = _make_client(test_settings, mock_db_ok, mock_vector_repo_down)
        response = client.get("/health")
        assert response.status_code == 503

    def test_qdrant_down_overall_status_error(
        self,
        test_settings: Settings,
        mock_db_ok: AsyncMock,
        mock_vector_repo_down: MagicMock,
    ):
        client = _make_client(test_settings, mock_db_ok, mock_vector_repo_down)
        data = client.get("/health").json()
        assert data["status"] == HealthStatus.error.value
        assert data["qdrant"]["status"] == HealthStatus.error.value

    def test_both_services_down_returns_503(
        self,
        test_settings: Settings,
        mock_db_down: AsyncMock,
        mock_vector_repo_down: MagicMock,
    ):
        """When both services are down, return HTTP 503."""
        client = _make_client(test_settings, mock_db_down, mock_vector_repo_down)
        response = client.get("/health")
        assert response.status_code == 503

    def test_response_contains_version(
        self,
        test_settings: Settings,
        mock_db_ok: AsyncMock,
        mock_vector_repo_ok: MagicMock,
    ):
        """Response includes the app version string."""
        client = _make_client(test_settings, mock_db_ok, mock_vector_repo_ok)
        data = client.get("/health").json()
        assert data["version"] == test_settings.app_version

    def test_response_shape(
        self,
        test_settings: Settings,
        mock_db_ok: AsyncMock,
        mock_vector_repo_ok: MagicMock,
    ):
        """Response JSON contains all required top-level fields."""
        client = _make_client(test_settings, mock_db_ok, mock_vector_repo_ok)
        data = client.get("/health").json()
        assert set(data.keys()) >= {"status", "postgres", "qdrant", "version"}
        assert set(data["postgres"].keys()) >= {"status", "detail"}
        assert set(data["qdrant"].keys()) >= {"status", "detail"}
