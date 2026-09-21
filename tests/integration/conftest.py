"""
tests/integration/conftest.py
------------------------------
Fixtures for integration tests against a real PostgreSQL instance.

Isolation strategy:
  `smartpark_test` database is created once per session using asyncpg
  directly (no SQLAlchemy, no psycopg2).  Each test gets a fresh
  async SQLAlchemy engine so asyncpg connections are never shared across
  event loops.  After each test all rows are deleted from `documents`.

  The development database (`smartpark_db`) is never touched.

Requirements:
  docker compose up -d must be running.

Run:
  pytest tests/integration/ -v
"""

import asyncio
import io
import re
from typing import AsyncGenerator
from unittest.mock import MagicMock

import asyncpg
import pytest
import pytest_asyncio
from docx import Document as DocxDocument
from fastapi import Request
from httpx import ASGITransport, AsyncClient
from pypdf import PdfWriter
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import get_settings
from app.core.database import Base, build_session_factory, get_db
from app.main import create_app

# ── Constants ─────────────────────────────────────────────────────────────────

TEST_DB_NAME = "smartpark_test"

# asyncpg DSN from asyncpg URL: strip the SQLAlchemy dialect prefix
_ASYNCPG_URL_RE = re.compile(r"postgresql\+asyncpg://(.+)")


def _asyncpg_dsn(sqlalchemy_url: str, db: str = "postgres") -> str:
    """Convert a postgresql+asyncpg://... URL to an asyncpg connect string."""
    m = _ASYNCPG_URL_RE.match(sqlalchemy_url)
    if not m:
        raise ValueError(f"Unexpected database URL format: {sqlalchemy_url}")
    # user:pass@host:port/dbname  → swap dbname
    base = m.group(1).rsplit("/", 1)[0]
    return f"postgresql://{base}/{db}"


def _test_sqlalchemy_url(sqlalchemy_url: str) -> str:
    """Return the SQLAlchemy URL pointing at the test database."""
    return sqlalchemy_url.rsplit("/", 1)[0] + f"/{TEST_DB_NAME}"


# ── Session-scoped: create/drop test database ─────────────────────────────────


@pytest.fixture(scope="session", autouse=True)
def create_test_database():
    """
    Create `smartpark_test` before the session; drop it after.

    Uses asyncpg directly (already a project dependency) with
    explicit transaction control to execute CREATE/DROP DATABASE.
    Runs the async work in a temporary event loop isolated from pytest's
    per-test loops so there is no loop-affinity conflict.
    """
    settings = get_settings()
    admin_dsn = _asyncpg_dsn(settings.database_url, "postgres")

    async def _setup():
        conn = await asyncpg.connect(admin_dsn)
        try:
            await conn.execute(f'DROP DATABASE IF EXISTS "{TEST_DB_NAME}"')
            await conn.execute(f'CREATE DATABASE "{TEST_DB_NAME}"')
        finally:
            await conn.close()

    async def _teardown():
        conn = await asyncpg.connect(admin_dsn)
        try:
            await conn.execute(f'DROP DATABASE IF EXISTS "{TEST_DB_NAME}"')
        finally:
            await conn.close()

    asyncio.run(_setup())
    yield
    asyncio.run(_teardown())


# ── Function-scoped: fresh async engine per test ──────────────────────────────


@pytest_asyncio.fixture()
async def test_engine():
    """
    Fresh async SQLAlchemy engine per test, pointing at `smartpark_test`.

    Creating a new engine per test ensures asyncpg connections live in
    the same event loop that the test runs in — avoids all loop-affinity
    errors from sharing engines across pytest's per-test event loops.
    """
    settings = get_settings()
    test_url = _test_sqlalchemy_url(settings.database_url)
    engine = create_async_engine(test_url, echo=False, pool_pre_ping=True)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture()
async def test_session_factory(test_engine):
    """Session factory bound to this test's engine."""
    return build_session_factory(test_engine)


# ── HTTP client ───────────────────────────────────────────────────────────────


@pytest_asyncio.fixture()
async def integration_client(
    test_engine, test_session_factory
) -> AsyncGenerator[AsyncClient, None]:
    """
    httpx.AsyncClient backed by a FastAPI app wired to the isolated test DB.

    The FastAPI lifespan is not triggered (avoids Qdrant network calls);
    app.state is populated manually and get_db is overridden.
    """
    app = create_app()

    app.state.db_engine = test_engine
    app.state.db_session_factory = test_session_factory
    app.state.qdrant_client = MagicMock()
    app.state.vector_repository = MagicMock()

    async def _test_get_db(request: Request) -> AsyncGenerator[AsyncSession, None]:
        async with test_session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = _test_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()


# ── File fixtures ─────────────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def sample_pdf_bytes() -> bytes:
    """Minimal valid PDF (single blank page) generated with pypdf.PdfWriter."""
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


@pytest.fixture(scope="session")
def sample_docx_bytes() -> bytes:
    """Minimal valid DOCX with one paragraph, generated with python-docx."""
    doc = DocxDocument()
    doc.add_paragraph("Integration test document — Hello from python-docx.")
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


@pytest.fixture(scope="session")
def oversized_pdf_bytes() -> bytes:
    """51 MB of data named as PDF — triggers size validation (< real I/O)."""
    return b"%PDF " + b"x" * (51 * 1024 * 1024)


@pytest.fixture(scope="session")
def corrupt_pdf_bytes() -> bytes:
    """PDF header without valid structure — triggers extraction 422."""
    return b"%PDF-1.4 this is not a valid pdf structure"


@pytest.fixture(scope="session")
def corrupt_docx_bytes() -> bytes:
    """Random bytes — not a valid ZIP/DOCX — triggers extraction 422."""
    return b"this is definitely not a docx file"
