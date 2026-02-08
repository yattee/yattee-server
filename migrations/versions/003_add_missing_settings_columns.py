"""Add missing settings columns and fix defaults.

Adds columns for settings that exist in the Python model but were missing
from the database schema. Also fixes default value mismatches and removes
dead columns.

Revision ID: 003
Revises: 002
Create Date: 2026-02-06
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "003"
down_revision: Union[str, Sequence[str], None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(table: str, column: str) -> bool:
    """Check if a column exists in a SQLite table via PRAGMA table_info."""
    conn = op.get_bind()
    result = conn.execute(sa.text(f"PRAGMA table_info({table})"))
    # PRAGMA table_info returns rows: (cid, name, type, notnull, dflt_value, pk)
    return any(row[1] == column for row in result)


def _add_column_if_not_exists(table: str, column: str, coltype: str, default: str) -> None:
    if not _column_exists(table, column):
        op.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coltype} DEFAULT {default}")


def _drop_column_if_exists(table: str, column: str) -> None:
    if _column_exists(table, column):
        op.execute(f"ALTER TABLE {table} DROP COLUMN {column}")


def upgrade() -> None:
    """Add missing columns, fix defaults, remove dead columns."""
    # Add missing columns that exist in Python model but not in DB
    _add_column_if_not_exists("settings", "feed_fallback_ytdlp_on_error", "INTEGER", "1")
    _add_column_if_not_exists("settings", "invidious_max_retries", "INTEGER", "3")
    _add_column_if_not_exists("settings", "invidious_retry_delay", "REAL", "1.0")

    # Ensure columns exist before updating defaults (may be missing in pre-Alembic DBs
    # where migration 002's CREATE TABLE IF NOT EXISTS was a no-op)
    _add_column_if_not_exists("settings", "proxy_download_max_age", "INTEGER", "300")
    _add_column_if_not_exists("settings", "feed_ytdlp_use_flat_playlist", "INTEGER", "0")

    # Fix default mismatches for existing installs that still have old defaults
    # proxy_download_max_age: DB default was 300 (5 min), should be 86400 (24h)
    op.execute("UPDATE settings SET proxy_download_max_age = 86400 WHERE proxy_download_max_age = 300")
    # feed_ytdlp_use_flat_playlist: DB default was 0, should be 1 (True)
    op.execute("UPDATE settings SET feed_ytdlp_use_flat_playlist = 1 WHERE feed_ytdlp_use_flat_playlist = 0")

    # Remove dead columns (not in Python model, not used anywhere)
    # SQLite 3.35.0+ (2021-03-12) supports ALTER TABLE DROP COLUMN:
    _drop_column_if_exists("settings", "cache_stream_ttl")
    _drop_column_if_exists("settings", "jwt_expiry_hours")


def downgrade() -> None:
    """Re-add removed columns, remove added columns."""
    _add_column_if_not_exists("settings", "cache_stream_ttl", "INTEGER", "300")
    _add_column_if_not_exists("settings", "jwt_expiry_hours", "INTEGER", "24")
    _drop_column_if_exists("settings", "feed_fallback_ytdlp_on_error")
    _drop_column_if_exists("settings", "invidious_max_retries")
    _drop_column_if_exists("settings", "invidious_retry_delay")
