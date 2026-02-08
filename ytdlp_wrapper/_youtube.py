"""YouTube-specific operations: video, search, channel, playlist, tab."""

import base64
import json
import logging
import urllib.parse
from typing import List, Optional

from ytdlp_wrapper._cache import get_channel_cache, get_search_cache, get_video_cache
from ytdlp_wrapper._core import run_ytdlp
from ytdlp_wrapper._sanitize import sanitize_channel_id, sanitize_playlist_id, sanitize_video_id

logger = logging.getLogger(__name__)


def build_search_sp(
    sort: Optional[str] = None, date: Optional[str] = None, duration: Optional[str] = None
) -> Optional[str]:
    """Build YouTube search sp parameter from filters.

    The sp parameter is a base64-encoded protobuf message that encodes
    sort order and filter options for YouTube search.

    Args:
        sort: Sort order - "date", "views", or "rating"
        date: Upload date filter - "hour", "today", "week", "month", "year"
        duration: Duration filter - "short", "medium", "long"

    Returns:
        Base64-encoded sp parameter, or None if no filters specified
    """
    SORT_MAP = {"date": 2, "views": 3, "rating": 4}
    DATE_MAP = {"hour": 1, "today": 2, "week": 3, "month": 4, "year": 5}
    DURATION_MAP = {"short": 1, "long": 2, "medium": 3}

    # Check if any filters are actually specified
    has_sort = sort and sort in SORT_MAP
    has_date = date and date in DATE_MAP
    has_duration = duration and duration in DURATION_MAP

    if not has_sort and not has_date and not has_duration:
        return None

    data = bytearray()

    # Field 1 (0x08): sort order
    if has_sort:
        data.extend([0x08, SORT_MAP[sort]])

    # Field 2 (0x12): filters submessage (only if date or duration specified)
    if has_date or has_duration:
        filters = bytearray()
        if has_date:
            filters.extend([0x08, DATE_MAP[date]])
        filters.extend([0x10, 0x01])  # type=video (required when using filters)
        if has_duration:
            filters.extend([0x18, DURATION_MAP[duration]])

        data.extend([0x12, len(filters)])
        data.extend(filters)

    return base64.b64encode(data).decode() if data else None


async def get_video_info(video_id: str, use_cache: bool = True) -> dict:
    """Get full video info including formats."""
    video_id = sanitize_video_id(video_id)

    cache_key = f"video:{video_id}"
    video_cache = get_video_cache()
    if use_cache and cache_key in video_cache:
        return video_cache[cache_key]

    stdout = await run_ytdlp(
        "-j",
        "--no-download",
        "--no-warnings",
        "--no-playlist",
        "--remote-components",
        "ejs:github",  # Required for JS challenge solving
        f"https://www.youtube.com/watch?v={video_id}",
    )

    info = json.loads(stdout)
    video_cache[cache_key] = info
    return info


async def search_videos(
    query: str, count: int = 20, sort: Optional[str] = None, date: Optional[str] = None, duration: Optional[str] = None
) -> List[dict]:
    """Search for videos with optional sorting and filtering.

    Args:
        query: Search query string
        count: Maximum number of results to return
        sort: Sort order - "relevance" (default), "date", "views", "rating"
        date: Upload date filter - "hour", "today", "week", "month", "year"
        duration: Duration filter - "short", "medium", "long"

    Returns:
        List of video info dictionaries
    """
    from settings import get_settings

    s = get_settings()
    count = min(count, s.max_search_results)

    cache_key = f"search:{query}:{count}:{sort}:{date}:{duration}"
    search_cache = get_search_cache()
    if cache_key in search_cache:
        return search_cache[cache_key]

    # Build search URL with filters
    sp = build_search_sp(sort, date, duration)

    if sp:
        # Use YouTube search URL with sp parameter for filtered searches
        encoded_query = urllib.parse.quote(query)
        url = f"https://www.youtube.com/results?search_query={encoded_query}&sp={urllib.parse.quote(sp)}"
        stdout = await run_ytdlp("-j", "--flat-playlist", "--no-warnings", "--playlist-items", f"1:{count}", url)
    else:
        # Use ytsearch for default relevance sort without filters
        stdout = await run_ytdlp("-j", "--flat-playlist", "--no-warnings", f"ytsearch{count}:{query}")

    results = []
    for line in stdout.strip().split("\n"):
        if line:
            try:
                results.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    search_cache[cache_key] = results
    return results


async def get_channel_info(channel_id: str) -> dict:
    """Get channel info by fetching a video from the channel."""
    channel_id = sanitize_channel_id(channel_id)

    cache_key = f"channel:{channel_id}"
    channel_cache = get_channel_cache()
    if cache_key in channel_cache:
        return channel_cache[cache_key]

    # Build channel videos URL
    if channel_id.startswith("@"):
        url = f"https://www.youtube.com/{channel_id}/videos"
    elif channel_id.startswith("UC"):
        url = f"https://www.youtube.com/channel/{channel_id}/videos"
    else:
        url = channel_id

    # Fetch full info from first video to get channel metadata (subscriber count, etc.)
    stdout = await run_ytdlp(
        "-j", "--no-download", "--no-warnings", "--playlist-items", "1", "--remote-components", "ejs:github", url
    )

    if not stdout.strip():
        # Fallback: try flat-playlist for basic info
        stdout = await run_ytdlp("-j", "--flat-playlist", "--playlist-items", "1", "--no-warnings", url)

    info = json.loads(stdout.strip().split("\n")[0]) if stdout.strip() else {}
    channel_cache[cache_key] = info
    return info


