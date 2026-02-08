"""Video endpoints."""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request

import avatar_cache
import database
import invidious_proxy
from basic_auth import get_current_user_from_request
from converters import (
    invidious_to_video_response,
    ytdlp_to_video_list_item,
    ytdlp_to_video_response,
)
from models import ChannelExtractResponse, Thumbnail, VideoResponse
from settings import get_settings
from utils import get_base_url
from ytdlp_wrapper import (
    YtDlpError,
    extract_channel_url,
    extract_url,
    get_channel_avatar,
    get_video_info,
    is_safe_url,
    is_valid_url,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["videos"])


def validate_extractor_allowed(extractor: str):
    """Check if extractor is allowed based on settings and enabled sites.

    Raises HTTPException 403 if the extractor is not allowed.
    """
    app_settings = get_settings()
    if app_settings.allow_all_sites_for_extraction:
        return  # All sites allowed

    # Check if site is enabled in database
    site = database.get_site_by_extractor(extractor)
    if not site or not site.get("enabled", False):
        raise HTTPException(
            status_code=403,
            detail=(
                f"Extraction from '{extractor}' is not allowed. Enable this site in admin settings "
                "or enable 'Allow all sites for extraction'."
            ),
        )


@router.get("/videos/{video_id}", response_model=VideoResponse)
async def get_video(
    video_id: str,
    request: Request,
    proxy: Optional[bool] = Query(None, description="Override site proxy_streaming setting (true=proxy, false=direct)"),
    invidious: Optional[bool] = Query(
        None, description="Override INVIDIOUS_PROXY_VIDEOS config (true=use Invidious, false=use yt-dlp)"
    ),
):
    """Get video details including streams (Invidious-compatible).

    Args:
        video_id: YouTube video ID
        proxy: Override the site's proxy_streaming setting. If not provided, uses
               the YouTube site configuration. When true, stream URLs point to
               /proxy/fast/ for proxied downloads. When false, direct CDN URLs.
        invidious: Override the INVIDIOUS_PROXY_VIDEOS config setting. If not provided,
                   uses the config default.
    """
    # Validate that YouTube extraction is allowed
    validate_extractor_allowed("youtube")

    base_url = get_base_url(request)
    s = get_settings()

    # Get user_id for token generation if basic auth is enabled
    user = get_current_user_from_request(request)
    user_id = user.get("id") if user else None

    # Get proxy_streaming setting from YouTube site config
    site_config = database.get_site_by_extractor("youtube")
    site_proxy_streaming = site_config.get("proxy_streaming", True) if site_config else True

    # Query param overrides site config if explicitly provided
    proxy_streams = proxy if proxy is not None else site_proxy_streaming

    # Determine whether to use Invidious proxy (query param overrides config)
    use_invidious = invidious if invidious is not None else s.invidious_proxy_videos

    # Try Invidious proxy first if enabled
    if use_invidious and invidious_proxy.is_enabled():
        try:
            data = await invidious_proxy.get_video(video_id)
            if data:
                # Skip Invidious for live videos - use yt-dlp instead
                if data.get("liveNow", False):
                    pass  # Fall through to yt-dlp
                else:
                    invidious_base = invidious_proxy.get_base_url()
                    response = invidious_to_video_response(
                        data, base_url, proxy_streams=proxy_streams, invidious_base_url=invidious_base, user_id=user_id
                    )

                    # Schedule background avatar caching for this channel
                    channel_id = data.get("authorId")
                    if channel_id:
                        avatar_cache.get_cache().schedule_background_fetch(channel_id)

                    return response
        except invidious_proxy.InvidiousProxyError:
            pass  # Fall through to yt-dlp

    try:
        info = await get_video_info(video_id)
        response = ytdlp_to_video_response(info, base_url, proxy_streams=proxy_streams, user_id=user_id)

        # Schedule background avatar caching for this channel
        channel_id = info.get("channel_id")
        if channel_id:
            avatar_cache.get_cache().schedule_background_fetch(channel_id)

        # Fetch channel avatar if enabled and we have channel ID and no thumbnails yet
        if s.invidious_author_thumbnails:
            if channel_id and not response.authorThumbnails:
                # Try Invidious first
                thumbnails = await invidious_proxy.get_channel_thumbnails(channel_id)
                if thumbnails:
                    response.authorThumbnails = thumbnails
                else:
                    # Fall back to scraping
                    avatar_url = await get_channel_avatar(channel_id)
                    if avatar_url:
                        response.authorThumbnails = [
                            Thumbnail(quality="default", url=avatar_url, width=176, height=176)
                        ]

        return response
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except YtDlpError as e:
        raise HTTPException(status_code=404, detail=f"Video not found: {e}")
    except invidious_proxy.InvidiousProxyError as e:
        raise HTTPException(status_code=502, detail=f"Invidious error: {e}")
    except (KeyError, TypeError) as e:
        logger.error(f"[Videos] Unexpected error for {video_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/extract", response_model=VideoResponse)
