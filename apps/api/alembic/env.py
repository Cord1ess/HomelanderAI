"""Alembic migration environment — synchronous runner for Windows compatibility.

Uses a regular (sync) psycopg connection so Alembic works on Windows where
asyncio.ProactorEventLoop is the default. The API itself still uses the async
psycopg driver at runtime (postgresql+psycopg://...).
"""
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.config import settings
from app.db.base import Base
import app.models  # noqa: F401 — registers all ORM models with Base.metadata

config = context.config

if config.config_file_name:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# Use sync psycopg URL for Alembic (swap async driver prefix)
_sync_url = (
    settings.database_url
    .replace("postgresql+asyncpg://", "postgresql+psycopg2://")
    .replace("postgresql+psycopg://", "postgresql+psycopg2://")
)


def run_migrations_offline() -> None:
    """Run migrations without an active DB connection (SQL output only)."""
    context.configure(
        url=_sync_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live database connection."""
    cfg = config.get_section(config.config_ini_section, {})
    cfg["sqlalchemy.url"] = _sync_url

    connectable = engine_from_config(
        cfg,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
