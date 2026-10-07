"""Runtime settings management with database persistence."""

import logging
from typing import Literal, Optional

from pydantic import BaseModel, Field

import database
import egress

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

    # YouTube egress proxy (used by yt-dlp + InnerTube)
    yt_egress_proxy_enabled: bool = Field(
        default=True,
        description=(
            "When false, the configured proxy is ignored — "
            "useful for temporary disable without losing the value."
        ),
    )
    yt_egress_proxy: Optional[str] = Field(
        default=None,
        description=(
            "HTTP/SOCKS proxy for YouTube-bound traffic. "
            "Format: scheme://[user:password@]host:port (credentials may contain reserved "
            "characters; they are percent-encoded automatically)"
        ),
    )
    yt_ip_family: Literal["auto", "ipv4", "ipv6"] = Field(
        default="auto",
        description=(
            "Force the IP family for YouTube-bound egress (yt-dlp, InnerTube, "
            "/proxy/relay). Ignored while the egress proxy is active — the "
            "proxy's own egress determines the family. Forcing a family the "
            "host doesn't have breaks playback. Takes precedence over "
            "HTTP(S)_PROXY environment variables when forced."
        ),
    )

    # PO token provider (bgutil) for YouTube
    yt_pot_enabled: bool = Field(
        default=False,
        description=(
            "Enable the bgutil PO token provider for yt-dlp. Unblocks full "
            "formats on age-restricted videos (GVS PO token required by web "
            "clients). Uses the bundled provider unless yt_pot_provider_url "
            "points at an external one."
        ),
    )
    yt_pot_provider_url: Optional[str] = Field(
        default=None,
        description=(
            "External bgutil POT provider base URL (http://host:4416). "
            "Empty = use the provider bundled in the image, managed by the app."
        ),
    )

    # InnerTube (direct YouTube API)
    innertube_enabled: bool = True

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
    invidious_local_streams: bool = Field(
        default=False,
        description=(
            "When true, request local=true from Invidious so stream URLs are "
            "proxied through the Invidious instance (companion) instead of "
            "pointing directly at googlevideo.com. Has no effect when the "
            "site's proxy_streaming is on (yattee-server proxies instead)."
        ),
    )

    # Feed
    feed_fetch_interval: int = Field(default=21600, ge=300, le=86400)
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


    def effective_yt_egress_proxy(self) -> Optional[str]:
        """Return the NORMALIZED egress proxy URL if configured and enabled.

        This is the single source every YouTube client consumes (yt-dlp,
        InnerTube, /proxy/relay), so they all see the same, correctly encoded
        value. A configured-but-malformed proxy raises egress.ProxyConfigError
        instead of silently falling back to direct (datacenter) egress.
        """
        if not (self.yt_egress_proxy_enabled and self.yt_egress_proxy):
            return None
        return egress.normalize_proxy_url(self.yt_egress_proxy)

    def effective_pot_provider_url(self) -> Optional[str]:
        """Return the external POT provider URL, or None (bundled provider implied)."""
        return self.yt_pot_provider_url or None

    def effective_ip_family(self) -> str:
        """Return the forced IP family, or "auto" while the egress proxy is active.

        With a proxy, the proxy's egress determines the family; forcing it
        locally would only affect the hop to the proxy (and httpx silently
        drops local_address when a proxy is set).
        """
        return "auto" if self.effective_yt_egress_proxy() else self.yt_ip_family


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
