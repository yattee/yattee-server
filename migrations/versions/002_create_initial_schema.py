"""Create initial schema.

Creates all tables for fresh databases. Uses IF NOT EXISTS so it's safe
to run on databases that already have the schema (existing databases).

Revision ID: 002
Revises: 001
Create Date: 2026-01-13
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "002"
down_revision: Union[str, Sequence[str], None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create all initial tables."""
    # Users table
    op.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            is_admin INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            last_login TIMESTAMP
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)")

    # Legacy admins table for backwards compatibility
    op.execute("""
        CREATE TABLE IF NOT EXISTS admins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login TIMESTAMP
        )
    """)

    # Cached videos table
    op.execute("""
        CREATE TABLE IF NOT EXISTS cached_videos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel_id TEXT NOT NULL,
            site TEXT NOT NULL,
            video_id TEXT NOT NULL,
            title TEXT NOT NULL,
            author TEXT NOT NULL,
            author_id TEXT NOT NULL,
            length_seconds INTEGER DEFAULT 0,
            view_count INTEGER,
            published INTEGER,
            published_text TEXT,
            thumbnail_url TEXT,
            thumbnail_data TEXT,
            video_url TEXT,
            fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(channel_id, site, video_id)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_cached_videos_channel ON cached_videos(channel_id, site)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_cached_videos_published ON cached_videos(published DESC)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cached_videos_channel_published "
        "ON cached_videos(channel_id, site, published DESC)"
    )

    # Feed fetch status table
    op.execute("""
        CREATE TABLE IF NOT EXISTS feed_fetch_status (
            channel_id TEXT NOT NULL,
            site TEXT NOT NULL,
            last_fetch TIMESTAMP,
            fetch_error TEXT,
            max_videos_fetched INTEGER,
            pagination_limited BOOLEAN DEFAULT 0,
            pagination_limit_reason TEXT,
            PRIMARY KEY (channel_id, site)
        )
    """)

    # Watched channels table
    op.execute("""
        CREATE TABLE IF NOT EXISTS watched_channels (
            channel_id TEXT NOT NULL,
            site TEXT NOT NULL,
            channel_name TEXT,
            channel_url TEXT,
            avatar_url TEXT,
            last_requested TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            subscriber_count INTEGER,
            is_verified BOOLEAN DEFAULT 0,
            metadata_updated_at TIMESTAMP,
            PRIMARY KEY (channel_id, site)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_watched_channels_last_requested ON watched_channels(last_requested)")

    # Sites table
    op.execute("""
        CREATE TABLE IF NOT EXISTS sites (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            extractor_pattern TEXT NOT NULL,
            enabled BOOLEAN DEFAULT 1,
            priority INTEGER DEFAULT 0,
            proxy_streaming BOOLEAN DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_sites_enabled ON sites(enabled)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_sites_extractor ON sites(extractor_pattern)")

    # Insert default YouTube site if no sites exist
    op.execute("""
        INSERT OR IGNORE INTO sites (id, name, extractor_pattern, enabled, priority, proxy_streaming)
        VALUES (1, 'YouTube', 'youtube', 1, 100, 0)
    """)

    # Credentials table
    op.execute("""
        CREATE TABLE IF NOT EXISTS credentials (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            site_id INTEGER NOT NULL,
            credential_type TEXT NOT NULL,
            key TEXT,
            value TEXT NOT NULL,
            is_encrypted BOOLEAN DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (site_id) REFERENCES sites(id) ON DELETE CASCADE
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_credentials_site_id ON credentials(site_id)")

    # Settings table
    op.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            jwt_expiry_hours INTEGER DEFAULT 24,
            ytdlp_path TEXT DEFAULT 'yt-dlp',
            ytdlp_timeout INTEGER DEFAULT 120,
            cache_video_ttl INTEGER DEFAULT 3600,
            cache_stream_ttl INTEGER DEFAULT 300,
            cache_search_ttl INTEGER DEFAULT 900,
            cache_channel_ttl INTEGER DEFAULT 1800,
            cache_avatar_ttl INTEGER DEFAULT 86400,
            cache_extract_ttl INTEGER DEFAULT 900,
            default_search_results INTEGER DEFAULT 20,
            max_search_results INTEGER DEFAULT 50,
            invidious_instance TEXT DEFAULT NULL,
            invidious_timeout INTEGER DEFAULT 10,
            invidious_author_thumbnails INTEGER DEFAULT 0,
            invidious_proxy_channels INTEGER DEFAULT 1,
            invidious_proxy_channel_tabs INTEGER DEFAULT 1,
            invidious_proxy_videos INTEGER DEFAULT 1,
            invidious_proxy_playlists INTEGER DEFAULT 1,
            invidious_proxy_captions INTEGER DEFAULT 1,
            invidious_proxy_thumbnails INTEGER DEFAULT 1,
            feed_fetch_interval INTEGER DEFAULT 1800,
            feed_channel_delay INTEGER DEFAULT 2,
            feed_max_videos INTEGER DEFAULT 30,
            feed_video_max_age INTEGER DEFAULT 30,
            feed_ytdlp_use_flat_playlist INTEGER DEFAULT 0,
            feed_fallback_ytdlp_on_414 INTEGER DEFAULT 0,
            basic_auth_enabled INTEGER DEFAULT 0,
            allow_all_sites_for_extraction INTEGER DEFAULT 0,
            rate_limit_window INTEGER DEFAULT 60,
            rate_limit_max_failures INTEGER DEFAULT 5,
            proxy_download_max_age INTEGER DEFAULT 300,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    op.execute("INSERT OR IGNORE INTO settings (id) VALUES (1)")


def downgrade() -> None:
    """Drop all tables."""
    op.execute("DROP TABLE IF EXISTS credentials")
    op.execute("DROP TABLE IF EXISTS sites")
    op.execute("DROP TABLE IF EXISTS settings")
    op.execute("DROP TABLE IF EXISTS watched_channels")
    op.execute("DROP TABLE IF EXISTS feed_fetch_status")
    op.execute("DROP TABLE IF EXISTS cached_videos")
    op.execute("DROP TABLE IF EXISTS admins")
    op.execute("DROP TABLE IF EXISTS users")
