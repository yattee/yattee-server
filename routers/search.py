"""Search endpoints."""

import logging
from typing import List, Optional, Union

from fastapi import APIRouter, HTTPException, Query

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


@router.get("/search")
async def search(
    q: str = Query(..., description="Search query"),
    page: int = Query(1, ge=1, description="Page number"),
    sort: Optional[str] = Query(None, description="Sort by: relevance, date, views, rating"),
    date: Optional[str] = Query(None, description="Upload date: hour, today, week, month, year"),
    duration: Optional[str] = Query(None, description="Duration: short, medium, long"),
    type: Optional[str] = Query("video", description="Result type: video, channel, or playlist"),
) -> List[Union[VideoListItem, ChannelListItem, PlaylistListItem]]:
    """Search for videos, channels, or playlists (Invidious-compatible)."""
    if not q.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    search_type = (type or "video").lower()

    # Channel, playlist, and "all" searches require Invidious
    if search_type in ("channel", "playlist", "all"):
        if not invidious_proxy.is_enabled():
            raise HTTPException(
                status_code=501, detail=f"Search type '{search_type}' requires Invidious proxy to be configured"
            )

        try:
            results = await invidious_proxy.search(q, type=search_type, page=page)
            invidious_base = _get_invidious_base()

            if search_type == "channel":
                return [invidious_to_channel_list_item(item, invidious_base) for item in results]
            elif search_type == "playlist":
                return [invidious_to_playlist_list_item(item, invidious_base) for item in results]
            else:  # "all" - mixed results
                # When type=all, Invidious returns mixed result types
                # Each item has a "type" field indicating if it's video, channel, or playlist
                converted_results = []
                for item in results:
                    item_type = item.get("type", "video")
                    if item_type == "channel":
                        converted_results.append(invidious_to_channel_list_item(item, invidious_base))
                    elif item_type == "playlist":
                        converted_results.append(invidious_to_playlist_list_item(item, invidious_base))
                    else:  # video
                        converted_results.append(invidious_to_video_list_item(item, invidious_base))
                return converted_results
        except invidious_proxy.InvidiousProxyError as e:
            raise HTTPException(status_code=502, detail=f"Invidious proxy error: {e}")

    # Video search - use yt-dlp
    try:
        s = get_settings()
        per_page = s.default_search_results
        count = page * per_page

        results = await search_videos(q, count, sort=sort, date=date, duration=duration)

        start = (page - 1) * per_page
        page_results = results[start : start + per_page]

        return [ytdlp_to_video_list_item(item) for item in page_results]
    except YtDlpError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except (KeyError, TypeError, ValueError) as e:
        logger.error(f"[Search] Unexpected error for query '{q}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/search/suggestions", response_model=List[str])
async def search_suggestions(q: str = Query(..., description="Search query")):
    """Get search suggestions (proxied from Invidious if configured)."""
    if not invidious_proxy.is_enabled():
        return []

    try:
        return await invidious_proxy.get_search_suggestions(q)
    except invidious_proxy.InvidiousProxyError:
        return []


@router.get("/trending", response_model=List[VideoListItem])
async def trending(region: str = Query("US", description="Region code")):
    """Get trending videos (proxied from Invidious if configured)."""
    if not invidious_proxy.is_enabled():
        return []

    try:
        results = await invidious_proxy.get_trending(region)
        invidious_base = _get_invidious_base()
        return [invidious_to_video_list_item(item, invidious_base) for item in results]
    except invidious_proxy.InvidiousProxyError:
        return []


@router.get("/popular", response_model=List[VideoListItem])
async def popular():
    """Get popular videos (proxied from Invidious if configured)."""
    if not invidious_proxy.is_enabled():
        return []

    try:
        results = await invidious_proxy.get_popular()
        invidious_base = _get_invidious_base()
        return [invidious_to_video_list_item(item, invidious_base) for item in results]
    except invidious_proxy.InvidiousProxyError:
        return []
