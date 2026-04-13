"""Switch existing instances to InnerTube-first defaults.

Disables Invidious proxy, enables InnerTube, and increases feed fetch
interval from 30 minutes to 360 minutes for users still on the old default.

Revision ID: 007
Revises: 006
Create Date: 2026-04-13
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "007"
down_revision: Union[str, Sequence[str], None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Switch to InnerTube-first defaults for existing users."""
    # Disable Invidious proxy master toggle
    op.execute("UPDATE settings SET invidious_enabled = 0")

    # Enable InnerTube
    op.execute("UPDATE settings SET innertube_enabled = 1")

    # Update feed interval from old default (1800s / 30min) to 21600s (360min)
    op.execute("UPDATE settings SET feed_fetch_interval = 21600 WHERE feed_fetch_interval = 1800")


def downgrade() -> None:
    """Restore previous defaults."""
    op.execute("UPDATE settings SET invidious_enabled = 1")
    op.execute("UPDATE settings SET feed_fetch_interval = 1800 WHERE feed_fetch_interval = 21600")
