"""
core/database.py
----------------
Async SQLAlchemy engine, session factory, and FastAPI dependency.

Architecture note (NOTES.md):
  FastAPI routers → Service layer → Repository layer → PostgreSQL
  Raw SQL must never appear in routers or services — only in repositories.
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings


class Base(DeclarativeBase):
    """Shared declarative base for all SQLAlchemy models."""


def _build_engine():
    settings = get_settings()
    return create_async_engine(
        settings.database_url,
        echo=settings.debug,          # logs SQL in debug mode only
        pool_pre_ping=True,           # verifies connection before checkout
        pool_size=5,
        max_overflow=10,
    )


# Module-level engine — created once at import time.
# In tests, replace this by patching app.core.database.engine.
engine = _build_engine()

# Session factory — use this to acquire AsyncSession instances.
AsyncSessionFactory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,  # avoid implicit lazy-loads after commit
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency that yields a single AsyncSession per request.

    Usage:
        @router.get("/example")
        async def example(db: AsyncSession = Depends(get_db)):
            ...
    """
    async with AsyncSessionFactory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
