"""Tests for settings module."""

import os
import sys
from unittest.mock import patch

import pytest
from pydantic import ValidationError

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import settings
from settings import Settings, get_settings, invalidate_cache, load_settings, save_settings


class TestSettingsModel:
    """Tests for the Settings pydantic model."""

    def test_default_values(self):
        """Test that Settings has correct default values."""
        s = Settings()
        assert s.ytdlp_path == "yt-dlp"
        assert s.ytdlp_timeout == 120
        assert s.cache_video_ttl == 3600
        assert s.cache_search_ttl == 900
        assert s.cache_channel_ttl == 1800
        assert s.cache_avatar_ttl == 86400
        assert s.default_search_results == 20
        assert s.max_search_results == 50
        assert s.invidious_instance is None
        assert s.invidious_timeout == 10
        assert s.feed_fetch_interval == 1800
        assert s.feed_channel_delay == 2
        assert s.feed_max_videos == 30
        assert s.feed_video_max_age == 30
        assert s.feed_ytdlp_use_flat_playlist is True
        assert s.feed_fallback_ytdlp_on_414 is False
        assert s.allow_all_sites_for_extraction is False
        assert s.cache_extract_ttl == 900
        assert s.rate_limit_window == 60
        assert s.rate_limit_max_failures == 5
        assert s.proxy_download_max_age == 86400

    def test_ytdlp_timeout_constraints(self):
        """Test yt-dlp timeout constraints."""
        assert Settings(ytdlp_timeout=10).ytdlp_timeout == 10
        assert Settings(ytdlp_timeout=600).ytdlp_timeout == 600

        with pytest.raises(ValidationError):
            Settings(ytdlp_timeout=9)

        with pytest.raises(ValidationError):
            Settings(ytdlp_timeout=601)

    def test_cache_ttl_constraints(self):
        """Test cache TTL constraints."""
        # cache_video_ttl: 60-86400
        assert Settings(cache_video_ttl=60).cache_video_ttl == 60
        assert Settings(cache_video_ttl=86400).cache_video_ttl == 86400
        with pytest.raises(ValidationError):
            Settings(cache_video_ttl=59)

        # cache_extract_ttl: 60-7200
        assert Settings(cache_extract_ttl=60).cache_extract_ttl == 60
        assert Settings(cache_extract_ttl=7200).cache_extract_ttl == 7200
        with pytest.raises(ValidationError):
            Settings(cache_extract_ttl=7201)

        # cache_avatar_ttl: 3600-604800
        assert Settings(cache_avatar_ttl=3600).cache_avatar_ttl == 3600
        assert Settings(cache_avatar_ttl=604800).cache_avatar_ttl == 604800
        with pytest.raises(ValidationError):
            Settings(cache_avatar_ttl=3599)

    def test_search_results_constraints(self):
        """Test search results constraints."""
        # default_search_results: 5-50
        assert Settings(default_search_results=5).default_search_results == 5
        assert Settings(default_search_results=50).default_search_results == 50
        with pytest.raises(ValidationError):
            Settings(default_search_results=4)
        with pytest.raises(ValidationError):
            Settings(default_search_results=51)

        # max_search_results: 10-100
        assert Settings(max_search_results=10).max_search_results == 10
        assert Settings(max_search_results=100).max_search_results == 100
        with pytest.raises(ValidationError):
            Settings(max_search_results=9)

    def test_feed_constraints(self):
        """Test feed-related constraints."""
        # feed_fetch_interval: 300-86400
        assert Settings(feed_fetch_interval=300).feed_fetch_interval == 300
        assert Settings(feed_fetch_interval=86400).feed_fetch_interval == 86400
        with pytest.raises(ValidationError):
            Settings(feed_fetch_interval=299)

        # feed_channel_delay: 1-30
        assert Settings(feed_channel_delay=1).feed_channel_delay == 1
        assert Settings(feed_channel_delay=30).feed_channel_delay == 30
        with pytest.raises(ValidationError):
            Settings(feed_channel_delay=0)

        # feed_max_videos: 10-100
        assert Settings(feed_max_videos=10).feed_max_videos == 10
        assert Settings(feed_max_videos=100).feed_max_videos == 100
        with pytest.raises(ValidationError):
            Settings(feed_max_videos=9)

        # feed_video_max_age: 1-365
        assert Settings(feed_video_max_age=1).feed_video_max_age == 1
        assert Settings(feed_video_max_age=365).feed_video_max_age == 365
        with pytest.raises(ValidationError):
            Settings(feed_video_max_age=0)

    def test_rate_limit_constraints(self):
        """Test rate limiting constraints."""
        # rate_limit_window: 10-600
        assert Settings(rate_limit_window=10).rate_limit_window == 10
        assert Settings(rate_limit_window=600).rate_limit_window == 600
        with pytest.raises(ValidationError):
            Settings(rate_limit_window=9)

        # rate_limit_max_failures: 1-100
        assert Settings(rate_limit_max_failures=1).rate_limit_max_failures == 1
        assert Settings(rate_limit_max_failures=100).rate_limit_max_failures == 100
        with pytest.raises(ValidationError):
            Settings(rate_limit_max_failures=0)

    def test_proxy_download_max_age_constraints(self):
        """Test proxy download max age constraints."""
        assert Settings(proxy_download_max_age=60).proxy_download_max_age == 60
        assert Settings(proxy_download_max_age=604800).proxy_download_max_age == 604800
        with pytest.raises(ValidationError):
            Settings(proxy_download_max_age=59)
        with pytest.raises(ValidationError):
            Settings(proxy_download_max_age=604801)

    def test_boolean_defaults(self):
        """Test boolean field defaults."""
        s = Settings()
        assert s.invidious_author_thumbnails is False
        assert s.invidious_proxy_channels is True
        assert s.invidious_proxy_channel_tabs is True
        assert s.invidious_proxy_videos is True
        assert s.invidious_proxy_playlists is True
        assert s.invidious_proxy_captions is True
        assert s.invidious_proxy_thumbnails is True

    def test_invidious_instance_optional(self):
        """Test that invidious_instance is optional."""
        s = Settings()
        assert s.invidious_instance is None

        s = Settings(invidious_instance="https://invidious.example.com")
        assert s.invidious_instance == "https://invidious.example.com"

    def test_model_dump(self):
        """Test that model_dump returns correct dictionary."""
        s = Settings(ytdlp_timeout=180)
        data = s.model_dump()
        assert data["ytdlp_timeout"] == 180
        assert "cache_video_ttl" in data


