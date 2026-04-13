"""Search endpoints."""

import logging
from typing import List, Optional, Union

from fastapi import APIRouter, HTTPException, Query

import innertube
import invidious_proxy
from converters import (
    invidious_to_channel_list_item,
    invidious_to_playlist_list_item,
    invidious_to_video_list_item,
    ytdlp_to_video_list_item,
)
from models import ChannelListItem, PlaylistListItem, VideoListItem
from settings import get_settings
from ytdlp_wrapper import YtDlpError, search_videos

router = APIRouter(tags=["search"])
logger = logging.getLogger(__name__)


def _get_invidious_base() -> str:
    """Get Invidious base URL for resolving relative URLs."""
    return invidious_proxy.get_base_url()


def _convert_innertube_item(
    item: dict,
) -> Union[VideoListItem, ChannelListItem, PlaylistListItem]:
    """Convert an InnerTube result (already Invidious-compatible) to a response model."""
    item_type = item.get("type", "video")
    if item_type == "channel":
        return invidious_to_channel_list_item(item)
    elif item_type == "playlist":
        return invidious_to_playlist_list_item(item)
    return invidious_to_video_list_item(item)


def _convert_invidious_item(
    item: dict, invidious_base: str
) -> Union[VideoListItem, ChannelListItem, PlaylistListItem]:
    """Convert an Invidious API result to a response model."""
    item_type = item.get("type", "video")
    if item_type == "channel":
        return invidious_to_channel_list_item(item, invidious_base)
    elif item_type == "playlist":
        return invidious_to_playlist_list_item(item, invidious_base)
    return invidious_to_video_list_item(item, invidious_base)


@router.get("/search")
async def search(
    q: str = Query(..., description="Search query"),
    page: int = Query(1, ge=1, description="Page number"),
    sort: Optional[str] = Query(None, description="Sort by: relevance, date, views, rating"),
    date: Optional[str] = Query(None, description="Upload date: hour, today, week, month, year"),
    duration: Optional[str] = Query(None, description="Duration: short, medium, long"),
    type: Optional[str] = Query("video", description="Result type: video, channel, playlist, or all"),
) -> List[Union[VideoListItem, ChannelListItem, PlaylistListItem]]:
    """Search for videos, channels, or playlists (Invidious-compatible)."""
    if not q.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    search_type = (type or "video").lower()

    # Step 1: Try InnerTube
    try:
        results = await innertube.search(q, search_type=search_type, page=page, sort=sort, date=date, duration=duration)
        if results:
            return [_convert_innertube_item(item) for item in results]
    except innertube.InnerTubeError as e:
        logger.debug(f"[Search] InnerTube search error: {e}")

    # Step 2: Fall back to Invidious
    if invidious_proxy.is_enabled():
        try:
            invidious_type = search_type if search_type != "all" else "all"
            results = await invidious_proxy.search(q, type=invidious_type, page=page)
            if results:
                invidious_base = _get_invidious_base()
                return [_convert_invidious_item(item, invidious_base) for item in results]
        except invidious_proxy.InvidiousProxyError as e:
            logger.debug(f"[Search] Invidious search error: {e}")

    # Step 3: Fall back to yt-dlp (video search only)
    if search_type in ("video", "all"):
        try:
            s = get_settings()
            per_page = s.default_search_results
            count = page * per_page

            results = await search_videos(q, count, sort=sort, date=date, duration=duration)

            start = (page - 1) * per_page
            page_results = results[start : start + per_page]

            return [ytdlp_to_video_list_item(item) for item in page_results]
        except YtDlpError as e:
            logger.debug(f"[Search] yt-dlp search error: {e}")
        except (KeyError, TypeError, ValueError) as e:
            logger.error(f"[Search] Unexpected error for query '{q}': {e}", exc_info=True)

    return []


@router.get("/search/suggestions", response_model=List[str])
async def search_suggestions(q: str = Query(..., description="Search query")):
    """Get search suggestions. Tries InnerTube first, falls back to Invidious."""
    # Try InnerTube first
    try:
        suggestions = await innertube.get_search_suggestions(q)
        if suggestions:
            return suggestions
    except innertube.InnerTubeError as e:
        logger.debug(f"[Search] InnerTube suggestions error: {e}")

    # Fall back to Invidious
    if invidious_proxy.is_enabled():
        try:
            return await invidious_proxy.get_search_suggestions(q)
        except invidious_proxy.InvidiousProxyError:
            pass

    return []


@router.get("/trending", response_model=List[VideoListItem])
async def trending(region: str = Query("US", description="Region code")):
    """Get trending videos. Tries InnerTube first, falls back to Invidious."""
    try:
        results = await innertube.get_trending(region)
        if results:
            return [invidious_to_video_list_item(item) for item in results]
    except innertube.InnerTubeError as e:
        logger.debug(f"[Search] InnerTube trending error: {e}")

    # Fall back to Invidious
    if invidious_proxy.is_enabled():
        try:
            results = await invidious_proxy.get_trending(region)
            invidious_base = _get_invidious_base()
            return [invidious_to_video_list_item(item, invidious_base) for item in results]
        except invidious_proxy.InvidiousProxyError:
            pass

    return []


@router.get("/popular", response_model=List[VideoListItem])
async def popular():
    """Get popular videos. Tries InnerTube first, falls back to Invidious."""
    try:
        results = await innertube.get_popular()
        if results:
            return [invidious_to_video_list_item(item) for item in results]
    except innertube.InnerTubeError as e:
        logger.debug(f"[Search] InnerTube popular error: {e}")

    # Fall back to Invidious
    if invidious_proxy.is_enabled():
        try:
            results = await invidious_proxy.get_popular()
            invidious_base = _get_invidious_base()
            return [invidious_to_video_list_item(item, invidious_base) for item in results]
        except invidious_proxy.InvidiousProxyError:
            pass

    return []
