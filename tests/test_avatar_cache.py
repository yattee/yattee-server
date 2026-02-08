"""Tests for avatar_cache module."""

import os
import sys
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import avatar_cache
from avatar_cache import AvatarCache, CachedAvatar, get_cache, start_avatar_cleanup_task, stop_avatar_cleanup_task


class TestCachedAvatar:
    """Tests for CachedAvatar dataclass."""

    def test_is_expired_false_when_fresh(self):
        """Test that fresh cache entry is not expired."""
        cached = CachedAvatar(
            channel_id="UC123",
            thumbnails=[{"url": "https://example.com/thumb.jpg"}],
            cached_at=time.time(),
        )
        assert cached.is_expired() is False

    def test_is_expired_true_when_old(self):
        """Test that old cache entry is expired."""
        # Set cached_at to be older than TTL (default 86400 seconds)
        cached = CachedAvatar(
            channel_id="UC123",
            thumbnails=[{"url": "https://example.com/thumb.jpg"}],
            cached_at=time.time() - 100000,  # More than default TTL
        )
        assert cached.is_expired() is True

    def test_is_expired_respects_settings(self):
        """Test that is_expired uses TTL from settings."""
        with patch("avatar_cache.get_settings") as mock_settings:
            mock_settings.return_value.cache_avatar_ttl = 60  # 60 seconds
            cached = CachedAvatar(
                channel_id="UC123",
                thumbnails=[],
                cached_at=time.time() - 30,  # 30 seconds old
            )
            assert cached.is_expired() is False

            cached = CachedAvatar(
                channel_id="UC123",
                thumbnails=[],
                cached_at=time.time() - 120,  # 120 seconds old
            )
            assert cached.is_expired() is True


