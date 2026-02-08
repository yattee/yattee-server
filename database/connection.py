"""Database connection management."""

import logging
import os
import sqlite3
from contextlib import contextmanager

import config

logger = logging.getLogger(__name__)

# Database path
DB_PATH = os.path.join(config.DATA_DIR, "yattee.db")


def get_db_path() -> str:
    """Get the database file path, ensuring data directory exists."""
    os.makedirs(config.DATA_DIR, exist_ok=True)
    return DB_PATH


@contextmanager
def get_connection():
    """Get a database connection with row factory."""
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()
