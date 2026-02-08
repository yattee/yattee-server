"""Tests for ytdlp_wrapper.py - sanitization and helper functions."""

import os
import sys

import pytest

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ytdlp_wrapper import (
    YtDlpError,
    build_search_sp,
    is_valid_url,
    sanitize_channel_id,
    sanitize_playlist_id,
    sanitize_video_id,
)

# =============================================================================
# Tests for sanitize_video_id
# =============================================================================


class TestSanitizeVideoId:
    """Tests for sanitize_video_id function."""

    def test_valid_video_id(self):
        """Test valid 11-character video ID."""
        assert sanitize_video_id("dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_valid_with_underscore(self):
        """Test video ID with underscore."""
        assert sanitize_video_id("abc_def-123") == "abc_def-123"

    def test_valid_with_dash(self):
        """Test video ID with dash."""
        assert sanitize_video_id("abcdefg-hij") == "abcdefg-hij"

    def test_too_short(self):
        """Test video ID that is too short raises ValueError."""
        with pytest.raises(ValueError, match="Invalid video ID format"):
            sanitize_video_id("abc123")

    def test_too_long(self):
        """Test video ID that is too long raises ValueError."""
        with pytest.raises(ValueError, match="Invalid video ID format"):
            sanitize_video_id("dQw4w9WgXcQextra")

    def test_invalid_characters(self):
        """Test video ID with invalid characters raises ValueError."""
        with pytest.raises(ValueError, match="Invalid video ID format"):
            sanitize_video_id("abc!@#$%^&*(")

    def test_empty_string(self):
        """Test empty string raises ValueError."""
        with pytest.raises(ValueError, match="Invalid video ID format"):
            sanitize_video_id("")

    def test_with_spaces(self):
        """Test video ID with spaces raises ValueError."""
        with pytest.raises(ValueError, match="Invalid video ID format"):
            sanitize_video_id("abc def 123")

    def test_command_injection_attempt(self):
        """Test that command injection is prevented."""
        with pytest.raises(ValueError, match="Invalid video ID format"):
            sanitize_video_id("; rm -rf /")

    def test_url_injection_attempt(self):
        """Test that URL injection is prevented."""
        with pytest.raises(ValueError, match="Invalid video ID format"):
            sanitize_video_id("https://evil")


# =============================================================================
# Tests for sanitize_channel_id
# =============================================================================


class TestSanitizeChannelId:
    """Tests for sanitize_channel_id function."""

    def test_valid_uc_channel_id(self):
        """Test valid UC-prefixed channel ID."""
        channel_id = "UCuAXFkgsw1L7xaCfnd5JJOw"
        assert sanitize_channel_id(channel_id) == channel_id

    def test_valid_handle(self):
        """Test valid @handle format."""
        assert sanitize_channel_id("@LinusTechTips") == "@LinusTechTips"

    def test_valid_handle_with_dots(self):
        """Test handle with dots."""
        assert sanitize_channel_id("@user.name") == "@user.name"

    def test_valid_handle_with_underscore(self):
        """Test handle with underscore."""
        assert sanitize_channel_id("@user_name") == "@user_name"

    def test_valid_url(self):
        """Test full URL is allowed."""
        url = "https://www.youtube.com/channel/UCuAXFkgsw1L7xaCfnd5JJOw"
        assert sanitize_channel_id(url) == url

    def test_valid_http_url(self):
        """Test HTTP URL is allowed."""
        url = "http://www.youtube.com/channel/UCtest"
        assert sanitize_channel_id(url) == url

    def test_base64_like_id(self):
        """Test base64-like IDs from other platforms (TikTok, etc.)."""
        # TikTok user IDs are often base64-like
        tiktok_id = "MS4wLjABAAAAAbcdefghijklmno"
        assert sanitize_channel_id(tiktok_id) == tiktok_id

    def test_invalid_short_id(self):
        """Test short ID raises ValueError."""
        with pytest.raises(ValueError, match="Invalid channel ID format"):
            sanitize_channel_id("abc")

    def test_invalid_characters(self):
        """Test ID with invalid characters raises ValueError."""
        with pytest.raises(ValueError, match="Invalid channel ID format"):
            sanitize_channel_id("UC!@#$%")

    def test_empty_string(self):
        """Test empty string raises ValueError."""
        with pytest.raises(ValueError, match="Invalid channel ID format"):
            sanitize_channel_id("")

    def test_command_injection(self):
        """Test command injection is prevented."""
        with pytest.raises(ValueError, match="Invalid channel ID format"):
            sanitize_channel_id("; whoami")


# =============================================================================
# Tests for sanitize_playlist_id
# =============================================================================


class TestSanitizePlaylistId:
    """Tests for sanitize_playlist_id function."""

    def test_valid_pl_playlist(self):
        """Test valid PL-prefixed playlist ID."""
        playlist_id = "PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf"
        assert sanitize_playlist_id(playlist_id) == playlist_id

    def test_valid_ol_playlist(self):
        """Test valid OL-prefixed playlist ID (YouTube Music)."""
        playlist_id = "OLAK5uy_k1234567890abcdefg"
        assert sanitize_playlist_id(playlist_id) == playlist_id

    def test_valid_uu_playlist(self):
        """Test valid UU-prefixed playlist ID (uploads)."""
        playlist_id = "UUuAXFkgsw1L7xaCfnd5JJOw"
        assert sanitize_playlist_id(playlist_id) == playlist_id

    def test_valid_with_underscore_dash(self):
        """Test playlist ID with underscore and dash."""
        playlist_id = "PL_test-123_abc"
        assert sanitize_playlist_id(playlist_id) == playlist_id

    def test_invalid_characters(self):
        """Test playlist ID with invalid characters raises ValueError."""
        with pytest.raises(ValueError, match="Invalid playlist ID format"):
            sanitize_playlist_id("PL!@#$%^")

    def test_empty_string(self):
        """Test empty string raises ValueError."""
        with pytest.raises(ValueError, match="Invalid playlist ID format"):
            sanitize_playlist_id("")

    def test_command_injection(self):
        """Test command injection is prevented."""
        with pytest.raises(ValueError, match="Invalid playlist ID format"):
            sanitize_playlist_id("PL;rm -rf /")


# =============================================================================
# Tests for build_search_sp
# =============================================================================


class TestBuildSearchSp:
    """Tests for build_search_sp function - YouTube search parameter encoding."""

    def test_no_filters(self):
        """Test with no filters returns None."""
        assert build_search_sp(None, None, None) is None

    def test_empty_strings(self):
        """Test with empty strings returns None."""
        assert build_search_sp("", "", "") is None

    def test_invalid_sort(self):
        """Test with invalid sort option returns None."""
        assert build_search_sp("invalid", None, None) is None

    def test_sort_by_date(self):
        """Test sort by date."""
        result = build_search_sp(sort="date")
        assert result is not None
        # Should be base64 encoded
        import base64

        decoded = base64.b64decode(result)
        assert len(decoded) > 0

    def test_sort_by_views(self):
        """Test sort by view count."""
        result = build_search_sp(sort="views")
        assert result is not None

    def test_sort_by_rating(self):
        """Test sort by rating."""
        result = build_search_sp(sort="rating")
        assert result is not None

    def test_date_filter_hour(self):
        """Test date filter for last hour."""
        result = build_search_sp(date="hour")
        assert result is not None

    def test_date_filter_today(self):
        """Test date filter for today."""
        result = build_search_sp(date="today")
        assert result is not None

    def test_date_filter_week(self):
        """Test date filter for this week."""
        result = build_search_sp(date="week")
        assert result is not None

    def test_date_filter_month(self):
        """Test date filter for this month."""
        result = build_search_sp(date="month")
        assert result is not None

    def test_date_filter_year(self):
        """Test date filter for this year."""
        result = build_search_sp(date="year")
        assert result is not None

    def test_duration_short(self):
        """Test duration filter for short videos."""
        result = build_search_sp(duration="short")
        assert result is not None

    def test_duration_medium(self):
        """Test duration filter for medium videos."""
        result = build_search_sp(duration="medium")
        assert result is not None

    def test_duration_long(self):
        """Test duration filter for long videos."""
        result = build_search_sp(duration="long")
        assert result is not None

    def test_combined_filters(self):
        """Test multiple filters combined."""
        result = build_search_sp(sort="date", date="week", duration="medium")
        assert result is not None
        # Combined should produce longer encoded result
        import base64

        decoded = base64.b64decode(result)
        assert len(decoded) > 2  # More bytes for multiple filters

    def test_invalid_date(self):
        """Test invalid date filter is ignored."""
        # Invalid date with valid sort should still work
        result = build_search_sp(sort="date", date="invalid")
        assert result is not None

    def test_invalid_duration(self):
        """Test invalid duration filter is ignored."""
        result = build_search_sp(sort="views", duration="invalid")
        assert result is not None


# =============================================================================
# Tests for is_valid_url
# =============================================================================


class TestIsValidUrl:
    """Tests for is_valid_url function."""

    def test_valid_https_url(self):
        """Test valid HTTPS URL."""
        assert is_valid_url("https://www.youtube.com/watch?v=abc123") is True

    def test_valid_http_url(self):
        """Test valid HTTP URL."""
        assert is_valid_url("http://example.com/video") is True

    def test_vimeo_url(self):
        """Test Vimeo URL."""
        assert is_valid_url("https://vimeo.com/123456789") is True

    def test_dailymotion_url(self):
        """Test Dailymotion URL."""
        assert is_valid_url("https://www.dailymotion.com/video/x123abc") is True

    def test_tiktok_url(self):
        """Test TikTok URL."""
        assert is_valid_url("https://www.tiktok.com/@user/video/123456") is True

    def test_invalid_scheme_ftp(self):
        """Test FTP URL is invalid."""
        assert is_valid_url("ftp://example.com/file") is False

    def test_invalid_scheme_javascript(self):
        """Test javascript: URL is invalid."""
        assert is_valid_url("javascript:alert(1)") is False

    def test_invalid_scheme_file(self):
        """Test file: URL is invalid."""
        assert is_valid_url("file:///etc/passwd") is False

    def test_no_scheme(self):
        """Test URL without scheme is invalid."""
        assert is_valid_url("www.youtube.com/watch?v=abc") is False

    def test_no_host(self):
        """Test URL without host is invalid."""
        assert is_valid_url("https:///path") is False

    def test_empty_string(self):
        """Test empty string is invalid."""
        assert is_valid_url("") is False

    def test_random_string(self):
        """Test random non-URL string is invalid."""
        assert is_valid_url("not a url at all") is False

    def test_url_with_query_params(self):
        """Test URL with query parameters."""
        assert is_valid_url("https://example.com/video?id=123&quality=hd") is True

    def test_url_with_fragment(self):
        """Test URL with fragment."""
        assert is_valid_url("https://example.com/video#timestamp=120") is True

    def test_url_with_port(self):
        """Test URL with port number."""
        assert is_valid_url("https://localhost:8080/video") is True

    def test_localhost(self):
        """Test localhost URL."""
        assert is_valid_url("http://localhost/video") is True

    def test_ip_address(self):
        """Test IP address URL."""
        assert is_valid_url("http://192.168.1.1/video") is True


# =============================================================================
# Tests for YtDlpError exception
# =============================================================================


class TestYtDlpError:
    """Tests for YtDlpError exception class."""

    def test_exception_message(self):
        """Test exception stores message."""
        error = YtDlpError("Video unavailable")
        assert str(error) == "Video unavailable"

    def test_exception_is_exception(self):
        """Test YtDlpError is an Exception."""
        assert issubclass(YtDlpError, Exception)

    def test_exception_can_be_raised(self):
        """Test exception can be raised and caught."""
        with pytest.raises(YtDlpError) as exc_info:
            raise YtDlpError("Test error")
        assert "Test error" in str(exc_info.value)
