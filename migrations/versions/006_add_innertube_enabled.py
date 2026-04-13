"""Add innertube_enabled toggle setting.

Adds a master toggle to enable/disable all InnerTube (direct YouTube API)
functionality.

Revision ID: 006
Revises: 005
Create Date: 2026-04-13
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "006"
down_revision: Union[str, Sequence[str], None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(table: str, column: str) -> bool:
    """Check if a column exists in a SQLite table via PRAGMA table_info."""
    conn = op.get_bind()
    result = conn.execute(sa.text(f"PRAGMA table_info({table})"))
    return any(row[1] == column for row in result)


def upgrade() -> None:
    """Add innertube_enabled column."""
    if not _column_exists("settings", "innertube_enabled"):
        op.execute("ALTER TABLE settings ADD COLUMN innertube_enabled INTEGER DEFAULT 1")


def downgrade() -> None:
    """Remove innertube_enabled column."""
    if _column_exists("settings", "innertube_enabled"):
        op.execute("ALTER TABLE settings DROP COLUMN innertube_enabled")
