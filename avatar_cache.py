"""Channel avatar cache with background fetching."""

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import invidious_proxy
from converters import resolve_invidious_url
from settings import get_settings

logger = logging.getLogger("avatar_cache")


@dataclass
class CachedAvatar:
    """Cached avatar data."""

    channel_id: str
    thumbnails: List[Dict[str, Any]]
    cached_at: float

    def is_expired(self) -> bool:
        s = get_settings()
        return time.time() - self.cached_at > s.cache_avatar_ttl


class AvatarCache:
    """In-memory cache for channel avatars with background fetching."""

    def __init__(self):
        self._cache: Dict[str, CachedAvatar] = {}
        self._pending: set[str] = set()  # Channel IDs currently being fetched
        self._lock = asyncio.Lock()
        self._fetch_semaphore = asyncio.Semaphore(5)  # Limit concurrent avatar fetches

    async def get(self, channel_id: str) -> Optional[List[Dict[str, Any]]]:
        """Get cached avatar thumbnails for a channel.

        Returns None if not cached or expired.
        """
        cached = self._cache.get(channel_id)
        if cached and not cached.is_expired():
            logger.debug(f"[AvatarCache] Cache hit for {channel_id}")
            return cached.thumbnails
        return None

    async def fetch_and_cache(self, channel_id: str) -> Optional[List[Dict[str, Any]]]:
        """Fetch avatar from Invidious and cache it.

        Returns the thumbnails if successful, None otherwise.
        """
        if not invidious_proxy.is_enabled():
            return None

        async with self._lock:
            # Check if already being fetched
            if channel_id in self._pending:
                logger.debug(f"[AvatarCache] Already fetching {channel_id}")
                return None
            self._pending.add(channel_id)

        try:
            logger.info(f"[AvatarCache] Fetching avatar for {channel_id}")
            channel_data = await invidious_proxy.get_channel(channel_id)

            if channel_data and "authorThumbnails" in channel_data:
                raw_thumbnails = channel_data.get("authorThumbnails", [])

                # Resolve relative URLs before caching
                invidious_base = invidious_proxy.get_base_url()
                thumbnails = []
                for thumb in raw_thumbnails:
                    resolved_thumb = dict(thumb)
                    if "url" in resolved_thumb:
                        resolved_thumb["url"] = resolve_invidious_url(resolved_thumb["url"], invidious_base)
                    thumbnails.append(resolved_thumb)

                # Evict oldest entries if cache is full
                await self._evict_if_needed()

                self._cache[channel_id] = CachedAvatar(
                    channel_id=channel_id, thumbnails=thumbnails, cached_at=time.time()
                )
                logger.info(f"[AvatarCache] Cached avatar for {channel_id}")
                return thumbnails
        except invidious_proxy.InvidiousProxyError as e:
            logger.warning(f"[AvatarCache] Failed to fetch avatar for {channel_id}: {e}")
        except (KeyError, TypeError, ValueError) as e:
            logger.error(f"[AvatarCache] Unexpected error fetching avatar for {channel_id}: {e}")
        finally:
            async with self._lock:
                self._pending.discard(channel_id)

        return None

    def schedule_background_fetch(self, channel_id: str):
        """Schedule a background fetch for a channel avatar.

        This is fire-and-forget - doesn't block the caller.
        """
        logger.info(f"[AvatarCache] schedule_background_fetch called for {channel_id}")

        if not invidious_proxy.is_enabled():
            logger.warning(f"[AvatarCache] Invidious proxy not enabled, skipping avatar fetch for {channel_id}")
            return

        # Skip if already cached and not expired
        cached = self._cache.get(channel_id)
        if cached and not cached.is_expired():
            logger.debug(f"[AvatarCache] Avatar already cached for {channel_id}, skipping")
            return

        # Skip if already being fetched
        if channel_id in self._pending:
            logger.debug(f"[AvatarCache] Avatar fetch already pending for {channel_id}, skipping")
            return

        try:
            logger.info(f"[AvatarCache] Creating background task for {channel_id}")
            asyncio.create_task(self._background_fetch(channel_id))
            logger.info(f"[AvatarCache] Background task created successfully for {channel_id}")
        except RuntimeError as e:
            logger.error(f"[AvatarCache] Failed to create background task for {channel_id}: {e}")
        except Exception as e:
            logger.error(f"[AvatarCache] Unexpected error scheduling fetch for {channel_id}: {e}", exc_info=True)

    async def _background_fetch(self, channel_id: str):
        """Background task to fetch and cache avatar with rate limiting."""
        async with self._fetch_semaphore:
            try:
                await self.fetch_and_cache(channel_id)
            except Exception as e:
                logger.error(f"[AvatarCache] Background fetch error for {channel_id}: {e}", exc_info=True)

    async def _evict_if_needed(self):
        """Evict oldest entries if cache exceeds max size."""
        # Note: avatar_cache_max_size is not in settings, use a reasonable default
        max_size = 10000
        if len(self._cache) >= max_size:
            # Sort by cached_at and remove oldest 10%
            sorted_entries = sorted(self._cache.items(), key=lambda x: x[1].cached_at)
            to_remove = len(self._cache) // 10 or 1
            for channel_id, _ in sorted_entries[:to_remove]:
                del self._cache[channel_id]
            logger.info(f"[AvatarCache] Evicted {to_remove} old entries")

    def cleanup_expired(self):
        """Remove all expired entries from cache."""
        expired = [channel_id for channel_id, cached in self._cache.items() if cached.is_expired()]
        for channel_id in expired:
            del self._cache[channel_id]
        if expired:
            logger.info(f"[AvatarCache] Cleaned up {len(expired)} expired entries")

    def stats(self) -> Dict[str, Any]:
        """Return cache statistics."""
        s = get_settings()
        expired_count = sum(1 for c in self._cache.values() if c.is_expired())
        return {
            "total_entries": len(self._cache),
            "expired_entries": expired_count,
            "pending_fetches": len(self._pending),
            "max_size": 10000,
            "ttl_seconds": s.cache_avatar_ttl,
        }


# Global cache instance
_avatar_cache: Optional[AvatarCache] = None


def get_cache() -> AvatarCache:
    """Get or create the global avatar cache."""
    global _avatar_cache
    if _avatar_cache is None:
        _avatar_cache = AvatarCache()
    return _avatar_cache


# --- Periodic cleanup ---
CLEANUP_INTERVAL = 3600  # Clean up expired avatars every hour

_cleanup_task: Optional[asyncio.Task] = None


async def _avatar_cleanup_loop():
    """Periodically clean up expired avatar cache entries."""
    while True:
        await asyncio.sleep(CLEANUP_INTERVAL)
        try:
            get_cache().cleanup_expired()
        except Exception as e:
            logger.error(f"[AvatarCache] Cleanup loop error: {e}", exc_info=True)


def start_avatar_cleanup_task():
    """Start the periodic avatar cache cleanup task."""
    global _cleanup_task
    if _cleanup_task is None or _cleanup_task.done():
        _cleanup_task = asyncio.create_task(_avatar_cleanup_loop())
        logger.info(f"[AvatarCache] Started periodic cleanup task (interval: {CLEANUP_INTERVAL}s)")


def stop_avatar_cleanup_task():
    """Stop the periodic avatar cache cleanup task."""
    global _cleanup_task
    if _cleanup_task and not _cleanup_task.done():
        _cleanup_task.cancel()
        logger.info("[AvatarCache] Stopped periodic cleanup task")