async def extract_video_url(
    request: Request, url: str = Query(..., description="URL to extract video from (any site yt-dlp supports)")
):
    """Extract video details from any URL that yt-dlp supports.

    This endpoint accepts arbitrary URLs (Vimeo, Twitter, TikTok, etc.) and
    returns video information in the same format as /videos/{id}.

    The response includes:
    - `extractor`: Site identifier (e.g., "vimeo", "twitter")
    - `originalUrl`: The URL for re-extraction when stream URLs expire

    Note: Stream URLs from most sites expire after a few hours.

    Args:
        url: Full URL to extract (e.g., https://vimeo.com/12345)
    """
    # Validate URL format
    if not is_valid_url(url):
        raise HTTPException(status_code=400, detail="Invalid URL format")

    # SSRF prevention - block requests to private/internal networks
    if not is_safe_url(url):
        raise HTTPException(status_code=403, detail="URL targets restricted network resources")

    base_url = get_base_url(request)

    # Get user_id for token generation if basic auth is enabled
    user = get_current_user_from_request(request)
    user_id = user.get("id") if user else None

    try:
        info = await extract_url(url)

        # Check site configuration for proxy_streaming setting
        extractor = info.get("extractor", "")

        # Validate that this extractor is allowed
        validate_extractor_allowed(extractor)

        site_config = database.get_site_by_extractor(extractor)
        proxy_streams = site_config.get("proxy_streaming", True) if site_config else True

        response = ytdlp_to_video_response(
            info, base_url, proxy_streams=proxy_streams, original_url=url, user_id=user_id
        )
        return response
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except YtDlpError as e:
        raise HTTPException(status_code=422, detail=f"Could not extract video: {e}")
    except (KeyError, TypeError) as e:
        logger.error(f"[Videos] Unexpected error extracting {url}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/extract/channel", response_model=ChannelExtractResponse)
async def extract_channel(
    url: str = Query(..., description="Channel/user URL to extract videos from (any site yt-dlp supports)"),
    page: int = Query(1, ge=1, description="Page number (1-based)"),
):
    """Extract videos from a channel/user page on any site that yt-dlp supports.

    This endpoint accepts channel/user URLs (Vimeo, Dailymotion, TikTok, etc.)
    and returns a list of videos from that channel.

    The response includes:
    - `author`: Channel/user name
    - `authorId`: Channel/user identifier
    - `authorUrl`: The channel URL (for re-extraction)
    - `extractor`: Site name (e.g., "Vimeo", "Dailymotion")
    - `videos`: List of videos with metadata
    - `continuation`: Next page number as string, or null if no more pages

    Note: Not all sites support channel extraction. If extraction fails,
    a 422 error is returned with details.

    Args:
        url: Full channel/user URL (e.g., https://vimeo.com/username)
        page: Page number (default: 1)
    """
    # Validate URL format
    if not is_valid_url(url):
        raise HTTPException(status_code=400, detail="Invalid URL format")

    # SSRF prevention - block requests to private/internal networks
    if not is_safe_url(url):
        raise HTTPException(status_code=403, detail="URL targets restricted network resources")

    try:
        info = await extract_channel_url(url, page=page)

        # Validate that this extractor is allowed
        extractor = info.get("extractor", "generic")
        validate_extractor_allowed(extractor)

        # Convert entries to VideoListItem
        videos = []
        for entry in info.get("entries", []):
            try:
                videos.append(ytdlp_to_video_list_item(entry))
            except (KeyError, TypeError, ValueError):
                continue  # Skip entries that fail to convert

        # Determine if there are more pages (if we got a full page, there might be more)
        per_page = 30
        continuation = str(page + 1) if len(videos) >= per_page else None

        return ChannelExtractResponse(
            author=info.get("channel", ""),
            authorId=info.get("channel_id", ""),
            authorUrl=info.get("channel_url", url),
            extractor=info.get("extractor", "generic"),
            videos=videos,
            continuation=continuation,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except YtDlpError as e:
        raise HTTPException(status_code=422, detail=f"Could not extract channel: {e}")
    except (KeyError, TypeError) as e:
        logger.error(f"[Videos] Unexpected error extracting channel {url}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
