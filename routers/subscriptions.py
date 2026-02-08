"""Client API endpoints for stateless feed."""

import asyncio
import json
import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

import avatar_cache
import database
import feed_fetcher
from security import is_safe_url_strict
from ytdlp_wrapper import is_valid_url

logger = logging.getLogger(__name__)
router = APIRouter(tags=["subscriptions"])

# Semaphore to limit concurrent feed fetches (DoS protection)
_feed_fetch_semaphore = asyncio.Semaphore(10)


async def _rate_limited_fetch(channel_id: str, site: str, channel_url: str):
    """Fetch channel feed with rate limiting via semaphore."""
    async with _feed_fetch_semaphore:
        await feed_fetcher.fetch_single_channel(channel_id, site, channel_url)


# =============================================================================
# Pydantic Models
# =============================================================================


class FeedVideoResponse(BaseModel):
    type: str = "video"
    videoId: str
    title: str
    author: str
    authorId: str
    lengthSeconds: int
    published: Optional[int]
    publishedText: Optional[str]
    viewCount: Optional[int]
    videoThumbnails: List[dict]
    extractor: str
    videoUrl: Optional[str]


# =============================================================================
# Stateless Feed Endpoints
# =============================================================================


class ChannelFeedRequest(BaseModel):
    """Channel info for feed request."""

    channel_id: str = Field(..., min_length=1)
    site: str = Field(..., min_length=1)
    channel_name: Optional[str] = None
    channel_url: Optional[str] = None
    avatar_url: Optional[str] = None


class StatelessFeedRequest(BaseModel):
    """Request body for stateless feed endpoint."""

    channels: List[ChannelFeedRequest] = Field(..., max_length=500)
    limit: int = Field(default=50, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)


class StatelessFeedResponse(BaseModel):
    """Response for stateless feed endpoint."""

    status: str  # "ready" or "fetching"
    videos: List[FeedVideoResponse]
    total: int
    has_more: bool
    ready_count: Optional[int] = None
    pending_count: Optional[int] = None
    error_count: Optional[int] = None
    eta_seconds: Optional[int] = None


class ChannelStatusRequest(BaseModel):
    """Channel info for status check."""

    channel_id: str = Field(..., min_length=1)
    site: str = Field(..., min_length=1)


class FeedStatusRequest(BaseModel):
    """Request body for feed status endpoint."""

    channels: List[ChannelStatusRequest] = Field(..., max_length=500)


class FeedStatusResponse(BaseModel):
    """Response for feed status endpoint."""

    status: str  # "ready" or "fetching"
    ready_count: int
    pending_count: int
    error_count: int = 0  # Channels that failed to fetch


