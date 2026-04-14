"""InnerTube - Direct YouTube API client.

Provides access to YouTube data without requiring an Invidious instance.
"""

from innertube._browse import (
    get_channel_info,
    get_channel_playlists,
    get_channel_shorts,
    get_channel_streams,
    get_channel_videos,
    get_popular,
    get_trending,
)
from innertube._client import InnerTubeError, get_client, innertube_get, innertube_post
from innertube._comments import get_comments
from innertube._playlists import get_playlist
from innertube._search import search, search_channel
from innertube._suggestions import get_search_suggestions
from innertube._thumbnails import proxy_thumbnail


def is_enabled() -> bool:
    """Check if InnerTube is enabled in settings."""
    from settings import get_settings

    return get_settings().innertube_enabled


__all__ = [
    "InnerTubeError",
    "get_channel_info",
    "get_channel_playlists",
    "get_channel_shorts",
    "get_channel_streams",
    "get_channel_videos",
    "get_client",
    "get_comments",
    "get_playlist",
    "get_popular",
    "get_search_suggestions",
    "get_trending",
    "innertube_get",
    "innertube_post",
    "is_enabled",
    "proxy_thumbnail",
    "search",
    "search_channel",
]