class TestAvatarCacheGet:
    """Tests for AvatarCache.get method."""

    @pytest.mark.asyncio
    async def test_get_returns_none_for_missing_channel(self):
        """Test that get returns None for non-cached channel."""
        cache = AvatarCache()
        result = await cache.get("UC_nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_returns_cached_thumbnails(self):
        """Test that get returns cached thumbnails."""
        cache = AvatarCache()
        thumbnails = [{"url": "https://example.com/thumb.jpg", "width": 88, "height": 88}]
        cache._cache["UC123"] = CachedAvatar(
            channel_id="UC123", thumbnails=thumbnails, cached_at=time.time()
        )
        result = await cache.get("UC123")
        assert result == thumbnails

    @pytest.mark.asyncio
    async def test_get_returns_none_for_expired(self):
        """Test that get returns None for expired entry."""
        cache = AvatarCache()
        cache._cache["UC123"] = CachedAvatar(
            channel_id="UC123",
            thumbnails=[{"url": "test"}],
            cached_at=time.time() - 100000,  # Very old
        )
        result = await cache.get("UC123")
        assert result is None


class TestAvatarCacheFetchAndCache:
    """Tests for AvatarCache.fetch_and_cache method."""

    @pytest.mark.asyncio
    async def test_returns_none_when_invidious_disabled(self):
        """Test that fetch_and_cache returns None when Invidious is disabled."""
        cache = AvatarCache()
        with patch("avatar_cache.invidious_proxy.is_enabled", return_value=False):
            result = await cache.fetch_and_cache("UC123")
            assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_already_pending(self):
        """Test that fetch_and_cache returns None when fetch is already pending."""
        cache = AvatarCache()
        cache._pending.add("UC123")
        with patch("avatar_cache.invidious_proxy.is_enabled", return_value=True):
            result = await cache.fetch_and_cache("UC123")
            assert result is None

    @pytest.mark.asyncio
    async def test_fetches_and_caches_thumbnails(self):
        """Test successful fetch and cache."""
        cache = AvatarCache()
        mock_thumbnails = [
            {"url": "/api/v1/thumbnails/UC123/0.jpg", "width": 88, "height": 88},
            {"url": "/api/v1/thumbnails/UC123/1.jpg", "width": 176, "height": 176},
        ]
        mock_channel_data = {"authorThumbnails": mock_thumbnails}

        with (
            patch("avatar_cache.invidious_proxy.is_enabled", return_value=True),
            patch("avatar_cache.invidious_proxy.get_channel", new_callable=AsyncMock) as mock_get,
            patch("avatar_cache.invidious_proxy.get_base_url", return_value="https://inv.example.com"),
        ):
            mock_get.return_value = mock_channel_data
            result = await cache.fetch_and_cache("UC123")

            assert result is not None
            assert len(result) == 2
            assert "UC123" in cache._cache
            # URLs should be resolved
            assert result[0]["url"].startswith("https://inv.example.com")

    @pytest.mark.asyncio
    async def test_returns_none_on_fetch_error(self):
        """Test that fetch_and_cache returns None on error."""
        cache = AvatarCache()
        with (
            patch("avatar_cache.invidious_proxy.is_enabled", return_value=True),
            patch("avatar_cache.invidious_proxy.get_channel", new_callable=AsyncMock) as mock_get,
        ):
            from invidious_proxy import InvidiousProxyError

            mock_get.side_effect = InvidiousProxyError("Network error")
            result = await cache.fetch_and_cache("UC123")
            assert result is None

    @pytest.mark.asyncio
    async def test_removes_from_pending_after_fetch(self):
        """Test that channel is removed from pending after fetch."""
        cache = AvatarCache()
        mock_channel_data = {"authorThumbnails": [{"url": "/thumb.jpg"}]}

        with (
            patch("avatar_cache.invidious_proxy.is_enabled", return_value=True),
            patch("avatar_cache.invidious_proxy.get_channel", new_callable=AsyncMock) as mock_get,
            patch("avatar_cache.invidious_proxy.get_base_url", return_value="https://inv.example.com"),
        ):
            mock_get.return_value = mock_channel_data
            await cache.fetch_and_cache("UC123")
            assert "UC123" not in cache._pending

    @pytest.mark.asyncio
    async def test_removes_from_pending_on_error(self):
        """Test that channel is removed from pending even on error."""
        cache = AvatarCache()
        with (
            patch("avatar_cache.invidious_proxy.is_enabled", return_value=True),
            patch("avatar_cache.invidious_proxy.get_channel", new_callable=AsyncMock) as mock_get,
        ):
            from invidious_proxy import InvidiousProxyError

            mock_get.side_effect = InvidiousProxyError("Error")
            await cache.fetch_and_cache("UC123")
            assert "UC123" not in cache._pending


class TestAvatarCacheScheduleBackgroundFetch:
    """Tests for AvatarCache.schedule_background_fetch method."""

    def test_skips_when_invidious_disabled(self):
        """Test that background fetch is skipped when Invidious is disabled."""
        cache = AvatarCache()
        with patch("avatar_cache.invidious_proxy.is_enabled", return_value=False):
            cache.schedule_background_fetch("UC123")
            assert "UC123" not in cache._pending

    def test_skips_when_cached_and_fresh(self):
        """Test that background fetch is skipped for fresh cached entry."""
        cache = AvatarCache()
        cache._cache["UC123"] = CachedAvatar(
            channel_id="UC123", thumbnails=[{"url": "test"}], cached_at=time.time()
        )
        with (
            patch("avatar_cache.invidious_proxy.is_enabled", return_value=True),
            patch("asyncio.create_task") as mock_task,
        ):
            cache.schedule_background_fetch("UC123")
            mock_task.assert_not_called()

    def test_skips_when_already_pending(self):
        """Test that background fetch is skipped when already pending."""
        cache = AvatarCache()
        cache._pending.add("UC123")
        with (
            patch("avatar_cache.invidious_proxy.is_enabled", return_value=True),
            patch("asyncio.create_task") as mock_task,
        ):
            cache.schedule_background_fetch("UC123")
            mock_task.assert_not_called()

    def test_creates_task_for_new_channel(self):
        """Test that background task is created for new channel."""
        cache = AvatarCache()
        with (
            patch("avatar_cache.invidious_proxy.is_enabled", return_value=True),
            patch("asyncio.create_task") as mock_task,
        ):
            cache.schedule_background_fetch("UC123")
            mock_task.assert_called_once()
            # Close the unawaited coroutine to avoid RuntimeWarning
            mock_task.call_args[0][0].close()


class TestAvatarCacheEviction:
    """Tests for AvatarCache eviction and cleanup."""

    @pytest.mark.asyncio
    async def test_evict_if_needed_when_under_limit(self):
        """Test that eviction doesn't occur when under limit."""
        cache = AvatarCache()
        for i in range(100):
            cache._cache[f"UC{i}"] = CachedAvatar(
                channel_id=f"UC{i}", thumbnails=[], cached_at=time.time()
            )
        await cache._evict_if_needed()
        assert len(cache._cache) == 100

    @pytest.mark.asyncio
    async def test_evict_if_needed_when_at_limit(self):
        """Test that eviction occurs when at limit."""
        cache = AvatarCache()
        # Fill to exactly max_size (10000)
        for i in range(10000):
            cache._cache[f"UC{i}"] = CachedAvatar(
                channel_id=f"UC{i}", thumbnails=[], cached_at=time.time() + i
            )
        await cache._evict_if_needed()
        # Should evict 10% (1000 entries)
        assert len(cache._cache) == 9000

    def test_cleanup_expired_removes_old_entries(self):
        """Test that cleanup_expired removes expired entries."""
        cache = AvatarCache()
        # Add fresh entries
        cache._cache["UC_fresh"] = CachedAvatar(
            channel_id="UC_fresh", thumbnails=[], cached_at=time.time()
        )
        # Add expired entries
        cache._cache["UC_old1"] = CachedAvatar(
            channel_id="UC_old1", thumbnails=[], cached_at=time.time() - 100000
        )
        cache._cache["UC_old2"] = CachedAvatar(
            channel_id="UC_old2", thumbnails=[], cached_at=time.time() - 100000
        )

        cache.cleanup_expired()

        assert "UC_fresh" in cache._cache
        assert "UC_old1" not in cache._cache
        assert "UC_old2" not in cache._cache


class TestAvatarCacheStats:
    """Tests for AvatarCache.stats method."""

    def test_stats_returns_correct_values(self):
        """Test that stats returns correct values."""
        cache = AvatarCache()
        cache._cache["UC1"] = CachedAvatar(
            channel_id="UC1", thumbnails=[], cached_at=time.time()
        )
        cache._cache["UC2"] = CachedAvatar(
            channel_id="UC2", thumbnails=[], cached_at=time.time() - 100000  # Expired
        )
        cache._pending.add("UC3")

        stats = cache.stats()

        assert stats["total_entries"] == 2
        assert stats["expired_entries"] == 1
        assert stats["pending_fetches"] == 1
        assert stats["max_size"] == 10000
        assert "ttl_seconds" in stats


class TestGetCache:
    """Tests for get_cache function."""

    def setup_method(self):
        """Reset global cache before each test."""
        avatar_cache._avatar_cache = None

    def test_creates_cache_on_first_call(self):
        """Test that get_cache creates cache on first call."""
        cache = get_cache()
        assert cache is not None
        assert isinstance(cache, AvatarCache)

    def test_returns_same_instance(self):
        """Test that get_cache returns same instance."""
        cache1 = get_cache()
        cache2 = get_cache()
        assert cache1 is cache2


class TestAvatarCleanupTask:
    """Tests for start/stop avatar cleanup task."""

    def setup_method(self):
        """Reset cleanup task before each test."""
        avatar_cache._cleanup_task = None

    def test_start_creates_task(self):
        """Test that start_avatar_cleanup_task creates an asyncio task."""
        mock_task = MagicMock()
        mock_task.done.return_value = False
        with patch("avatar_cache.asyncio.create_task", return_value=mock_task) as mock_create:
            start_avatar_cleanup_task()
            mock_create.assert_called_once()
            assert avatar_cache._cleanup_task is mock_task
            # Close the unawaited coroutine to avoid RuntimeWarning
            mock_create.call_args[0][0].close()

    def test_start_is_idempotent(self):
        """Test that start doesn't create duplicate task if already running."""
        mock_task = MagicMock()
        mock_task.done.return_value = False
        avatar_cache._cleanup_task = mock_task
        with patch("avatar_cache.asyncio.create_task") as mock_create:
            start_avatar_cleanup_task()
            mock_create.assert_not_called()

    def test_start_restarts_if_task_done(self):
        """Test that start creates new task if previous one finished."""
        old_task = MagicMock()
        old_task.done.return_value = True
        avatar_cache._cleanup_task = old_task
        new_task = MagicMock()
        new_task.done.return_value = False
        with patch("avatar_cache.asyncio.create_task", return_value=new_task) as mock_create:
            start_avatar_cleanup_task()
            mock_create.assert_called_once()
            assert avatar_cache._cleanup_task is new_task
            # Close the unawaited coroutine to avoid RuntimeWarning
            mock_create.call_args[0][0].close()

    def test_stop_cancels_running_task(self):
        """Test that stop_avatar_cleanup_task cancels running task."""
        mock_task = MagicMock()
        mock_task.done.return_value = False
        avatar_cache._cleanup_task = mock_task
        stop_avatar_cleanup_task()
        mock_task.cancel.assert_called_once()

    def test_stop_is_safe_when_no_task(self):
        """Test that stop is safe when no task exists."""
        avatar_cache._cleanup_task = None
        stop_avatar_cleanup_task()  # Should not raise
