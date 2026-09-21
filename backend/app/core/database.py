"""
core/database.py
----------------
Async SQLAlchemy engine factory, session dependency, and declarative Base.

Architecture note (NOTES.md):
  FastAPI routers → Service layer → Repository layer → PostgreSQL
  Raw SQL must never appear in routers or services — only in repositories.

Lifecycle design (post-audit fix I1):
  The engine and session factory are created in the application lifespan
  (main.py) and stored on app.state, exactly like the Qdrant client.
  get_db() reads from request.app.state so that:
    - No connection objects exist at module import time.
    - Integration tests can provide a different engine (pointing at a test DB)
      by setting app.state.db_session_factory before the test client starts —
      no fragile module-level patching required.
"""

from collections.abc import AsyncGenerator

from fastapi import Request
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import Settings


class Base(DeclarativeBase):
    """Shared declarative base for all SQLAlchemy models."""


def build_engine(settings: Settings) -> AsyncEngine:
    """
    Build an async SQLAlchemy engine from application settings.

    Called once in lifespan startup (main.py) and stored on app.state.
    Exposed as a public function so integration tests can call it with a
    test-specific Settings object to get an engine pointing at a test DB.
    """
    return create_async_engine(
        settings.database_url,
        echo=settings.debug,    # logs SQL in debug mode only
        pool_pre_ping=True,     # verifies connection before checkout
        pool_size=5,
        max_overflow=10,
    )


def build_session_factory(
    engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    """
    Build an async session factory bound to the given engine.

    Called once in lifespan startup and stored on app.state.
    Kept separate from build_engine so integration test fixtures can bind
    a factory to a test engine without reconstructing the engine.
    """
    return async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,  # avoid implicit lazy-loads after commit
    )


async def get_db(request: Request) -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency that yields a single AsyncSession per request.

    Reads the session factory from request.app.state (set in lifespan),
    so the dependency is bound to whatever engine the running app (or test)
    configured — no module-level singletons.

    Usage:
        @router.get("/example")
        async def example(db: AsyncSession = Depends(get_db)):
            ...
    """
    session_factory: async_sessionmaker[AsyncSession] = (
        request.app.state.db_session_factory
    )
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