@router.post("/feed", response_model=StatelessFeedResponse)
async def post_feed(data: StatelessFeedRequest):
    """
    Get feed for a list of channels (stateless).

    This endpoint:
    1. Registers channels in watched_channels table
    2. Checks which channels have cached videos
    3. Queues uncached channels for immediate fetch
    4. Returns available videos and fetch status
    """
    if not data.channels:
        return StatelessFeedResponse(
            status="ready", videos=[], total=0, has_more=False, ready_count=0, pending_count=0, error_count=0
        )

    # Validate all URLs before processing (SSRF prevention)
    # DNS resolution enabled to prevent DNS rebinding attacks
    for ch in data.channels:
        if ch.channel_url:
            if not is_valid_url(ch.channel_url):
                raise HTTPException(status_code=400, detail=f"Invalid channel URL format for {ch.channel_id}")
            is_safe, reason = is_safe_url_strict(ch.channel_url)
            if not is_safe:
                raise HTTPException(status_code=403, detail=f"Channel URL blocked for {ch.channel_id}: {reason}")
        if ch.avatar_url:
            if not is_valid_url(ch.avatar_url):
                raise HTTPException(status_code=400, detail=f"Invalid avatar URL format for {ch.channel_id}")
            is_safe, reason = is_safe_url_strict(ch.avatar_url)
            if not is_safe:
                raise HTTPException(status_code=403, detail=f"Avatar URL blocked for {ch.channel_id}: {reason}")

    # Convert to dict format for database functions
    channels_dict = [
        {
            "channel_id": ch.channel_id,
            "site": ch.site,
            "channel_name": ch.channel_name,
            "channel_url": ch.channel_url,
            "avatar_url": ch.avatar_url,
        }
        for ch in data.channels
    ]

    # 1. Upsert all channels to watched_channels (updates last_requested)
    database.upsert_watched_channels(channels_dict)

    # 1b. Schedule avatar caching for YouTube channels
    cache = avatar_cache.get_cache()
    youtube_channels = [ch for ch in data.channels if ch.site.lower() == "youtube"]
    if youtube_channels:
        logger.debug(f"Scheduling avatar cache for {len(youtube_channels)} YouTube channels")
        for ch in youtube_channels:
            cache.schedule_background_fetch(ch.channel_id)

    # 2. Check which channels have cached videos
    cached_channels = database.get_cached_channel_ids(channels_dict)
    all_channel_keys = {(ch.channel_id, ch.site) for ch in data.channels}

    # 2b. Check which channels have errors
    errored_channels = database.get_errored_channel_ids(channels_dict)

    # Calculate counts: pending excludes both cached and errored
    uncached_channels = all_channel_keys - cached_channels - errored_channels
    ready_count = len(cached_channels)
    error_count = len(errored_channels)
    pending_count = len(uncached_channels)

    logger.info(
        f"POST /feed: {len(data.channels)} channels requested - "
        f"cached: {ready_count}, pending: {pending_count}, errored: {error_count}"
    )

    # 3. Queue uncached channels for immediate fetch (skip errored ones)
    if uncached_channels:
        logger.debug(f"Queueing {pending_count} uncached channels for fetch")
        for ch in data.channels:
            if (ch.channel_id, ch.site) in uncached_channels:
                # Queue for immediate background fetch (rate-limited)
                asyncio.create_task(_rate_limited_fetch(ch.channel_id, ch.site, ch.channel_url))

    # 4. Get feed from cached channels only
    videos = database.get_feed_for_channels(channels_dict, limit=data.limit, offset=data.offset)
    total = database.get_feed_count_for_channels(channels_dict)

    logger.debug(f"Returning {len(videos)} videos (total: {total}) from cached channels")

    # Build response
    feed_videos = []
    for v in videos:
        # Build thumbnail list from stored data
        thumbnails = []
        if v.get("thumbnail_data"):
            try:
                thumbnails = json.loads(v["thumbnail_data"])
            except (json.JSONDecodeError, TypeError):
                # Fallback to legacy single thumbnail if JSON parsing fails
                if v.get("thumbnail_url"):
                    thumbnails = [{"quality": "default", "url": v["thumbnail_url"], "width": 320, "height": 180}]
        elif v.get("thumbnail_url"):
            # Legacy fallback for old cached videos without thumbnail_data
            thumbnails = [{"quality": "default", "url": v["thumbnail_url"], "width": 320, "height": 180}]

        feed_videos.append(
            FeedVideoResponse(
                videoId=v["video_id"],
                title=v["title"],
                author=v["author"] or "",
                authorId=v["author_id"],
                lengthSeconds=int(v["length_seconds"] or 0),
                published=v["published"],
                publishedText=v["published_text"],
                viewCount=v["view_count"],
                videoThumbnails=thumbnails,
                extractor=v["site"],
                videoUrl=v["video_url"],
            )
        )

    # Determine status
    status = "ready" if pending_count == 0 else "fetching"
    eta_seconds = pending_count * 3 if pending_count > 0 else None  # ~3 sec per channel estimate

    return StatelessFeedResponse(
        status=status,
        videos=feed_videos,
        total=total,
        has_more=data.offset + data.limit < total,
        ready_count=ready_count,
        pending_count=pending_count,
        error_count=error_count,
        eta_seconds=eta_seconds,
    )


@router.post("/feed/status", response_model=FeedStatusResponse)
async def post_feed_status(data: FeedStatusRequest):
    """
    Check feed status for a list of channels (lightweight polling endpoint).

    Returns count of channels with cached videos vs pending fetch.
    Errored channels are counted separately and treated as "done" (not pending).
    """
    if not data.channels:
        return FeedStatusResponse(status="ready", ready_count=0, pending_count=0, error_count=0)

    # Convert to dict format
    channels_dict = [{"channel_id": ch.channel_id, "site": ch.site} for ch in data.channels]

    # Check which channels have cached videos
    cached_channels = database.get_cached_channel_ids(channels_dict)
    all_channel_keys = {(ch.channel_id, ch.site) for ch in data.channels}

    # Check which channels have errors
    errored_channels = database.get_errored_channel_ids(channels_dict)

    ready_count = len(cached_channels)
    error_count = len(errored_channels)
    # Pending = total - ready - errored (errored channels are "done", just with errors)
    pending_count = len(all_channel_keys - cached_channels - errored_channels)

    # Status is "ready" when no channels are still pending
    status = "ready" if pending_count == 0 else "fetching"

    return FeedStatusResponse(
        status=status, ready_count=ready_count, pending_count=pending_count, error_count=error_count
    )