class TestGetSettings:
    """Tests for get_settings function."""

    def setup_method(self):
        """Reset settings cache before each test."""
        settings._cached_settings = None

    def test_returns_settings_instance(self):
        """Test that get_settings returns a Settings instance."""
        with patch("settings.load_settings") as mock_load:
            mock_load.return_value = Settings()
            s = get_settings()
            assert isinstance(s, Settings)

    def test_caches_settings(self):
        """Test that get_settings caches the result."""
        with patch("settings.load_settings") as mock_load:
            mock_load.return_value = Settings()

            # First call should load
            get_settings()
            assert mock_load.call_count == 1

            # Second call should use cache
            get_settings()
            assert mock_load.call_count == 1

    def test_returns_same_instance(self):
        """Test that get_settings returns same cached instance."""
        with patch("settings.load_settings") as mock_load:
            mock_load.return_value = Settings()

            s1 = get_settings()
            s2 = get_settings()
            assert s1 is s2


class TestLoadSettings:
    """Tests for load_settings function."""

    def test_returns_defaults_when_no_row(self):
        """Test that load_settings returns defaults when database has no row."""
        with patch("settings.database.get_settings_row") as mock_get:
            mock_get.return_value = None
            s = load_settings()
            assert s.ytdlp_timeout == 120  # default value

    def test_loads_from_database(self):
        """Test that load_settings loads values from database."""
        with patch("settings.database.get_settings_row") as mock_get:
            mock_get.return_value = {
                "ytdlp_timeout": 180,
                "cache_video_ttl": 7200,
            }
            s = load_settings()
            assert s.ytdlp_timeout == 180
            assert s.cache_video_ttl == 7200

    def test_filters_invalid_fields(self):
        """Test that load_settings filters out invalid fields."""
        with patch("settings.database.get_settings_row") as mock_get:
            mock_get.return_value = {
                "ytdlp_timeout": 180,
                "invalid_field": "should be ignored",
                "another_invalid": 123,
            }
            s = load_settings()
            assert s.ytdlp_timeout == 180
            assert not hasattr(s, "invalid_field")

    def test_uses_defaults_for_missing_fields(self):
        """Test that load_settings uses defaults for missing fields."""
        with patch("settings.database.get_settings_row") as mock_get:
            mock_get.return_value = {"ytdlp_timeout": 180}
            s = load_settings()
            assert s.ytdlp_timeout == 180
            assert s.cache_video_ttl == 3600  # default


class TestSaveSettings:
    """Tests for save_settings function."""

    def setup_method(self):
        """Reset settings cache before each test."""
        settings._cached_settings = None

    def test_saves_to_database(self):
        """Test that save_settings saves to database."""
        with patch("settings.database.update_settings") as mock_update:
            s = Settings(ytdlp_timeout=180)
            save_settings(s)
            mock_update.assert_called_once()
            call_args = mock_update.call_args[0][0]
            assert call_args["ytdlp_timeout"] == 180

    def test_updates_cache(self):
        """Test that save_settings updates the cache."""
        with patch("settings.database.update_settings"):
            s = Settings(ytdlp_timeout=200)
            save_settings(s)
            assert settings._cached_settings is s
            assert settings._cached_settings.ytdlp_timeout == 200


class TestInvalidateCache:
    """Tests for invalidate_cache function."""

    def setup_method(self):
        """Reset settings cache before each test."""
        settings._cached_settings = None

    def test_clears_cache(self):
        """Test that invalidate_cache clears the cache."""
        settings._cached_settings = Settings()
        assert settings._cached_settings is not None

        invalidate_cache()
        assert settings._cached_settings is None

    def test_forces_reload(self):
        """Test that invalidate_cache forces reload on next access."""
        with patch("settings.load_settings") as mock_load:
            mock_load.return_value = Settings()

            # Initial load
            get_settings()
            assert mock_load.call_count == 1

            # Invalidate cache
            invalidate_cache()

            # Should reload
            get_settings()
            assert mock_load.call_count == 2
