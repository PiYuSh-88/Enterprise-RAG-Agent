"""
services/interfaces.py
----------------------
Protocol (interface) definitions for all service and repository dependencies.

Why Protocols instead of ABCs?
  FastAPI's Depends() wires concrete implementations at runtime.
  Protocols allow test code to inject plain mock objects without inheriting
  from anything — as long as the mock has the right method signatures,
  isinstance checks pass and mypy is satisfied.

Rule (NOTES.md): services are wired against these interfaces, not concrete
classes.  This is what makes the test suite mockable without hitting real APIs.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from app.models.document import Document
    from app.schemas.document import DocumentCreate


@runtime_checkable
class IVectorRepository(Protocol):
    """
    Minimal interface for vector-store repositories.

    Milestone 0: only ping() is required.
    Milestone 1+: add upsert(), search(), delete() here as they are implemented.
    """

    async def ping(self) -> bool:
        """
        Return True if the vector store is reachable, False otherwise.
        Must never raise — swallow exceptions and return False.
        """
        ...


@runtime_checkable
class IDocumentRepository(Protocol):
    """
    Interface for the document metadata repository (PostgreSQL).

    Milestone 1: create() and get_by_id() are required.
    Milestone 2+: add list(), delete(), update_status() as needed.
    """

    async def create(self, data: DocumentCreate) -> Document:
        """
        Persist a new document record and return the ORM instance.
        Must flush so the returned object has a populated id.
        """
        ...

    async def get_by_id(self, doc_id: uuid.UUID) -> Document | None:
        """
        Fetch a document by primary key.
        Returns None if not found; never raises on missing row.
        """
        ...
