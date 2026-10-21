"""Add HLS playback settings (Yattee 2 / mpv).

hls_filter_enabled      serve one variant per HLS master instead of YouTube's
                        100+ muxed variants (mpv probes them all on start)
hls_audio_language      language of the muxed YouTube HLS variant to serve
hls_min_height /        bounds of the qualities listed to the client
hls_max_height          (0 = no bound)
hls_dash_enabled        translate DASH to byte-range HLS (4K, separate
                        audio languages) instead of using YouTube's HLS
hls_dash_audio_languages  extra audio renditions besides the original
hls_dash_prefer_av1     prefer AV1 over H.264 when both exist

Revision ID: 014
Revises: 013
Create Date: 2026-10-10
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "014"
down_revision: Union[str, Sequence[str], None] = "013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_COLUMNS = {
    "hls_filter_enabled": "INTEGER DEFAULT 1",
    "hls_audio_language": "TEXT",
    "hls_min_height": "INTEGER DEFAULT 0",
    "hls_max_height": "INTEGER DEFAULT 0",
    "hls_dash_enabled": "INTEGER DEFAULT 1",
    "hls_dash_audio_languages": "TEXT",
    "hls_dash_prefer_av1": "INTEGER DEFAULT 0",
}


def _column_exists(table: str, column: str) -> bool:
    conn = op.get_bind()
    result = conn.execute(sa.text(f"PRAGMA table_info({table})"))
    return any(row[1] == column for row in result)


def upgrade() -> None:
    for column, ddl in _COLUMNS.items():
        if not _column_exists("settings", column):
            op.execute(f"ALTER TABLE settings ADD COLUMN {column} {ddl}")


def downgrade() -> None:
    for column in _COLUMNS:
        if _column_exists("settings", column):
            op.execute(f"ALTER TABLE settings DROP COLUMN {column}")
