"""
core/config.py
--------------
Application configuration via pydantic-settings.

All values are read from environment variables / .env file.
Never hardcode secrets or connection strings — only defaults that are
safe to expose (e.g. port numbers, model names) are set here.
"""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolve .env relative to this file's location (backend/app/core/config.py)
# so the path is correct regardless of which directory uvicorn is run from.
# parents[0]=core/  parents[1]=app/  parents[2]=backend/  parents[3]=repo root
_ENV_FILE = Path(__file__).resolve().parents[3] / ".env"


class Settings(BaseSettings):
    """Central settings object.  Populated from .env (gitignored)."""

    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",  # silently ignore unknown env vars
    )

    # ── App ──────────────────────────────────────────────────────────────────
    app_env: str = Field(default="development")
    app_name: str = Field(default="SmartPark RAG Agent")
    app_version: str = Field(default="0.1.0")
    debug: bool = Field(default=False)
    secret_key: str = Field(default="change-me")

    # ── API Server ────────────────────────────────────────────────────────────
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8000)

    # ── PostgreSQL ────────────────────────────────────────────────────────────
    postgres_host: str = Field(default="localhost")
    postgres_port: int = Field(default=5432)
    postgres_db: str = Field(default="ragdb")
    postgres_user: str = Field(default="postgres")
    postgres_password: str = Field(default="devpassword123")
    database_url: str = Field(
        default="postgresql+asyncpg://postgres:devpassword123@localhost:5432/ragdb"
    )

    # ── Qdrant ────────────────────────────────────────────────────────────────
    qdrant_host: str = Field(default="localhost")
    qdrant_port: int = Field(default=6333)
    qdrant_api_key: str = Field(default="")
    qdrant_collection_name: str = Field(default="rag_documents")

    # ── OpenAI ────────────────────────────────────────────────────────────────
    openai_api_key: str = Field(default="")
    openai_embedding_model: str = Field(default="text-embedding-3-small")
    openai_chat_model: str = Field(default="gpt-4o-mini")
    openai_max_tokens: int = Field(default=2048)
    openai_temperature: float = Field(default=0.2)

    # ── Document Processing ───────────────────────────────────────────────────
    chunk_size: int = Field(default=1000)
    chunk_overlap: int = Field(default=150)
    max_upload_size_mb: int = Field(default=50)

    # ── Embeddings ────────────────────────────────────────────────────────────
    # MUST match the Qdrant collection vector size. Any mismatch causes every
    # insert to fail — do NOT change without recreating the collection.
    embedding_dimensions: int = Field(default=1536)

    # ── Auth / JWT ────────────────────────────────────────────────────────────
    jwt_secret: str = Field(default="change-me-jwt")
    jwt_algorithm: str = Field(default="HS256")
    jwt_expire_minutes: int = Field(default=60)

    # ── CORS ──────────────────────────────────────────────────────────────────
    cors_origins: str = Field(default="http://localhost:3000,http://localhost:5173")

    # ── Logging ───────────────────────────────────────────────────────────────
    log_level: str = Field(default="INFO")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Return a cached Settings instance.

    Using lru_cache ensures the .env file is parsed only once per process.
    In tests, call ``get_settings.cache_clear()`` before patching env vars
    to force a fresh read.
    """
    return Settings()
