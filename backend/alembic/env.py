"""
alembic/env.py
--------------
Alembic migration environment — patched for async SQLAlchemy + asyncpg.

Key changes from the generated default:
  1. DATABASE_URL is read from pydantic-settings (our .env), not alembic.ini,
     so there is a single source of truth for the connection string.
  2. asyncpg uses async I/O, so we use AsyncEngine + run_sync() rather than
     the synchronous engine_from_config().
  3. target_metadata is set to Base.metadata so alembic autogenerate can
     detect model changes (no models yet in Milestone 0, but wired correctly).
"""

import asyncio
import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# ── Make sure `app` package is importable when running alembic from backend/ ──
# Alembic runs from backend/, so backend/ is already in sys.path usually,
# but this guards against edge cases (e.g. running from repo root).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings  # noqa: E402
from app.core.database import Base  # noqa: E402

# ── Alembic config object ─────────────────────────────────────────────────────
config = context.config

# Set up Python logging from alembic.ini [loggers] section
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Point autogenerate at our SQLAlchemy metadata
target_metadata = Base.metadata

# Override sqlalchemy.url with the value from pydantic-settings / .env
# so we never store the connection string in alembic.ini.
settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.database_url)


# ── Offline migrations ────────────────────────────────────────────────────────
def run_migrations_offline() -> None:
    """
    Emit SQL to stdout without a live DB connection.
    Useful for generating migration scripts to review before applying.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


# ── Online migrations (async) ─────────────────────────────────────────────────
def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Create an async engine and run migrations via run_sync()."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


# ── Entry point ───────────────────────────────────────────────────────────────
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
