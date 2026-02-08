"""TTLCache instances and cache management."""

import logging
from typing import Optional

from cachetools import TTLCache

from settings import get_settings

logger = logging.getLogger(__name__)

# Lazy-initialized caches for different content types
_video_cache: Optional[TTLCache] = None
_search_cache: Optional[TTLCache] = None
_channel_cache: Optional[TTLCache] = None
_extract_cache: Optional[TTLCache] = None


def get_video_cache() -> TTLCache:
    """Get video cache, initializing lazily with current settings."""
    global _video_cache
    if _video_cache is None:
        s = get_settings()
        _video_cache = TTLCache(maxsize=100, ttl=s.cache_video_ttl)
    return _video_cache


def get_search_cache() -> TTLCache:
    """Get search cache, initializing lazily with current settings."""
    global _search_cache
    if _search_cache is None:
        s = get_settings()
        _search_cache = TTLCache(maxsize=50, ttl=s.cache_search_ttl)
    return _search_cache


def get_channel_cache() -> TTLCache:
    """Get channel cache, initializing lazily with current settings."""
    global _channel_cache
    if _channel_cache is None:
        s = get_settings()
        _channel_cache = TTLCache(maxsize=50, ttl=s.cache_channel_ttl)
    return _channel_cache


def get_extract_cache() -> TTLCache:
    """Get extract cache for external URLs."""
    global _extract_cache
    if _extract_cache is None:
        s = get_settings()
        _extract_cache = TTLCache(maxsize=50, ttl=s.cache_extract_ttl)
    return _extract_cache


def reset_caches() -> None:
    """Reset all caches (call when cache settings change)."""
    global _video_cache, _search_cache, _channel_cache, _extract_cache
    _video_cache = None
    _search_cache = None
    _channel_cache = None
    _extract_cache = None
    logger.info("yt-dlp caches reset")
