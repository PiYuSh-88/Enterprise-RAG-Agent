"""
routers/health.py
-----------------
GET /health — liveness/readiness probe for Postgres and Qdrant.

Architecture:
  This router is intentionally thin.  It delegates connectivity checks to
  injected dependencies and shapes the HTTP response — that's all.

Behaviour:
  - Returns HTTP 200 with overall status "ok" when both services are reachable.
  - Returns HTTP 503 with overall status "error" when any service is down.
  - Never raises an unhandled exception; failures surface as structured JSON.

Phase 6 note (roadmap.md): /health, /ready, /live will be split into separate
endpoints.  For Milestone 0, a single combined /health is correct per
MILESTONE_0.md scope.
"""

import logging

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.schemas.health import HealthResponse, HealthStatus, ServiceHealth
from app.services.interfaces import IVectorRepository

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Health"])


async def _check_postgres(db: AsyncSession) -> ServiceHealth:
    """Ping PostgreSQL with a trivial query."""
    try:
        await db.execute(text("SELECT 1"))
        return ServiceHealth(status=HealthStatus.ok, detail="reachable")
    except Exception as exc:
        logger.error("Postgres health check failed: %s", exc)
        return ServiceHealth(status=HealthStatus.error, detail=str(exc))


async def _check_qdrant(vector_repo: IVectorRepository) -> ServiceHealth:
    """Ping Qdrant via the repository abstraction."""
    reachable = await vector_repo.ping()
    if reachable:
        return ServiceHealth(status=HealthStatus.ok, detail="reachable")
    return ServiceHealth(status=HealthStatus.error, detail="unreachable")


def get_vector_repository(request: Request) -> IVectorRepository:
    """
    FastAPI dependency that retrieves the QdrantVectorRepository stored
    on app.state during lifespan startup.
    """
    return request.app.state.vector_repository


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Health check",
    description=(
        "Returns the reachability status of Postgres and Qdrant. "
        "HTTP 200 when all services are up; HTTP 503 when any service is down."
    ),
)
async def health_check(
    db: AsyncSession = Depends(get_db),
    vector_repo: IVectorRepository = Depends(get_vector_repository),
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    postgres_health = await _check_postgres(db)
    qdrant_health = await _check_qdrant(vector_repo)

    all_ok = (
        postgres_health.status == HealthStatus.ok
        and qdrant_health.status == HealthStatus.ok
    )
    overall = HealthStatus.ok if all_ok else HealthStatus.error
    http_status = status.HTTP_200_OK if all_ok else status.HTTP_503_SERVICE_UNAVAILABLE

    response = HealthResponse(
        status=overall,
        postgres=postgres_health,
        qdrant=qdrant_health,
        version=settings.app_version,
    )
    return JSONResponse(content=response.model_dump(), status_code=http_status)
