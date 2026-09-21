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

from typing import Protocol, runtime_checkable


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
