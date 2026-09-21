# models/__init__.py
# Import all ORM models here so that:
#   1. alembic/env.py (which imports Base.metadata) picks them up for autogenerate.
#   2. Any module that does `from app.models import Document` works cleanly.
from app.models.document import Document  # noqa: F401

__all__ = ["Document"]
