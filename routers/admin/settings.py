"""Settings and watched channels endpoints."""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

import avatar_cache
import database
import settings as settings_module
from utils import get_base_url

from .deps import get_current_admin

router = APIRouter()


# =============================================================================
# Pydantic Models
# =============================================================================


class WatchedChannelResponse(BaseModel):
    channel_id: str
    site: str
    channel_name: Optional[str]
    channel_url: Optional[str]
    avatar_url: Optional[str]
    last_requested: str
    last_fetch: Optional[str]
    fetch_error: Optional[str]
    video_count: int = 0
    last_video_published: Optional[int] = None
    last_video_title: Optional[str] = None


class SettingsResponse(BaseModel):
    ytdlp_path: str
    ytdlp_timeout: int
    cache_video_ttl: int
    cache_search_ttl: int
    cache_channel_ttl: int
    cache_avatar_ttl: int
    cache_extract_ttl: int
    default_search_results: int
    max_search_results: int
    invidious_enabled: bool
    invidious_instance: Optional[str]
    invidious_timeout: int
    invidious_max_retries: int
    invidious_retry_delay: float
    invidious_author_thumbnails: bool
    invidious_proxy_channels: bool
    invidious_proxy_channel_tabs: bool
    invidious_proxy_videos: bool
    invidious_proxy_playlists: bool
    invidious_proxy_captions: bool
    invidious_proxy_thumbnails: bool
    feed_fetch_interval: int
    feed_channel_delay: int
    feed_max_videos: int
    feed_video_max_age: int
    feed_ytdlp_use_flat_playlist: bool
    feed_fallback_ytdlp_on_414: bool
    feed_fallback_ytdlp_on_error: bool
    allow_all_sites_for_extraction: bool
    dns_cache_ttl: int
    rate_limit_window: int
    rate_limit_max_failures: int
    rate_limit_cleanup_interval: int
    proxy_download_max_age: int
    proxy_max_concurrent_downloads: int


class SettingsUpdate(BaseModel):
    ytdlp_path: Optional[str] = None
    ytdlp_timeout: Optional[int] = None
    cache_video_ttl: Optional[int] = None
    cache_search_ttl: Optional[int] = None
    cache_channel_ttl: Optional[int] = None
    cache_avatar_ttl: Optional[int] = None
    cache_extract_ttl: Optional[int] = None
    default_search_results: Optional[int] = None
    max_search_results: Optional[int] = None
    invidious_enabled: Optional[bool] = None
    invidious_instance: Optional[str] = None
    invidious_timeout: Optional[int] = None
    invidious_max_retries: Optional[int] = None
    invidious_retry_delay: Optional[float] = None
    invidious_author_thumbnails: Optional[bool] = None
    invidious_proxy_channels: Optional[bool] = None
    invidious_proxy_channel_tabs: Optional[bool] = None
    invidious_proxy_videos: Optional[bool] = None
    invidious_proxy_playlists: Optional[bool] = None
    invidious_proxy_captions: Optional[bool] = None
    invidious_proxy_thumbnails: Optional[bool] = None
    feed_fetch_interval: Optional[int] = None
    feed_channel_delay: Optional[int] = None
    feed_max_videos: Optional[int] = None
    feed_video_max_age: Optional[int] = None
    feed_ytdlp_use_flat_playlist: Optional[bool] = None
    feed_fallback_ytdlp_on_414: Optional[bool] = None
    feed_fallback_ytdlp_on_error: Optional[bool] = None
    allow_all_sites_for_extraction: Optional[bool] = None
    dns_cache_ttl: Optional[int] = None
    rate_limit_window: Optional[int] = None
    rate_limit_max_failures: Optional[int] = None
    rate_limit_cleanup_interval: Optional[int] = None
    proxy_download_max_age: Optional[int] = None
    proxy_max_concurrent_downloads: Optional[int] = None


# =============================================================================
# Settings API
# =============================================================================


