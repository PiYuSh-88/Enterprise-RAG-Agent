"""
main.py
-------
FastAPI application factory.

Responsibilities:
  - Create the FastAPI app instance with metadata.
  - Manage lifespan: open/close the Qdrant client and store the
    QdrantVectorRepository on app.state so routers can retrieve it
    via request.app.state.
  - Register all routers.
  - Configure CORS.

What is NOT here:
  - Business logic (lives in services/)
  - Data access (lives in repositories/)
  - Configuration details (lives in core/config.py)
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
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
      - Build and store the Qdrant client + repository on app.state.
        Storing on state (rather than as a module-level singleton) makes
        it trivial to swap in a test double during tests.

    Shutdown:
      - Close the Qdrant client connection cleanly.
    """
    settings = get_settings()
    logger.info("Starting %s v%s [%s]", settings.app_name, settings.app_version, settings.app_env)

    # Build Qdrant client and wrap in repository
    qdrant_client = build_qdrant_client(settings)
    app.state.qdrant_client = qdrant_client
    app.state.vector_repository = QdrantVectorRepository(client=qdrant_client)

    logger.info("Qdrant client initialised → %s:%s", settings.qdrant_host, settings.qdrant_port)

    yield  # ← application runs here

    # Shutdown
    logger.info("Shutting down — closing Qdrant client")
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

    # ── CORS ──────────────────────────────────────────────────────────────────
    origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Routers ───────────────────────────────────────────────────────────────
    app.include_router(health_router.router)
    # Phase 1+: add document, chat, agent routers here

    return app


# Module-level app instance used by uvicorn:
#   uvicorn app.main:app --reload   (run from backend/)
app = create_app()
