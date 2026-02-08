"""Invidious proxy client for fallback endpoints."""

import asyncio
import logging
import urllib.parse
from typing import Any, List, Optional

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

from converters import resolve_invidious_url
from models import Thumbnail
from settings import get_settings
from ytdlp_wrapper import YtDlpError

# Router for companion proxy endpoints
router = APIRouter(tags=["companion"])

# Configure logging
logger = logging.getLogger("invidious_proxy")

# Shared HTTP client for connection pooling
_client: Optional[httpx.AsyncClient] = None
_client_timeout: Optional[int] = None


async def get_client() -> httpx.AsyncClient:
    """Get or create the shared HTTP client."""
    global _client, _client_timeout
    s = get_settings()
    # Recreate client if timeout setting changed
    if _client is None or _client.is_closed or _client_timeout != s.invidious_timeout:
        if _client is not None and not _client.is_closed:
            await _client.aclose()
        _client = httpx.AsyncClient(timeout=httpx.Timeout(s.invidious_timeout), follow_redirects=True)
        _client_timeout = s.invidious_timeout
    return _client


def is_enabled() -> bool:
    """Check if Invidious proxy is configured and enabled."""
    s = get_settings()
    if not s.invidious_enabled:
        return False
    return s.invidious_instance is not None and s.invidious_instance.strip() != ""


def get_base_url() -> str:
    """Get the Invidious instance base URL.

    The URL is admin-configured and trusted — SSRF checks are
    applied only to user-supplied URLs at their respective endpoints.
    """
    s = get_settings()
    if not s.invidious_instance:
        return ""
    return s.invidious_instance.rstrip("/")


async def fetch_json(endpoint: str) -> Any:
    """Fetch JSON from Invidious API endpoint with retry logic.

    Retries transient errors (500, 502, 503, 504, 408, 429, timeouts)
    with exponential backoff. Non-retryable errors (400, 401, 403, 404, 414)
    are raised immediately.
    """
    if not is_enabled():
        return None

    base = get_base_url()
    if not base:
        raise InvidiousProxyError("Invidious instance URL validation failed (DNS or SSRF check)")

    client = await get_client()
    url = f"{base}{endpoint}"
    s = get_settings()

    max_retries = s.invidious_max_retries
    base_delay = s.invidious_retry_delay
    last_error: Optional[InvidiousProxyError] = None

    for attempt in range(max_retries + 1):  # +1 for initial attempt
        if attempt > 0:
            delay = base_delay * (2 ** (attempt - 1))  # Exponential backoff
            logger.info(f"[Invidious] Retry {attempt}/{max_retries} for {endpoint} after {delay:.1f}s")
            await asyncio.sleep(delay)

        logger.info(f"[Invidious] Proxy request: {endpoint}" + (f" (attempt {attempt + 1})" if attempt > 0 else ""))

        try:
            response = await client.get(url)
            response.raise_for_status()
            logger.info(f"[Invidious] Proxy success: {endpoint} ({response.status_code})")
            return response.json()
        except httpx.HTTPStatusError as e:
            status_code = e.response.status_code
            error_msg = f"HTTP {status_code}: {e.response.text[:200]}"
            logger.warning(f"[Invidious] Proxy error: {endpoint} - {error_msg}")
            last_error = InvidiousProxyError.from_http_status(status_code, error_msg)

            # Don't retry non-retryable errors
            if not last_error.is_retryable:
                raise last_error

        except httpx.TimeoutException as e:
            error_msg = f"Timeout: {e}"
            logger.warning(f"[Invidious] Proxy timeout: {endpoint} - {e}")
            last_error = InvidiousProxyError.from_connection_error(error_msg)

        except httpx.RequestError as e:
            error_msg = f"Request failed: {e}"
            logger.warning(f"[Invidious] Proxy error: {endpoint} - {e}")
            last_error = InvidiousProxyError.from_connection_error(error_msg)

        except (ValueError, TypeError) as e:
            error_msg = f"Unexpected error: {e}"
            logger.warning(f"[Invidious] Proxy error: {endpoint} - {e}")
            # Unexpected errors are not retryable
            raise InvidiousProxyError(error_msg, status_code=None, is_retryable=False)

    # All retries exhausted
    logger.warning(f"[Invidious] All {max_retries} retries exhausted for {endpoint}")
    if last_error:
        raise last_error
    raise InvidiousProxyError(f"Failed after {max_retries} retries", is_retryable=True)


