"""Add tuning settings: dns_cache_ttl, proxy_max_concurrent_downloads, rate_limit_cleanup_interval.

Revision ID: 005
Revises: 004
Create Date: 2026-02-06
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "005"
down_revision: Union[str, Sequence[str], None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(table: str, column: str) -> bool:
    """Check if a column exists in a SQLite table via PRAGMA table_info."""
    conn = op.get_bind()
    result = conn.execute(sa.text(f"PRAGMA table_info({table})"))
    return any(row[1] == column for row in result)


def _add_column_if_not_exists(table: str, column: str, coltype: str, default: str) -> None:
    if not _column_exists(table, column):
        op.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coltype} DEFAULT {default}")


def upgrade() -> None:
    """Add tuning settings columns."""
    _add_column_if_not_exists("settings", "dns_cache_ttl", "INTEGER", "30")
    _add_column_if_not_exists("settings", "proxy_max_concurrent_downloads", "INTEGER", "3")
    _add_column_if_not_exists("settings", "rate_limit_cleanup_interval", "INTEGER", "300")


def downgrade() -> None:
    """Remove tuning settings columns."""
    for col in ("dns_cache_ttl", "proxy_max_concurrent_downloads", "rate_limit_cleanup_interval"):
        if _column_exists("settings", col):
            op.execute(f"ALTER TABLE settings DROP COLUMN {col}")
