"""Async wrapper for yt-dlp subprocess execution."""

from ytdlp_wrapper._cache import (
    get_channel_cache,
    get_extract_cache,
    get_search_cache,
    get_video_cache,
    reset_caches,
)
from ytdlp_wrapper._captions import fetch_caption_content, get_caption_url
from ytdlp_wrapper._core import (
    _separate_flags_and_urls,
    run_ytdlp,
)
from ytdlp_wrapper._extract import extract_channel_url, extract_url
from ytdlp_wrapper._sanitize import (
    YtDlpError,
    is_safe_url,
    is_valid_url,
    sanitize_channel_id,
    sanitize_extension,
    sanitize_format_id,
    sanitize_playlist_id,
    sanitize_video_id,
)
from ytdlp_wrapper._youtube import (
    build_search_sp,
    get_channel_avatar,
    get_channel_info,
    get_channel_tab,
    get_channel_videos,
    get_playlist_info,
    get_video_info,
    search_channel,
    search_videos,
)

__all__ = [
    # _cache
    "get_video_cache",
    "get_search_cache",
    "get_channel_cache",
    "get_extract_cache",
    "reset_caches",
    # _sanitize
    "YtDlpError",
    "sanitize_video_id",
    "sanitize_channel_id",
    "sanitize_playlist_id",
    "is_valid_url",
    "is_safe_url",
    "sanitize_format_id",
    "sanitize_extension",
    # _core
    "_separate_flags_and_urls",
    "run_ytdlp",
    # _youtube
    "build_search_sp",
    "get_video_info",
    "search_videos",
    "get_channel_info",
    "get_channel_avatar",
    "get_channel_videos",
    "get_playlist_info",
    "get_channel_tab",
    "search_channel",
    # _extract
    "extract_url",
    "extract_channel_url",
    # _captions
    "get_caption_url",
    "fetch_caption_content",
]