async def get_trending(region: str = "US") -> List[dict]:
    """Get trending videos from Invidious."""
    data = await fetch_json(f"/api/v1/trending?region={region}")
    return data if isinstance(data, list) else []


async def get_popular() -> List[dict]:
    """Get popular videos from Invidious."""
    data = await fetch_json("/api/v1/popular")
    return data if isinstance(data, list) else []


async def get_search_suggestions(query: str) -> List[str]:
    """Get search suggestions from Invidious."""
    encoded_query = urllib.parse.quote(query)
    data = await fetch_json(f"/api/v1/search/suggestions?q={encoded_query}")

    if isinstance(data, dict) and "suggestions" in data:
        return data["suggestions"]
    return []


async def search(query: str, type: str = "video", page: int = 1) -> List[dict]:
    """Search using Invidious API.

    Args:
        query: Search query string
        type: Result type - "video", "channel", or "playlist"
        page: Page number (1-based)

    Returns:
        List of search results matching the specified type
    """
    encoded_query = urllib.parse.quote(query)
    data = await fetch_json(f"/api/v1/search?q={encoded_query}&type={type}&page={page}")
    return data if isinstance(data, list) else []


async def get_channel(channel_id: str) -> Optional[dict]:
    """Get channel info from Invidious."""
    encoded_id = urllib.parse.quote(channel_id)
    return await fetch_json(f"/api/v1/channels/{encoded_id}")


async def get_channel_thumbnails(channel_id: str) -> List[Thumbnail]:
    """Get channel/author thumbnails from Invidious.

    Args:
        channel_id: The channel ID to fetch thumbnails for

    Returns:
        List of Thumbnail objects, empty if not available or error occurs
    """
    if not is_enabled():
        return []

    try:
        channel_data = await get_channel(channel_id)
        if channel_data and "authorThumbnails" in channel_data:
            invidious_base = get_base_url()
            thumbnails = []
            for thumb in channel_data.get("authorThumbnails", []):
                thumbnails.append(
                    Thumbnail(
                        quality=thumb.get("quality", "default"),
                        url=resolve_invidious_url(thumb.get("url", ""), invidious_base),
                        width=thumb.get("width"),
                        height=thumb.get("height"),
                    )
                )
            return thumbnails
    except InvidiousProxyError:
        pass

    return []


async def get_video(video_id: str) -> Optional[dict]:
    """Get video info from Invidious."""
    encoded_id = urllib.parse.quote(video_id)
    return await fetch_json(f"/api/v1/videos/{encoded_id}")


async def get_playlist(playlist_id: str) -> Optional[dict]:
    """Get playlist info from Invidious."""
    encoded_id = urllib.parse.quote(playlist_id)
    return await fetch_json(f"/api/v1/playlists/{encoded_id}")


async def _fetch_channel_tab(channel_id: str, tab: str, continuation: Optional[str] = None) -> dict:
    """Fetch a channel tab from Invidious API.

    Args:
        channel_id: The channel ID
        tab: Tab name (videos, playlists, shorts, streams, channels)
        continuation: Optional continuation token for pagination

    Returns:
        Response dict from Invidious API
    """
    encoded_id = urllib.parse.quote(channel_id)
    endpoint = f"/api/v1/channels/{encoded_id}/{tab}"
    if continuation:
        endpoint += f"?continuation={urllib.parse.quote(continuation)}"
    return await fetch_json(endpoint)


async def get_channel_videos(channel_id: str, continuation: Optional[str] = None) -> dict:
    """Get channel videos from Invidious."""
    return await _fetch_channel_tab(channel_id, "videos", continuation)


