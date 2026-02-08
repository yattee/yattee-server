"""Add invidious_enabled toggle setting.

Adds a master toggle to enable/disable all Invidious functionality
without clearing the instance URL.

Revision ID: 004
Revises: 003
Create Date: 2026-02-06
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "004"
down_revision: Union[str, Sequence[str], None] = "003"
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
    """Add invidious_enabled column."""
    _add_column_if_not_exists("settings", "invidious_enabled", "INTEGER", "1")


def downgrade() -> None:
    """Remove invidious_enabled column."""
    if _column_exists("settings", "invidious_enabled"):
        op.execute("ALTER TABLE settings DROP COLUMN invidious_enabled")
