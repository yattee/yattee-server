"""Baseline migration - marks current schema as version 1.

This is the baseline migration that establishes version tracking for existing databases.
All tables (users, admins, cached_videos, feed_fetch_status, watched_channels,
sites, credentials, settings) are assumed to already exist.

For fresh databases, the schema is created by migration 002.

Revision ID: 001
Revises:
Create Date: 2026-01-13
"""

from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Baseline migration - existing schema is already in place."""
    # No operations needed - this migration exists to mark the baseline version
    # for databases that were created before Alembic was introduced.
    pass


def downgrade() -> None:
    """Cannot downgrade from baseline."""
    raise RuntimeError("Cannot downgrade from baseline migration - this would destroy all data")
