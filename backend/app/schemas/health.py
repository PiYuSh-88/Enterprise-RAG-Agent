"""
schemas/health.py
-----------------
Pydantic response models for the /health endpoint.

Kept as a separate schema module (not inlined in the router) so the
shape can be imported and asserted in unit tests without importing
the router or any FastAPI machinery.
"""

from enum import Enum

from pydantic import BaseModel


class HealthStatus(str, Enum):
    """Possible health states for a single service."""

    ok = "ok"
    error = "error"


class ServiceHealth(BaseModel):
    """Health report for one downstream service."""

    status: HealthStatus
    detail: str = ""


class HealthResponse(BaseModel):
    """Top-level response returned by GET /health."""

    status: HealthStatus          # overall: ok only if ALL services are ok
    postgres: ServiceHealth
    qdrant: ServiceHealth
    version: str = ""