async def get_channel_avatar(channel_id: str) -> Optional[str]:
    """Fetch channel avatar URL.

    Note: YouTube channel avatars are not available through yt-dlp and
    require either YouTube Data API or scraping. Scraping is unreliable
    due to consent pages and JavaScript requirements. For now, return None
    and let the client handle missing avatars gracefully.

    Future: Could proxy through an Invidious instance if available on
    the same Docker network, or use YouTube Data API with an API key.
    """
    # Channel avatars not available without YouTube API or complex scraping
    # Yattee handles missing avatars gracefully with placeholder images
    return None


async def get_channel_videos(channel_id: str, page: int = 1, per_page: int = 30) -> List[dict]:
    """Get channel videos with pagination."""
    channel_id = sanitize_channel_id(channel_id)

    # Build channel videos URL
    if channel_id.startswith("@"):
        url = f"https://www.youtube.com/{channel_id}/videos"
    elif channel_id.startswith("UC"):
        url = f"https://www.youtube.com/channel/{channel_id}/videos"
    else:
        url = channel_id

    # Calculate which items to fetch
    start = (page - 1) * per_page + 1
    end = start + per_page - 1

    stdout = await run_ytdlp("-j", "--flat-playlist", "--no-warnings", "--playlist-items", f"{start}:{end}", url)

    results = []
    for line in stdout.strip().split("\n"):
        if line:
            try:
                results.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    return results


async def get_playlist_info(playlist_id: str) -> dict:
    """Get playlist info and videos."""
    playlist_id = sanitize_playlist_id(playlist_id)

    stdout = await run_ytdlp(
        "--dump-single-json", "--flat-playlist", "--no-warnings", f"https://www.youtube.com/playlist?list={playlist_id}"
    )

    # --dump-single-json returns a single JSON object with playlist metadata
    # (including description) and entries array
    return json.loads(stdout)


async def get_channel_tab(channel_id: str, tab: str, page: int = 1, per_page: int = 30) -> List[dict]:
    """Get channel tab content (playlists, shorts, streams).

    Args:
        channel_id: Channel ID (UC...) or handle (@name)
        tab: Tab name - "playlists", "shorts", or "streams"
        page: Page number (1-based)
        per_page: Results per page

    Returns:
        List of items from the specified tab
    """
    channel_id = sanitize_channel_id(channel_id)

    # Build channel tab URL
    if channel_id.startswith("@"):
        url = f"https://www.youtube.com/{channel_id}/{tab}"
    elif channel_id.startswith("UC"):
        url = f"https://www.youtube.com/channel/{channel_id}/{tab}"
    else:
        url = channel_id

    # Calculate which items to fetch
    start = (page - 1) * per_page + 1
    end = start + per_page - 1

    stdout = await run_ytdlp("-j", "--flat-playlist", "--no-warnings", "--playlist-items", f"{start}:{end}", url)

    results = []
    for line in stdout.strip().split("\n"):
        if line:
            try:
                results.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    return results


async def search_channel(channel_id: str, query: str, page: int = 1, per_page: int = 20) -> List[dict]:
    """Search for videos within a channel.

    Works by using YouTube's channel search URL:
    https://www.youtube.com/channel/{channel_id}/search?query={query}

    For non-YouTube channels, attempts to use the channel URL with search query appended,
    though this may not work for all platforms.

    Args:
        channel_id: Channel ID (UC...) or handle (@name) or full URL
        query: Search query string
        page: Page number (1-based)
        per_page: Results per page (default 20)

    Returns:
        List of video info dictionaries
    """
    channel_id = sanitize_channel_id(channel_id)

    # Build channel search URL
    if channel_id.startswith("@"):
        url = f"https://www.youtube.com/{channel_id}/search?query={urllib.parse.quote(query)}"
    elif channel_id.startswith("UC"):
        url = f"https://www.youtube.com/channel/{channel_id}/search?query={urllib.parse.quote(query)}"
    elif channel_id.startswith(("http://", "https://")):
        # For full URLs (non-YouTube), append search query if supported
        # Most platforms don't support channel search via URL, but we try
        url = f"{channel_id}/search?query={urllib.parse.quote(query)}"
    else:
        # Assume it's a non-standard ID, try as YouTube channel
        url = f"https://www.youtube.com/channel/{channel_id}/search?query={urllib.parse.quote(query)}"

    # Calculate pagination
    start = (page - 1) * per_page + 1
    end = start + per_page - 1

    stdout = await run_ytdlp("-j", "--flat-playlist", "--no-warnings", "--playlist-items", f"{start}:{end}", url)

    results = []
    for line in stdout.strip().split("\n"):
        if line:
            try:
                data = json.loads(line)
                # Filter out playlists (channel search can return mixed results)
                # Only include videos (ie_key == "Youtube" or no ie_key for non-YouTube)
                ie_key = data.get("ie_key", "")
                if ie_key in ("Youtube", "YoutubeTab", "") or "_type" not in data:
                    # Skip playlist entries (YoutubeTab with _type == 'playlist')
                    if data.get("_type") == "playlist":
                        continue
                    results.append(data)
            except json.JSONDecodeError:
                continue

    return results