@router.get("/api/settings", response_model=SettingsResponse)
async def get_settings(admin: dict = Depends(get_current_admin)):
    """Get current server settings."""
    settings = settings_module.get_settings()
    return SettingsResponse(**settings.model_dump())


@router.put("/api/settings", response_model=SettingsResponse)
async def update_settings(data: SettingsUpdate, admin: dict = Depends(get_current_admin)):
    """Update server settings."""
    from pydantic import ValidationError

    current = settings_module.get_settings()
    update_data = data.model_dump(exclude_unset=True)

    # Merge with current settings
    merged = {**current.model_dump(), **update_data}

    try:
        new_settings = settings_module.Settings(**merged)
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))

    settings_module.save_settings(new_settings)

    # Reset caches if cache settings changed
    cache_keys = [
        "cache_video_ttl", "cache_search_ttl", "cache_channel_ttl", "cache_avatar_ttl", "cache_extract_ttl",
    ]
    if any(k in update_data for k in cache_keys):
        try:
            from ytdlp_wrapper import reset_caches

            reset_caches()
        except ImportError:
            pass  # reset_caches not yet implemented

    return SettingsResponse(**new_settings.model_dump())


# =============================================================================
# Watched Channels API (Stateless Feed Aggregation)
# =============================================================================


@router.get("/api/watched-channels", response_model=List[WatchedChannelResponse])
async def list_watched_channels(request: Request, admin: dict = Depends(get_current_admin)):
    """Get all watched channels with feed fetch status and video stats.

    Watched channels are channels that clients have requested in feed requests.
    They are prefetched by the background feed fetcher.
    """
    channels = database.get_watched_channels_with_status()

    # Get base URL for generating avatar proxy URLs
    base_url = get_base_url(request)

    return [
        WatchedChannelResponse(
            channel_id=ch["channel_id"],
            site=ch["site"],
            channel_name=ch["channel_name"],
            # For YouTube channels without channel_url, generate from channel_id
            channel_url=ch["channel_url"]
            or (
                f"https://www.youtube.com/{ch['channel_id']}"
                if ch["channel_id"].startswith("@")
                else f"https://www.youtube.com/channel/{ch['channel_id']}"
            )
            if ch.get("site", "").lower() == "youtube"
            else ch["channel_url"],
            # For YouTube channels without avatar_url, generate proxy URL
            avatar_url=ch["avatar_url"]
            or (
                f"{base_url}/api/v1/channels/{ch['channel_id']}/avatar/176.jpg"
                if ch.get("site", "").lower() == "youtube" and base_url
                else None
            ),
            last_requested=ch["last_requested"] or "",
            last_fetch=ch["last_fetch"],
            fetch_error=ch["fetch_error"],
            video_count=ch.get("video_count", 0),
            last_video_published=ch.get("last_video_published"),
            last_video_title=ch.get("last_video_title"),
        )
        for ch in channels
    ]


@router.post("/api/watched-channels/refresh-all")
async def refresh_all_watched_channels(admin: dict = Depends(get_current_admin)):
    """Trigger immediate refresh of all watched channels.

    Starts a background task to fetch all watched channels.
    Returns immediately while the fetch happens in the background.
    """
    import asyncio
    import logging

    from feed_fetcher import fetch_all_channels

    logger = logging.getLogger(__name__)

    # Schedule avatar caching for all YouTube watched channels
    cache = avatar_cache.get_cache()
    channels = database.get_all_watched_channels()
    youtube_channels = [ch for ch in channels if ch.get("site", "").lower() == "youtube" and ch.get("channel_id")]

    if youtube_channels:
        logger.debug(f"Scheduling avatar cache refresh for {len(youtube_channels)} YouTube watched channels")
        for ch in youtube_channels:
            cache.schedule_background_fetch(ch["channel_id"])

    # Trigger background fetch (non-blocking)
    asyncio.create_task(fetch_all_channels())

    return {"success": True, "message": "Refresh started for all channels"}
