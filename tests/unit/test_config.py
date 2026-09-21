"""
tests/unit/test_config.py
-------------------------
Unit tests for core/config.py.

Goals:
  1. Settings loads without error when valid env vars are present.
  2. Field types and defaults are correct.
  3. embedding_dimensions is 1536 (NOTES.md hard requirement).
  4. No real .env file is required — values are injected via monkeypatch.
"""

import pytest
from app.core.config import Settings, get_settings


class TestSettingsDefaults:
    """Settings constructed with explicit values (no .env dependency)."""

    def test_settings_instantiation(self, test_settings: Settings):
        """Settings object is created without errors."""
        assert test_settings is not None

    def test_app_env(self, test_settings: Settings):
        assert test_settings.app_env == "test"

    def test_app_version(self, test_settings: Settings):
        assert test_settings.app_version == "0.0.1-test"

    def test_debug_flag(self, test_settings: Settings):
        assert test_settings.debug is True

    def test_postgres_port_is_int(self, test_settings: Settings):
        """Port numbers must be integers, not strings."""
        assert isinstance(test_settings.postgres_port, int)
        assert test_settings.postgres_port == 5432

    def test_qdrant_port_is_int(self, test_settings: Settings):
        assert isinstance(test_settings.qdrant_port, int)
        assert test_settings.qdrant_port == 6333

    def test_embedding_dimensions_is_1536(self, test_settings: Settings):
        """
        CRITICAL (NOTES.md): Qdrant collection vector size MUST be 1536.
        Any mismatch causes every insert to fail.
        """
        assert test_settings.embedding_dimensions == 1536

    def test_database_url_contains_asyncpg(self, test_settings: Settings):
        """DATABASE_URL must use asyncpg driver for async SQLAlchemy."""
        assert "asyncpg" in test_settings.database_url

    def test_openai_embedding_model_default(self):
        """Verify the default embedding model matches NOTES.md."""
        # Use a fresh Settings instance with the model field at its default
        s = Settings(
            database_url="postgresql+asyncpg://u:p@localhost/db",
            _env_file=None,  # type: ignore[call-arg]
        )
        assert s.openai_embedding_model == "text-embedding-3-small"

    def test_openai_chat_model_default(self):
        """Verify the default chat model matches NOTES.md."""
        s = Settings(
            database_url="postgresql+asyncpg://u:p@localhost/db",
            _env_file=None,  # type: ignore[call-arg]
        )
        assert s.openai_chat_model == "gpt-4o-mini"


class TestGetSettings:
    """Tests for the get_settings() cached dependency."""

    def test_get_settings_returns_settings_instance(self, monkeypatch):
        """get_settings() returns a Settings object."""
        # Clear cache first so monkeypatched env vars take effect
        get_settings.cache_clear()
        monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost/db")
        result = get_settings()
        assert isinstance(result, Settings)
        get_settings.cache_clear()

    def test_get_settings_is_cached(self, monkeypatch):
        """Calling get_settings() twice returns the same object (lru_cache)."""
        get_settings.cache_clear()
        monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost/db")
        first = get_settings()
        second = get_settings()
        assert first is second
        get_settings.cache_clear()
