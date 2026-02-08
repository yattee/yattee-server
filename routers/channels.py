"""Channel endpoints."""

import logging
import re
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

import avatar_cache
import database
import invidious_proxy
from converters import (
    invidious_to_playlist_list_item,
    invidious_to_video_list_item,
    resolve_invidious_url,
    ytdlp_to_playlist_list_item,
    ytdlp_to_video_list_item,
)
from models import (
    ChannelMetadataRequest,
    ChannelPlaylistsResponse,
    ChannelResponse,
    ChannelSearchResponse,
    ChannelShortsResponse,
    ChannelStreamsResponse,
    ChannelVideosResponse,
    Thumbnail,
)
from security import is_safe_url_strict
from settings import get_settings
from ytdlp_wrapper import (
    YtDlpError,
    extract_channel_url,
    get_channel_avatar,
    get_channel_info,
    get_channel_tab,
    get_channel_videos,
)
from ytdlp_wrapper import search_channel as ytdlp_search_channel

router = APIRouter(tags=["channels"])
logger = logging.getLogger(__name__)


def _is_youtube_channel_id(channel_id: str) -> bool:
    """Check if the channel_id is a YouTube-style ID or handle."""
    # YouTube channel IDs: UC + 22 alphanumeric chars
    if re.match(r"^UC[a-zA-Z0-9_-]{22}$", channel_id):
        return True
    # YouTube handles: @username
    if channel_id.startswith("@"):
        return True
    return False


@router.post("/channels/metadata")
async def get_channels_metadata(data: ChannelMetadataRequest):
    """
    Get cached metadata for multiple channels.
    Returns subscriber counts and verified status from cache (no API calls).

    POST /api/v1/channels/metadata
    Body: {"channel_ids": ["UCxxxxxx", "UCyyyyyy"]}

    Response:
    {
        "channels": [
            {"channel_id": "UCxxxxxx", "subscriber_count": 1234567, "is_verified": true},
            {"channel_id": "UCyyyyyy", "subscriber_count": null, "is_verified": false}
        ]
    }
    """
    if not data.channel_ids:
        return {"channels": []}

    metadata = database.get_channels_metadata(data.channel_ids)
    return {"channels": metadata}


