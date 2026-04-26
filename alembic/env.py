"""Alembic environment: uses the same URL as ``app.database.get_database_url``."""

from __future__ import annotations

import logging
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from app.database import Base, get_database_url

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata
logger = logging.getLogger("alembic.env")


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (SQL script only)."""
    url = get_database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode with a live engine."""
    connectable = create_engine(
        get_database_url(),
        poolclass=pool.NullPool,
        pool_pre_ping=True,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