async def get_channel_videos_multi_page(channel_id: str, max_videos: int = 60) -> dict:
    """Get channel videos from Invidious with automatic pagination.

    Invidious returns ~60 videos per page. This function automatically
    fetches multiple pages if needed to reach the desired max_videos count.

    Note: Due to Invidious continuation token length limitations (can cause 414 errors),
    pagination may stop before reaching max_videos if continuation tokens become too long.

    Args:
        channel_id: The channel ID to fetch videos from
        max_videos: Maximum number of videos to fetch (default: 60)

    Returns:
        Dict with keys:
            - videos: List of video dicts from Invidious
            - total_fetched: Total number of videos retrieved
            - pages_fetched: Number of API calls made
            - pagination_limited: True if pagination stopped before reaching max_videos
            - limit_reason: Reason pagination stopped ("414_error", "no_continuation", "max_reached")
    """
    all_videos = []
    continuation = None
    page_count = 0
    pagination_limited = False
    limit_reason = None

    # Keep fetching pages until we have enough videos or no more pages
    while len(all_videos) < max_videos:
        page_count += 1

        try:
            data = await get_channel_videos(channel_id, continuation)
        except InvidiousProxyError as e:
            # Handle 414 URI Too Large errors (continuation tokens can be extremely long)
            if "414" in str(e):
                token_length = len(continuation) if continuation else 0
                logger.warning(
                    f"[Invidious Multi-Page] {channel_id}: 414 URI Too Large on page {page_count}, "
                    f"stopping at {len(all_videos)} videos. Token length: ~{token_length} chars"
                )
                pagination_limited = True
                limit_reason = "414_error"
                break
            # Re-raise other errors
            raise

        if not data or "videos" not in data:
            logger.debug(f"[Invidious Multi-Page] {channel_id}: No data on page {page_count}, stopping")
            limit_reason = "no_data"
            break

        videos = data.get("videos", [])
        if not videos:
            logger.debug(f"[Invidious Multi-Page] {channel_id}: No videos on page {page_count}, stopping")
            limit_reason = "no_videos"
            break

        all_videos.extend(videos)
        logger.debug(
            f"[Invidious Multi-Page] {channel_id}: Page {page_count} fetched "
            f"{len(videos)} videos, total: {len(all_videos)}/{max_videos}"
        )

        # Check if there's a continuation token for next page
        continuation = data.get("continuation")
        if not continuation:
            # No more pages available
            logger.debug(
                f"[Invidious Multi-Page] {channel_id}: No continuation token, "
                f"channel has {len(all_videos)} videos total"
            )
            limit_reason = "no_continuation"
            break

    # Determine final status
    result_count = len(all_videos)
    if result_count >= max_videos:
        limit_reason = "max_reached"

    if result_count > 0:
        logger.info(
            f"[Invidious Multi-Page] {channel_id}: Fetched {result_count} videos "
            f"using {page_count} API call(s) [reason: {limit_reason}]"
        )

    # Return videos and metadata
    return {
        "videos": all_videos[:max_videos],
        "total_fetched": result_count,
        "pages_fetched": page_count,
        "pagination_limited": pagination_limited,
        "limit_reason": limit_reason,
    }


async def get_comments(video_id: str, continuation: Optional[str] = None) -> Optional[dict]:
    """Get video comments from Invidious."""
    encoded_id = urllib.parse.quote(video_id)
    endpoint = f"/api/v1/comments/{encoded_id}"
    if continuation:
        endpoint += f"?continuation={urllib.parse.quote(continuation)}"
    return await fetch_json(endpoint)


async def get_channel_playlists(channel_id: str, continuation: Optional[str] = None) -> dict:
    """Get channel playlists from Invidious."""
    return await _fetch_channel_tab(channel_id, "playlists", continuation)


async def get_channel_shorts(channel_id: str, continuation: Optional[str] = None) -> dict:
    """Get channel shorts from Invidious."""
    return await _fetch_channel_tab(channel_id, "shorts", continuation)


async def get_channel_streams(channel_id: str, continuation: Optional[str] = None) -> dict:
    """Get channel past live streams from Invidious."""
    return await _fetch_channel_tab(channel_id, "streams", continuation)


async def search_channel(channel_id: str, query: str, page: int = 1) -> dict:
    """Search within a channel using Invidious API.

    Args:
        channel_id: YouTube channel ID (UC...) or handle (@name)
        query: Search query string
        page: Page number (1-based)

    Returns:
        Dict with 'videos' list and optional 'continuation' token
    """
    encoded_id = urllib.parse.quote(channel_id)
    encoded_query = urllib.parse.quote(query)
    endpoint = f"/api/v1/channels/{encoded_id}/search?q={encoded_query}&page={page}"
    return await fetch_json(endpoint)


class InvidiousProxyError(Exception):
    """Error from Invidious proxy."""

    def __init__(self, message: str, status_code: Optional[int] = None, is_retryable: bool = False):
        super().__init__(message)
        self.status_code = status_code
        self.is_retryable = is_retryable

    @classmethod
    def from_http_status(cls, status_code: int, message: str) -> "InvidiousProxyError":
        """Create error from HTTP status code with automatic retryable detection."""
        retryable_codes = {500, 502, 503, 504, 408, 429}
        return cls(message, status_code=status_code, is_retryable=status_code in retryable_codes)

    @classmethod
    def from_connection_error(cls, message: str) -> "InvidiousProxyError":
        """Create error from connection/timeout error (always retryable)."""
        return cls(message, status_code=None, is_retryable=True)


