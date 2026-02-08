"""Database schema initialization using Alembic migrations."""

import logging
import os

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, text

import config

logger = logging.getLogger(__name__)

# Path to alembic.ini (project root)
ALEMBIC_INI_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "alembic.ini")


def _get_alembic_config():
    """Get Alembic configuration."""
    return Config(ALEMBIC_INI_PATH)


def _get_database_url():
    """Build SQLite database URL."""
    db_path = os.path.join(config.DATA_DIR, "yattee.db")
    return f"sqlite:///{db_path}"


def _get_current_revision(engine):
    """Get the current database revision."""
    with engine.connect() as conn:
        context = MigrationContext.configure(conn)
        return context.get_current_revision()


def _is_fresh_database(engine):
    """Check if this is a fresh database (no tables exist)."""
    with engine.connect() as conn:
        result = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='users'"))
        return result.fetchone() is None


def init_db():
    """Initialize the database using Alembic migrations.

    For existing databases (pre-Alembic):
        - Stamps the database with baseline revision
        - Runs any pending migrations

    For fresh databases:
        - Runs all migrations from scratch
    """
    # Ensure data directory exists
    os.makedirs(config.DATA_DIR, exist_ok=True)

    engine = create_engine(_get_database_url())
    alembic_cfg = _get_alembic_config()
    current_rev = _get_current_revision(engine)

    if current_rev is None:
        # No Alembic version table - either fresh DB or pre-Alembic DB
        if _is_fresh_database(engine):
            # Fresh database - run all migrations from scratch
            logger.info("Fresh database detected - running all migrations")
            command.upgrade(alembic_cfg, "head")
        else:
            # Existing database without Alembic tracking
            # Stamp with baseline, then run any pending migrations
            logger.info("Existing database detected - stamping with baseline revision")
            command.stamp(alembic_cfg, "001")
            command.upgrade(alembic_cfg, "head")
    else:
        # Alembic is already tracking - just run pending migrations
        logger.info(f"Database at revision {current_rev} - checking for pending migrations")
        command.upgrade(alembic_cfg, "head")

    logger.info("Database initialization complete")
