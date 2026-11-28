"""Add hls_dash_relay: fetch translated-HLS segments through /proxy/relay.

Revision ID: 015
Revises: 014
Create Date: 2026-10-10
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "015"
down_revision: Union[str, Sequence[str], None] = "014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(table: str, column: str) -> bool:
    conn = op.get_bind()
    result = conn.execute(sa.text(f"PRAGMA table_info({table})"))
    return any(row[1] == column for row in result)


def upgrade() -> None:
    if not _column_exists("settings", "hls_dash_relay"):
        op.execute("ALTER TABLE settings ADD COLUMN hls_dash_relay INTEGER DEFAULT 1")


def downgrade() -> None:
    if _column_exists("settings", "hls_dash_relay"):
        op.execute("ALTER TABLE settings DROP COLUMN hls_dash_relay")
