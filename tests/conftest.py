"""
tests/conftest.py
-----------------
Shared pytest fixtures available to all test modules.

Design:
  - All fixtures here are *unit-test safe* — no real network, no real DB.
  - Integration fixtures (real Postgres/Qdrant) will go in
    tests/integration/conftest.py (Phase 6+).
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock

from app.core.config import Settings, get_settings
from app.main import create_app


# ── Settings fixture ──────────────────────────────────────────────────────────

@pytest.fixture()
def test_settings() -> Settings:
    """
    Return a Settings instance with known test values, without reading .env.
    Constructed directly to avoid any filesystem dependency.
    """
    return Settings(
        app_env="test",
        app_name="Test RAG Agent",
        app_version="0.0.1-test",
        debug=True,
        secret_key="test-secret",
        postgres_host="localhost",
        postgres_port=5432,
        postgres_db="testdb",
        postgres_user="testuser",
        postgres_password="testpass",
        database_url="postgresql+asyncpg://testuser:testpass@localhost:5432/testdb",
        qdrant_host="localhost",
        qdrant_port=6333,
        qdrant_api_key="",
        qdrant_collection_name="test_collection",
        openai_api_key="sk-test",
        embedding_dimensions=1536,
        jwt_secret="test-jwt-secret",
        log_level="DEBUG",
        cors_origins="http://localhost:3000",
    )


# ── Mock repository fixture ───────────────────────────────────────────────────

@pytest.fixture()
def mock_vector_repo_ok() -> MagicMock:
    """Vector repository mock whose ping() returns True (Qdrant reachable)."""
    repo = MagicMock()
    repo.ping = AsyncMock(return_value=True)
    return repo


@pytest.fixture()
def mock_vector_repo_down() -> MagicMock:
    """Vector repository mock whose ping() returns False (Qdrant unreachable)."""
    repo = MagicMock()
    repo.ping = AsyncMock(return_value=False)
    return repo


# ── Mock DB session fixture ───────────────────────────────────────────────────

@pytest.fixture()
def mock_db_ok() -> AsyncMock:
    """AsyncSession mock that succeeds on execute() (Postgres reachable)."""
    session = AsyncMock()
    session.execute = AsyncMock(return_value=MagicMock())
    return session


@pytest.fixture()
def mock_db_down() -> AsyncMock:
    """AsyncSession mock whose execute() raises (Postgres unreachable)."""
    session = AsyncMock()
    session.execute = AsyncMock(
        side_effect=Exception("could not connect to server")
    )
    return session


# ── TestClient fixture ────────────────────────────────────────────────────────

@pytest.fixture()
def test_app(test_settings: Settings, mock_vector_repo_ok: MagicMock):
    """
    FastAPI TestClient with all external dependencies overridden.

    - get_settings() → test_settings (no .env needed)
    - get_db() → mock_db_ok (no Postgres needed)
    - get_vector_repository() → mock_vector_repo_ok (no Qdrant needed)
    """
    from app.core.database import get_db
    from app.routers.health import get_vector_repository

    app = create_app()

    # Override dependency injection
    app.dependency_overrides[get_settings] = lambda: test_settings
    app.dependency_overrides[get_db] = lambda: mock_db_ok
    app.dependency_overrides[get_vector_repository] = lambda: mock_vector_repo_ok

    # Pre-populate app.state so the lifespan doesn't try to connect to Qdrant
    app.state.vector_repository = mock_vector_repo_ok
    app.state.qdrant_client = MagicMock()

    with TestClient(app, raise_server_exceptions=True) as client:
        yield client

    app.dependency_overrides.clear()
