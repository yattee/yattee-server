"""Alembic environment configuration for raw SQL migrations."""

import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

# Add project root to path for importing config
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config as app_config

# Alembic Config object
alembic_config = context.config

# Setup logging
if alembic_config.config_file_name is not None:
    fileConfig(alembic_config.config_file_name, disable_existing_loggers=False)

# No ORM metadata - using raw SQL migrations
target_metadata = None


def get_database_url():
    """Build SQLite database URL from app config."""
    db_path = os.path.join(app_config.DATA_DIR, "yattee.db")
    return f"sqlite:///{db_path}"


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (generates SQL without connecting)."""
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
    """Run migrations in 'online' mode (executes against database)."""
    # Ensure data directory exists
    os.makedirs(app_config.DATA_DIR, exist_ok=True)

    connectable = create_engine(get_database_url(), poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