@router.get("/captions/{video_id}")
async def get_captions(video_id: str, request: Request, token: str = None):
    """Get available captions for a video.

    If invidious_proxy_captions is enabled and Invidious is configured,
    proxies to Invidious's /companion endpoint. Otherwise, uses yt-dlp
    to get caption info directly.

    Args:
        token: Authentication token (required when basic auth is enabled)

    Returns JSON list of available captions.
    """
    # Validate token if basic auth is enabled
    user_id = _validate_resource_token(token, video_id)

    s = get_settings()

    # Use Invidious if enabled and configured
    if s.invidious_proxy_captions and is_enabled():
        client = await get_client()

        # Build URL with /companion prefix for Invidious, stripping our token param
        params = {k: v for k, v in request.query_params.items() if k != "token"}
        query_string = urllib.parse.urlencode(params)
        url = f"{get_base_url()}/companion/api/v1/captions/{video_id}"
        if query_string:
            url = f"{url}?{query_string}"

        logger.info(f"[Captions] Invidious proxy request: {video_id}")

        try:
            response = await client.get(url)

            headers = {}
            if "content-type" in response.headers:
                headers["content-type"] = response.headers["content-type"]

            return Response(content=response.content, status_code=response.status_code, headers=headers)
        except httpx.HTTPStatusError as e:
            logger.warning(f"[Captions] Invidious error: {video_id} - HTTP {e.response.status_code}")
            raise HTTPException(status_code=e.response.status_code, detail=str(e))
        except httpx.RequestError as e:
            logger.warning(f"[Captions] Invidious error: {video_id} - {e}")
            raise HTTPException(status_code=502, detail=f"Upstream error: {e}")
        except (ValueError, KeyError, TypeError) as e:
            logger.warning(f"[Captions] Invidious error: {video_id} - {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    # Use yt-dlp directly
    logger.info(f"[Captions] yt-dlp request: {video_id}")

    try:
        import ytdlp_wrapper
        from converters import convert_captions
        from utils import get_base_url as get_request_base_url

        info = await ytdlp_wrapper.get_video_info(video_id)

        # Get base URL for proxy endpoints
        base_url = get_request_base_url(request)

        captions = convert_captions(
            info.get("subtitles"), info.get("automatic_captions"), video_id, base_url, user_id=user_id
        )

        # Return in Invidious-compatible format
        return {"captions": [c.model_dump() for c in captions]}

    except ValueError as e:
        logger.warning(f"[Captions] Invalid video ID: {video_id} - {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except YtDlpError as e:
        logger.warning(f"[Captions] yt-dlp error: {video_id} - {e}")
        raise HTTPException(status_code=502, detail=str(e))
    except (KeyError, TypeError) as e:
        logger.warning(f"[Captions] yt-dlp error: {video_id} - {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


def _validate_resource_token(token: Optional[str], video_id: str) -> Optional[int]:
    """Validate resource token when authentication is required.

    Used by thumbnails, captions list, and caption content endpoints.

    Args:
        token: The token from query parameter
        video_id: The video ID being accessed

    Returns:
        The user_id from the token, or None if auth is not required

    Raises:
        HTTPException: If auth is required and token is invalid
    """
    import database
    import tokens

    # Check if any users exist (auth is required when users exist)
    if not database.has_any_user():
        return None  # No auth required (setup not complete)

    # Users exist, token is required
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required. Missing token.")

    is_valid, user_id, error = tokens.validate_stream_token(token, video_id)
    if not is_valid:
        raise HTTPException(status_code=401, detail=f"Invalid token: {error}")

    return user_id


@router.get("/captions/{video_id}/content")
async def get_caption_content(
    video_id: str,
    request: Request,
    lang: str = None,
    auto: bool = False,
    format: str = "vtt",
    token: str = None,
):
    """Proxy caption content for a video.

    Args:
        video_id: YouTube video ID
        lang: Language code (required)
        auto: Use auto-generated captions (default: false)
        format: Output format - vtt, srv1, json3 (default: vtt)
        token: Authentication token (required when basic auth is enabled)
    """
    if not lang:
        raise HTTPException(status_code=400, detail="lang parameter is required")

    # Validate token if basic auth is enabled
    _validate_resource_token(token, video_id)

    logger.info(f"[Captions] Content request: {video_id} lang={lang} auto={auto} format={format}")

    try:
        import ytdlp_wrapper

        content, content_type = await ytdlp_wrapper.fetch_caption_content(
            video_id, lang, auto_generated=auto, format=format
        )

        if not content:
            logger.warning(f"[Captions] 404 for {video_id} lang={lang} auto={auto} format={format}")
            raise HTTPException(status_code=404, detail=f"Caption not found: lang={lang}, auto={auto}")

        return Response(
            content=content,
            media_type=content_type,
            headers={"Content-Disposition": f'inline; filename="{video_id}_{lang}.{format}"'},
        )

    except ValueError as e:
        logger.warning(f"[Captions] Invalid video ID: {video_id} - {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except YtDlpError as e:
        logger.warning(f"[Captions] Content fetch error: {video_id} - {e}")
        raise HTTPException(status_code=502, detail=str(e))
    except (KeyError, TypeError, OSError) as e:
        logger.warning(f"[Captions] Content fetch error: {video_id} - {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/storyboards/{video_id}")
async def proxy_storyboards(video_id: str, request: Request):
    """Proxy storyboard requests to Invidious.

    This endpoint handles /api/v1/storyboards/{video_id} and proxies to
    {invidious}/api/v1/storyboards/{video_id}.
    """
    if not is_enabled():
        raise HTTPException(status_code=503, detail="Invidious proxy not configured")

    client = await get_client()

    query_string = str(request.query_params)
    url = f"{get_base_url()}/api/v1/storyboards/{video_id}"
    if query_string:
        url = f"{url}?{query_string}"

    logger.info(f"[Storyboards] Proxy request: {video_id}")

    try:
        response = await client.get(url)

        headers = {}
        if "content-type" in response.headers:
            headers["content-type"] = response.headers["content-type"]

        return Response(content=response.content, status_code=response.status_code, headers=headers)
    except httpx.HTTPStatusError as e:
        logger.warning(f"[Storyboards] Proxy error: {video_id} - HTTP {e.response.status_code}")
        raise HTTPException(status_code=e.response.status_code, detail=str(e))
    except httpx.RequestError as e:
        logger.warning(f"[Storyboards] Proxy error: {video_id} - {e}")
        raise HTTPException(status_code=502, detail=f"Upstream error: {e}")
    except (ValueError, KeyError, TypeError) as e:
        logger.warning(f"[Storyboards] Proxy error: {video_id} - {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/thumbnails/{video_id}/{filename}")
async def proxy_thumbnail(video_id: str, filename: str, request: Request, token: str = None):
    """Proxy thumbnail requests to Invidious.

    This endpoint handles /api/v1/thumbnails/{video_id}/{filename} and proxies to
    {invidious}/vi/{video_id}/{filename}.

    Thumbnail filenames are typically: maxres.jpg, maxresdefault.jpg, sddefault.jpg,
    hqdefault.jpg, mqdefault.jpg, default.jpg, 1.jpg, 2.jpg, 3.jpg

    Args:
        token: Authentication token (required when basic auth is enabled)
    """
    # Validate token if basic auth is enabled
    _validate_resource_token(token, video_id)

    if not is_enabled():
        raise HTTPException(status_code=503, detail="Invidious proxy not configured")

    client = await get_client()

    # Build URL: {invidious}/vi/{video_id}/{filename}
    url = f"{get_base_url()}/vi/{video_id}/{filename}"

    logger.info(f"[Thumbnails] Proxy request: {video_id}/{filename}")

    try:
        response = await client.get(url)

        headers = {}
        if "content-type" in response.headers:
            headers["content-type"] = response.headers["content-type"]
        if "cache-control" in response.headers:
            headers["cache-control"] = response.headers["cache-control"]

        return Response(content=response.content, status_code=response.status_code, headers=headers)
    except httpx.HTTPStatusError as e:
        logger.warning(f"[Thumbnails] Proxy error: {video_id}/{filename} - HTTP {e.response.status_code}")
        raise HTTPException(status_code=e.response.status_code, detail=str(e))
    except httpx.RequestError as e:
        logger.warning(f"[Thumbnails] Proxy error: {video_id}/{filename} - {e}")
        raise HTTPException(status_code=502, detail=f"Upstream error: {e}")
    except (ValueError, KeyError, TypeError) as e:
        logger.warning(f"[Thumbnails] Proxy error: {video_id}/{filename} - {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
