"""Switch fresh installs to InnerTube-first defaults.

For brand new installs (no users provisioned yet), disable Invidious proxy
and enable InnerTube. Existing instances keep their Invidious/InnerTube
settings — in particular, a user who had the Invidious proxy enabled stays
enabled.

For all installs (fresh and existing), bump feed_fetch_interval from the
old 30-minute default to 360 minutes when the user is still on that old
default; users who customised the interval are left alone.

Revision ID: 007
Revises: 006
Create Date: 2026-04-13
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "007"
down_revision: Union[str, Sequence[str], None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _is_fresh_install() -> bool:
    # Migrations run before env_provisioning creates the admin user, so an
    # empty users table at this point means the database has never been used.
    conn = op.get_bind()
    count = conn.execute(sa.text("SELECT COUNT(*) FROM users")).scalar()
    return (count or 0) == 0


def upgrade() -> None:
    """Apply InnerTube-first defaults only on fresh installs; bump feed interval for everyone on the old default."""
    if _is_fresh_install():
        op.execute("UPDATE settings SET invidious_enabled = 0")
        op.execute("UPDATE settings SET innertube_enabled = 1")

    op.execute("UPDATE settings SET feed_fetch_interval = 21600 WHERE feed_fetch_interval = 1800")


def downgrade() -> None:
    """Revert the feed interval bump; Invidious/InnerTube toggles on fresh installs are left in place."""
    op.execute("UPDATE settings SET feed_fetch_interval = 1800 WHERE feed_fetch_interval = 21600")
