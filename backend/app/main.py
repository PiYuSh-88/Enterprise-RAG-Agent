"""
main.py
-------
FastAPI application factory.

Responsibilities:
  - Create the FastAPI app instance with metadata.
  - Manage lifespan: build and store all I/O clients on app.state, then
    dispose them cleanly on shutdown.
  - Register all routers.
  - Configure CORS.

What is NOT here:
  - Business logic (lives in services/)
  - Data access (lives in repositories/)
  - Configuration details (lives in core/config.py)

app.state contract (set during lifespan startup):
  db_engine            — AsyncEngine (SQLAlchemy)
  db_session_factory   — async_sessionmaker[AsyncSession]
  qdrant_client        — AsyncQdrantClient
  vector_repository    — QdrantVectorRepository
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.database import build_engine, build_session_factory
from app.repositories.vector_repository import (
    QdrantVectorRepository,
    build_qdrant_client,
)
from app.routers import health as health_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan context manager.

    Startup:
      - Build the async SQLAlchemy engine + session factory and store on
        app.state (fix I1: no module-import-time engine creation).
      - Build the Qdrant client + repository and store on app.state.

    Shutdown:
      - Dispose the SQLAlchemy engine (returns connections to OS).
      - Close the Qdrant client connection.

    All I/O resources live exclusively on app.state, making them
    trivially replaceable in tests without module-level patching.
    """
    settings = get_settings()
    logger.info(
        "Starting %s v%s [%s]",
        settings.app_name,
        settings.app_version,
        settings.app_env,
    )

    # ── PostgreSQL ─────────────────────────────────────────────────────────────
    db_engine = build_engine(settings)
    app.state.db_engine = db_engine
    app.state.db_session_factory = build_session_factory(db_engine)
    logger.info("DB engine initialised → %s", settings.postgres_host)

    # ── Qdrant ────────────────────────────────────────────────────────────────
    qdrant_client = build_qdrant_client(settings)
    app.state.qdrant_client = qdrant_client
    app.state.vector_repository = QdrantVectorRepository(client=qdrant_client)
    logger.info(
        "Qdrant client initialised → %s:%s",
        settings.qdrant_host,
        settings.qdrant_port,
    )

    yield  # ← application runs here

    # ── Shutdown ──────────────────────────────────────────────────────────────
    logger.info("Shutting down — disposing DB engine and Qdrant client")
    await app.state.db_engine.dispose()
    await qdrant_client.close()


def create_app() -> FastAPI:
    """Application factory — returns a configured FastAPI instance."""
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="Enterprise RAG + Agent System — backend API",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # ── CORS ───────────────────────────────────────────────────────────────────
    origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Routers ────────────────────────────────────────────────────────────────
    app.include_router(health_router.router)
    # Phase 1+: add document, chat, agent routers here

    return app


# Module-level app instance used by uvicorn:
#   uvicorn app.main:app --reload   (run from backend/)
app = create_app()
