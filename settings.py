"""Runtime settings management with database persistence."""

import logging
from typing import Optional

from pydantic import BaseModel, Field

import database

logger = logging.getLogger(__name__)


class Settings(BaseModel):
    """Runtime application settings stored in database."""

    # yt-dlp
    ytdlp_path: str = Field(default="yt-dlp")
    ytdlp_timeout: int = Field(default=120, ge=10, le=600)

    # Cache TTLs (in seconds)
    cache_video_ttl: int = Field(default=3600, ge=60, le=86400)

    cache_search_ttl: int = Field(default=900, ge=60, le=7200)
    cache_channel_ttl: int = Field(default=1800, ge=60, le=86400)
    cache_avatar_ttl: int = Field(default=86400, ge=3600, le=604800)

    # Search
    default_search_results: int = Field(default=20, ge=5, le=50)
    max_search_results: int = Field(default=50, ge=10, le=100)

    # Invidious
    invidious_enabled: bool = True
    invidious_instance: Optional[str] = None
    invidious_timeout: int = Field(default=10, ge=5, le=60)
    invidious_max_retries: int = Field(default=3, ge=1, le=10)
    invidious_retry_delay: float = Field(default=1.0, ge=0.5, le=30.0)
    invidious_author_thumbnails: bool = False
    invidious_proxy_channels: bool = True
    invidious_proxy_channel_tabs: bool = True
    invidious_proxy_videos: bool = True
    invidious_proxy_playlists: bool = True
    invidious_proxy_captions: bool = True
    invidious_proxy_thumbnails: bool = True

    # Feed
    feed_fetch_interval: int = Field(default=1800, ge=300, le=86400)
    feed_channel_delay: int = Field(default=2, ge=1, le=30)
    feed_max_videos: int = Field(default=30, ge=10, le=100)
    feed_video_max_age: int = Field(default=30, ge=1, le=365)
    feed_ytdlp_use_flat_playlist: bool = Field(
        default=True,
        description=(
            "Use fast yt-dlp flat-playlist mode (recommended). Disabling may cause timeouts "
            "but provides publish dates when Invidious is unavailable."
        ),
    )
    feed_fallback_ytdlp_on_414: bool = Field(
        default=False, description="Automatically use yt-dlp when Invidious hits 414 pagination errors"
    )
    feed_fallback_ytdlp_on_error: bool = Field(
        default=True, description="Automatically use yt-dlp when Invidious fails after retries (500, 502, etc.)"
    )

    # Extraction
    allow_all_sites_for_extraction: bool = Field(
        default=False,
        description="Allow extraction from any site. When disabled, only sites enabled in the Sites table are allowed.",
    )
    cache_extract_ttl: int = Field(default=900, ge=60, le=7200)

    # Security
    dns_cache_ttl: int = Field(default=30, ge=5, le=3600)

    # Rate limiting (Basic Auth)
    rate_limit_window: int = Field(default=60, ge=10, le=600)
    rate_limit_max_failures: int = Field(default=5, ge=1, le=100)
    rate_limit_cleanup_interval: int = Field(default=300, ge=60, le=3600)

    # Proxy/download cleanup
    proxy_download_max_age: int = Field(default=86400, ge=60, le=604800)
    proxy_max_concurrent_downloads: int = Field(default=3, ge=1, le=20)


# In-memory cached settings
_cached_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Get current settings (cached in memory)."""
    global _cached_settings
    if _cached_settings is None:
        _cached_settings = load_settings()
    return _cached_settings


def load_settings() -> Settings:
    """Load settings from database."""
    row = database.get_settings_row()
    if row:
        # Filter to only valid Settings fields
        valid_fields = Settings.model_fields.keys()
        filtered = {k: v for k, v in row.items() if k in valid_fields}
        return Settings(**filtered)
    return Settings()  # Use defaults


def save_settings(settings: Settings) -> None:
    """Save settings to database and update cache."""
    global _cached_settings
    database.update_settings(settings.model_dump())
    _cached_settings = settings
    logger.info("Settings updated and cache refreshed")


def invalidate_cache() -> None:
    """Force reload settings from database on next access."""
    global _cached_settings
    _cached_settings = None