@router.get("/channels/{channel_id}", response_model=ChannelResponse)
async def get_channel(channel_id: str):
    """Get channel details (Invidious-compatible)."""
    s = get_settings()

    # For YouTube channels, try Invidious proxy first if enabled (faster)
    if _is_youtube_channel_id(channel_id):
        if s.invidious_proxy_channels and invidious_proxy.is_enabled():
            try:
                data = await invidious_proxy.get_channel(channel_id)
                if data:
                    invidious_base = invidious_proxy.get_base_url()
                    thumbnails = []
                    for thumb in data.get("authorThumbnails", []):
                        thumbnails.append(
                            Thumbnail(
                                quality=thumb.get("quality", "default"),
                                url=resolve_invidious_url(thumb.get("url", ""), invidious_base),
                                width=thumb.get("width"),
                                height=thumb.get("height"),
                            )
                        )
                    banners = []
                    for banner in data.get("authorBanners", []):
                        banners.append(
                            Thumbnail(
                                quality=banner.get("quality", "default"),
                                url=resolve_invidious_url(banner.get("url", ""), invidious_base),
                                width=banner.get("width"),
                                height=banner.get("height"),
                            )
                        )
                    return ChannelResponse(
                        authorId=data.get("authorId", channel_id),
                        author=data.get("author", ""),
                        description=data.get("description"),
                        subCount=data.get("subCount"),
                        totalViews=data.get("totalViews"),
                        authorThumbnails=thumbnails,
                        authorBanners=banners,
                        authorVerified=data.get("authorVerified", False),
                    )
            except invidious_proxy.InvidiousProxyError:
                # Fall through to yt-dlp
                pass

        # Fall back to yt-dlp for YouTube
        try:
            info = await get_channel_info(channel_id)

            # Get the resolved channel ID (UC...) from yt-dlp response
            resolved_channel_id = info.get("channel_id") or info.get("uploader_id") or channel_id

            # Fetch channel avatar - try Invidious first (using resolved ID), then fall back to scraping
            thumbnails = await invidious_proxy.get_channel_thumbnails(resolved_channel_id)

            if not thumbnails:
                # Fall back to scraping YouTube page
                avatar_url = await get_channel_avatar(channel_id)
                if avatar_url:
                    thumbnails.append(Thumbnail(quality="default", url=avatar_url, width=176, height=176))

            return ChannelResponse(
                authorId=resolved_channel_id,
                author=info.get("channel") or info.get("uploader") or info.get("playlist_channel") or "",
                description=info.get("description"),
                subCount=info.get("channel_follower_count"),
                totalViews=info.get("view_count"),
                authorThumbnails=thumbnails,
                authorBanners=[],
                authorVerified=info.get("channel_is_verified", False),
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except YtDlpError as e:
            raise HTTPException(status_code=404, detail=f"Channel not found: {e}")
        except (KeyError, TypeError) as e:
            logger.error(f"[Channels] Unexpected error for channel {channel_id}: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    # For non-YouTube channels, look up the subscription
    subscription = database.get_subscription_by_channel_id(channel_id)
    if not subscription:
        raise HTTPException(
            status_code=404, detail=f"Channel not found. Non-YouTube channel '{channel_id}' must be subscribed first."
        )

    # Return channel info from subscription data
    thumbnails = []
    if subscription.get("avatar_url"):
        thumbnails.append(Thumbnail(quality="default", url=subscription["avatar_url"], width=176, height=176))

    return ChannelResponse(
        authorId=channel_id,
        author=subscription.get("channel_name", ""),
        description=None,
        subCount=None,
        totalViews=None,
        authorThumbnails=thumbnails,
        authorBanners=[],
        authorVerified=False,
    )


@router.get("/channels/{channel_id}/videos", response_model=ChannelVideosResponse)
async def get_channel_videos_endpoint(
    channel_id: str, continuation: Optional[str] = Query(None, description="Continuation token for pagination")
):
    """Get channel videos (Invidious-compatible)."""
    # Convert continuation to page number for yt-dlp (which uses page-based pagination)
    # For Invidious proxy, pass continuation token directly
    page = int(continuation) if continuation and continuation.isdigit() else 1

    # For YouTube channels, try Invidious proxy first if enabled
    if _is_youtube_channel_id(channel_id):
        if get_settings().invidious_proxy_channels and invidious_proxy.is_enabled():
            try:
                data = await invidious_proxy.get_channel_videos(channel_id, continuation)
                if data and "videos" in data:
                    invidious_base = invidious_proxy.get_base_url()
                    video_items = [invidious_to_video_list_item(v, invidious_base) for v in data["videos"]]
                    return ChannelVideosResponse(videos=video_items, continuation=data.get("continuation"))
            except invidious_proxy.InvidiousProxyError:
                # Fall through to yt-dlp
                pass

        # Fall back to yt-dlp for YouTube
        try:
            videos = await get_channel_videos(channel_id, page)
            video_items = [ytdlp_to_video_list_item(video) for video in videos]
            continuation = str(page + 1) if video_items else None
            return ChannelVideosResponse(videos=video_items, continuation=continuation)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except YtDlpError as e:
            raise HTTPException(status_code=404, detail=f"Channel not found: {e}")
        except (KeyError, TypeError) as e:
            logger.error(f"[Channels] Unexpected error for channel {channel_id} videos: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    # For non-YouTube channels, look up the subscription's channel_url
    subscription = database.get_subscription_by_channel_id(channel_id)
    if not subscription or not subscription.get("channel_url"):
        raise HTTPException(
            status_code=404, detail=f"Channel not found. Non-YouTube channel '{channel_id}' must be subscribed first."
        )

    channel_url = subscription["channel_url"]

    try:
        result = await extract_channel_url(channel_url, page=page, per_page=30)
        entries = result.get("entries", [])
        video_items = [ytdlp_to_video_list_item(video) for video in entries]
        continuation = str(page + 1) if video_items else None
        return ChannelVideosResponse(videos=video_items, continuation=continuation)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except YtDlpError as e:
        raise HTTPException(status_code=404, detail=f"Channel not found: {e}")
    except (KeyError, TypeError) as e:
        logger.error(f"[Channels] Unexpected error for channel {channel_id} videos: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/channels/{channel_id}/avatar/{size}.jpg")
async def get_channel_avatar_image(channel_id: str, size: int):
    """Proxy channel avatar image.

    Returns the actual avatar image, proxied through this server.
    Picks the closest available size from cached thumbnails.

    Common sizes: 32, 48, 76, 100, 176, 512
    """
    logger.info(f"[Avatar Endpoint] Request for channel {channel_id}, size {size}")

    # Early return for non-YouTube channels - these must be subscribed with stored avatar URL
    if not _is_youtube_channel_id(channel_id):
        subscription = database.get_subscription_by_channel_id(channel_id)
        if not subscription or not subscription.get("avatar_url"):
            logger.info(f"[Avatar Endpoint] Non-YouTube channel {channel_id} not subscribed or no avatar stored")
            raise HTTPException(status_code=404, detail="Avatar not available for non-YouTube channel")

        # Proxy the stored avatar URL for subscribed non-YouTube channels
        image_url = subscription["avatar_url"]

        # SSRF prevention - validate URL before fetching
        is_safe, reason = is_safe_url_strict(image_url)
        if not is_safe:
            logger.warning(f"[Avatar Endpoint] Blocked unsafe avatar URL for {channel_id}: {reason}")
            raise HTTPException(status_code=403, detail=f"Avatar URL blocked: {reason}")

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(image_url)
                response.raise_for_status()
                return Response(
                    content=response.content,
                    media_type=response.headers.get("content-type", "image/jpeg"),
                    headers={"Cache-Control": "public, max-age=86400"},
                )
        except httpx.HTTPError as e:
            logger.warning(f"[Avatar Endpoint] Failed to fetch stored avatar for {channel_id}: {e}")
            raise HTTPException(status_code=404, detail="Avatar not found")

    # YouTube channel - use avatar cache
    cache = avatar_cache.get_cache()

    # Try cache first
    thumbnails = await cache.get(channel_id)
    logger.info(f"[Avatar Endpoint] Cache check for {channel_id}: {'HIT' if thumbnails else 'MISS'}")

    # Not in cache - fetch now
    if not thumbnails:
        logger.info(f"[Avatar Endpoint] Fetching avatar for {channel_id}")
        thumbnails = await cache.fetch_and_cache(channel_id)
        logger.info(f"[Avatar Endpoint] Fetch result for {channel_id}: {'SUCCESS' if thumbnails else 'FAILED'}")

    if not thumbnails:
        logger.error(f"[Avatar Endpoint] No thumbnails available for {channel_id}")
        raise HTTPException(status_code=404, detail=f"Avatar not found for channel {channel_id}")

    # Find the best matching size
    best_thumb = None
    best_diff = float("inf")

    for thumb in thumbnails:
        thumb_size = thumb.get("width") or thumb.get("height") or 0
        diff = abs(thumb_size - size)
        if diff < best_diff:
            best_diff = diff
            best_thumb = thumb

    if not best_thumb or not best_thumb.get("url"):
        raise HTTPException(status_code=404, detail=f"Avatar URL not found for channel {channel_id}")

    # Fetch and proxy the image
    image_url = best_thumb["url"]
    # Fix protocol-relative URLs
    if image_url.startswith("//"):
        image_url = "https:" + image_url

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(image_url)
            response.raise_for_status()

            content_type = response.headers.get("content-type", "image/jpeg")
            return Response(
                content=response.content,
                media_type=content_type,
                headers={
                    "Cache-Control": "public, max-age=86400"  # Cache for 24h
                },
            )
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Failed to fetch avatar image: {e}")


@router.get("/channels/{channel_id}/playlists", response_model=ChannelPlaylistsResponse)
async def get_channel_playlists_endpoint(
    channel_id: str, continuation: Optional[str] = Query(None, description="Continuation token for pagination")
):
    """Get channel playlists (Invidious-compatible)."""
    # Try Invidious proxy first if enabled
    if get_settings().invidious_proxy_channel_tabs and invidious_proxy.is_enabled():
        try:
            data = await invidious_proxy.get_channel_playlists(channel_id, continuation)
            if data and "playlists" in data:
                invidious_base = invidious_proxy.get_base_url()
                playlist_items = [invidious_to_playlist_list_item(p, invidious_base) for p in data["playlists"]]
                return ChannelPlaylistsResponse(playlists=playlist_items, continuation=data.get("continuation"))
        except invidious_proxy.InvidiousProxyError:
            # Fall through to yt-dlp
            pass

    # Fall back to yt-dlp
    try:
        # Convert continuation to page number (yt-dlp uses page-based pagination)
        page = int(continuation) if continuation and continuation.isdigit() else 1
        playlists = await get_channel_tab(channel_id, "playlists", page)
        playlist_items = [ytdlp_to_playlist_list_item(p) for p in playlists]
        # Return next page as continuation if we got results
        next_continuation = str(page + 1) if playlist_items else None
        return ChannelPlaylistsResponse(playlists=playlist_items, continuation=next_continuation)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except YtDlpError as e:
        raise HTTPException(status_code=404, detail=f"Channel not found: {e}")
    except (KeyError, TypeError) as e:
        logger.error(f"[Channels] Unexpected error for channel {channel_id} playlists: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/channels/{channel_id}/shorts", response_model=ChannelShortsResponse)
async def get_channel_shorts_endpoint(
    channel_id: str, continuation: Optional[str] = Query(None, description="Continuation token for pagination")
):
    """Get channel shorts (Invidious-compatible)."""
    # Try Invidious proxy first if enabled
    if get_settings().invidious_proxy_channel_tabs and invidious_proxy.is_enabled():
        try:
            data = await invidious_proxy.get_channel_shorts(channel_id, continuation)
            if data and "videos" in data:
                invidious_base = invidious_proxy.get_base_url()
                video_items = [invidious_to_video_list_item(v, invidious_base) for v in data["videos"]]
                return ChannelShortsResponse(videos=video_items, continuation=data.get("continuation"))
        except invidious_proxy.InvidiousProxyError:
            # Fall through to yt-dlp
            pass

    # Fall back to yt-dlp
    try:
        page = int(continuation) if continuation and continuation.isdigit() else 1
        videos = await get_channel_tab(channel_id, "shorts", page)
        video_items = [ytdlp_to_video_list_item(v) for v in videos]
        next_continuation = str(page + 1) if video_items else None
        return ChannelShortsResponse(videos=video_items, continuation=next_continuation)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except YtDlpError as e:
        raise HTTPException(status_code=404, detail=f"Channel not found: {e}")
    except (KeyError, TypeError) as e:
        logger.error(f"[Channels] Unexpected error for channel {channel_id} shorts: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/channels/{channel_id}/streams", response_model=ChannelStreamsResponse)
async def get_channel_streams_endpoint(
    channel_id: str, continuation: Optional[str] = Query(None, description="Continuation token for pagination")
):
    """Get channel past live streams (Invidious-compatible)."""
    # Try Invidious proxy first if enabled
    if get_settings().invidious_proxy_channel_tabs and invidious_proxy.is_enabled():
        try:
            data = await invidious_proxy.get_channel_streams(channel_id, continuation)
            if data and "videos" in data:
                invidious_base = invidious_proxy.get_base_url()
                video_items = [invidious_to_video_list_item(v, invidious_base) for v in data["videos"]]
                return ChannelStreamsResponse(videos=video_items, continuation=data.get("continuation"))
        except invidious_proxy.InvidiousProxyError:
            # Fall through to yt-dlp
            pass

    # Fall back to yt-dlp
    try:
        page = int(continuation) if continuation and continuation.isdigit() else 1
        videos = await get_channel_tab(channel_id, "streams", page)
        video_items = [ytdlp_to_video_list_item(v) for v in videos]
        next_continuation = str(page + 1) if video_items else None
        return ChannelStreamsResponse(videos=video_items, continuation=next_continuation)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except YtDlpError as e:
        raise HTTPException(status_code=404, detail=f"Channel not found: {e}")
    except (KeyError, TypeError) as e:
        logger.error(f"[Channels] Unexpected error for channel {channel_id} streams: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/channels/{channel_id}/search", response_model=ChannelSearchResponse)
async def search_channel_endpoint(
    channel_id: str,
    q: str = Query(..., description="Search query"),
    page: int = Query(1, ge=1, description="Page number"),
):
    """Search for videos within a channel (Invidious-compatible).

    Args:
        channel_id: YouTube channel ID (UC...) or handle (@name)
        q: Search query string
        page: Page number (1-based, default 1)

    Returns:
        ChannelSearchResponse with matching videos and continuation token
    """
    if not q or not q.strip():
        raise HTTPException(status_code=400, detail="Search query 'q' is required")

    # For YouTube channels, try Invidious proxy first if enabled
    if _is_youtube_channel_id(channel_id):
        if get_settings().invidious_proxy_channels and invidious_proxy.is_enabled():
            try:
                data = await invidious_proxy.search_channel(channel_id, q, page)
                if data and "videos" in data:
                    invidious_base = invidious_proxy.get_base_url()
                    video_items = [invidious_to_video_list_item(v, invidious_base) for v in data["videos"]]
                    return ChannelSearchResponse(
                        videos=video_items, continuation=str(page + 1) if video_items else None
                    )
            except invidious_proxy.InvidiousProxyError:
                # Fall through to yt-dlp
                pass

        # Fall back to yt-dlp for YouTube
        try:
            videos = await ytdlp_search_channel(channel_id, q, page)
            video_items = [ytdlp_to_video_list_item(video) for video in videos]
            continuation = str(page + 1) if video_items else None
            return ChannelSearchResponse(videos=video_items, continuation=continuation)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except YtDlpError as e:
            raise HTTPException(status_code=404, detail=f"Channel not found or search failed: {e}")
        except (KeyError, TypeError) as e:
            logger.error(f"[Channels] Unexpected error searching channel {channel_id}: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    # For non-YouTube channels, look up the subscription and attempt extraction
    subscription = database.get_subscription_by_channel_id(channel_id)
    if not subscription or not subscription.get("channel_url"):
        raise HTTPException(
            status_code=404, detail=f"Channel not found. Non-YouTube channel '{channel_id}' must be subscribed first."
        )

    channel_url = subscription["channel_url"]

    # Attempt channel search via yt-dlp (may not work for all platforms)
    try:
        videos = await ytdlp_search_channel(channel_url, q, page)
        video_items = [ytdlp_to_video_list_item(video) for video in videos]
        continuation = str(page + 1) if video_items else None
        return ChannelSearchResponse(videos=video_items, continuation=continuation)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except YtDlpError as e:
        # Channel search may not be supported for this platform
        raise HTTPException(status_code=501, detail=f"Channel search not supported for this platform: {e}")
    except (KeyError, TypeError) as e:
        logger.error(f"[Channels] Unexpected error searching channel {channel_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
