"""Tests for invidious_proxy module."""

import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from invidious_proxy import (
    InvidiousProxyError,
    fetch_json,
    get_base_url,
    get_channel,
    get_channel_thumbnails,
    get_channel_videos,
    get_channel_videos_multi_page,
    get_search_suggestions,
    get_trending,
    is_enabled,
    search,
)


class TestIsEnabled:
    """Tests for is_enabled function."""

    def test_returns_true_when_configured(self):
        """Test is_enabled returns True when instance is configured."""
        with patch("invidious_proxy.get_settings") as mock_settings:
            mock_settings.return_value.invidious_instance = "https://invidious.example.com"
            assert is_enabled() is True

    def test_returns_false_when_none(self):
        """Test is_enabled returns False when instance is None."""
        with patch("invidious_proxy.get_settings") as mock_settings:
            mock_settings.return_value.invidious_instance = None
            assert is_enabled() is False

    def test_returns_false_when_empty_string(self):
        """Test is_enabled returns False when instance is empty string."""
        with patch("invidious_proxy.get_settings") as mock_settings:
            mock_settings.return_value.invidious_instance = ""
            assert is_enabled() is False

    def test_returns_false_when_whitespace(self):
        """Test is_enabled returns False when instance is whitespace."""
        with patch("invidious_proxy.get_settings") as mock_settings:
            mock_settings.return_value.invidious_instance = "   "
            assert is_enabled() is False


class TestGetBaseUrl:
    """Tests for get_base_url function."""

    def test_returns_url_without_trailing_slash(self):
        """Test get_base_url strips trailing slash."""
        with patch("invidious_proxy.get_settings") as mock_settings:
            mock_settings.return_value.invidious_instance = "https://invidious.example.com/"
            assert get_base_url() == "https://invidious.example.com"

    def test_returns_url_as_is_without_trailing_slash(self):
        """Test get_base_url returns URL as-is when no trailing slash."""
        with patch("invidious_proxy.get_settings") as mock_settings:
            mock_settings.return_value.invidious_instance = "https://invidious.example.com"
            assert get_base_url() == "https://invidious.example.com"

    def test_returns_empty_when_none(self):
        """Test get_base_url returns empty string when instance is None."""
        with patch("invidious_proxy.get_settings") as mock_settings:
            mock_settings.return_value.invidious_instance = None
            assert get_base_url() == ""


class TestFetchJson:
    """Tests for fetch_json function."""

    @pytest.mark.asyncio
    async def test_returns_none_when_disabled(self):
        """Test fetch_json returns None when Invidious is disabled."""
        with patch("invidious_proxy.is_enabled", return_value=False):
            result = await fetch_json("/api/v1/test")
            assert result is None

    @pytest.mark.asyncio
    async def test_returns_json_on_success(self):
        """Test fetch_json returns parsed JSON on success."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"test": "data"}
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        with (
            patch("invidious_proxy.is_enabled", return_value=True),
            patch("invidious_proxy.get_client", return_value=mock_client),
            patch("invidious_proxy.get_base_url", return_value="https://inv.example.com"),
        ):
            result = await fetch_json("/api/v1/test")
            assert result == {"test": "data"}
            mock_client.get.assert_called_once_with("https://inv.example.com/api/v1/test")

    @pytest.mark.asyncio
    async def test_raises_error_on_non_retryable_http_error(self):
        """Test fetch_json raises InvidiousProxyError immediately on non-retryable HTTP error."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.text = "Not Found"

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.HTTPStatusError(
            "Error", request=MagicMock(), response=mock_response
        ))

        with (
            patch("invidious_proxy.is_enabled", return_value=True),
            patch("invidious_proxy.get_client", return_value=mock_client),
            patch("invidious_proxy.get_base_url", return_value="https://inv.example.com"),
        ):
            with pytest.raises(InvidiousProxyError) as exc_info:
                await fetch_json("/api/v1/test")
            assert "HTTP 404" in str(exc_info.value)
            assert exc_info.value.is_retryable is False
            # Non-retryable errors should not be retried
            assert mock_client.get.call_count == 1

    @pytest.mark.asyncio
    async def test_retries_on_retryable_http_error(self):
        """Test fetch_json retries on retryable HTTP errors (500, 502, etc.)."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.HTTPStatusError(
            "Error", request=MagicMock(), response=mock_response
        ))

        mock_settings = MagicMock()
        mock_settings.invidious_max_retries = 2
        mock_settings.invidious_retry_delay = 0.01  # Fast for testing

        with (
            patch("invidious_proxy.is_enabled", return_value=True),
            patch("invidious_proxy.get_client", return_value=mock_client),
            patch("invidious_proxy.get_base_url", return_value="https://inv.example.com"),
            patch("invidious_proxy.get_settings", return_value=mock_settings),
        ):
            with pytest.raises(InvidiousProxyError) as exc_info:
                await fetch_json("/api/v1/test")
            assert "HTTP 500" in str(exc_info.value)
            assert exc_info.value.is_retryable is True
            # Should have tried initial + 2 retries = 3 total
            assert mock_client.get.call_count == 3

    @pytest.mark.asyncio
    async def test_succeeds_on_retry(self):
        """Test fetch_json succeeds if retry is successful."""
        mock_response_error = MagicMock()
        mock_response_error.status_code = 500
        mock_response_error.text = "Internal Server Error"

        mock_response_success = MagicMock()
        mock_response_success.json.return_value = {"test": "data"}
        mock_response_success.status_code = 200
        mock_response_success.raise_for_status = MagicMock()

        call_count = 0
        async def mock_get(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise httpx.HTTPStatusError("Error", request=MagicMock(), response=mock_response_error)
            return mock_response_success

        mock_client = AsyncMock()
        mock_client.get = mock_get

        mock_settings = MagicMock()
        mock_settings.invidious_max_retries = 3
        mock_settings.invidious_retry_delay = 0.01

        with (
            patch("invidious_proxy.is_enabled", return_value=True),
            patch("invidious_proxy.get_client", return_value=mock_client),
            patch("invidious_proxy.get_base_url", return_value="https://inv.example.com"),
            patch("invidious_proxy.get_settings", return_value=mock_settings),
        ):
            result = await fetch_json("/api/v1/test")
            assert result == {"test": "data"}
            assert call_count == 2  # Failed once, succeeded on retry

    @pytest.mark.asyncio
    async def test_raises_error_on_request_error(self):
        """Test fetch_json raises InvidiousProxyError on request error after retries."""
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.RequestError("Connection failed"))

        mock_settings = MagicMock()
        mock_settings.invidious_max_retries = 2
        mock_settings.invidious_retry_delay = 0.01

        with (
            patch("invidious_proxy.is_enabled", return_value=True),
            patch("invidious_proxy.get_client", return_value=mock_client),
            patch("invidious_proxy.get_base_url", return_value="https://inv.example.com"),
            patch("invidious_proxy.get_settings", return_value=mock_settings),
        ):
            with pytest.raises(InvidiousProxyError) as exc_info:
                await fetch_json("/api/v1/test")
            assert "Request failed" in str(exc_info.value)
            assert exc_info.value.is_retryable is True
            # Should have tried initial + 2 retries = 3 total
            assert mock_client.get.call_count == 3


class TestGetTrending:
    """Tests for get_trending function."""

    @pytest.mark.asyncio
    async def test_returns_list(self):
        """Test get_trending returns a list."""
        with patch("invidious_proxy.fetch_json", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = [{"videoId": "abc123", "title": "Test Video"}]
            result = await get_trending()
            assert isinstance(result, list)
            assert len(result) == 1
            mock_fetch.assert_called_once_with("/api/v1/trending?region=US")

    @pytest.mark.asyncio
    async def test_returns_empty_list_on_invalid_response(self):
        """Test get_trending returns empty list on invalid response."""
        with patch("invidious_proxy.fetch_json", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = None
            result = await get_trending()
            assert result == []


class TestGetSearchSuggestions:
    """Tests for get_search_suggestions function."""

    @pytest.mark.asyncio
    async def test_returns_suggestions(self):
        """Test get_search_suggestions returns suggestions list."""
        with patch("invidious_proxy.fetch_json", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = {"query": "test", "suggestions": ["test1", "test2"]}
            result = await get_search_suggestions("test")
            assert result == ["test1", "test2"]

    @pytest.mark.asyncio
    async def test_encodes_query(self):
        """Test get_search_suggestions properly encodes query."""
        with patch("invidious_proxy.fetch_json", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = {"suggestions": []}
            await get_search_suggestions("test query with spaces")
            mock_fetch.assert_called_once()
            call_args = mock_fetch.call_args[0][0]
            assert "test%20query%20with%20spaces" in call_args

    @pytest.mark.asyncio
    async def test_returns_empty_list_on_invalid_response(self):
        """Test get_search_suggestions returns empty list on invalid response."""
        with patch("invidious_proxy.fetch_json", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = None
            result = await get_search_suggestions("test")
            assert result == []


class TestSearch:
    """Tests for search function."""

    @pytest.mark.asyncio
    async def test_search_videos(self):
        """Test search returns video results."""
        with patch("invidious_proxy.fetch_json", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = [{"videoId": "abc", "title": "Test"}]
            result = await search("test query", type="video")
            assert isinstance(result, list)
            mock_fetch.assert_called_once()
            call_args = mock_fetch.call_args[0][0]
            assert "type=video" in call_args
            assert "page=1" in call_args

    @pytest.mark.asyncio
    async def test_search_with_page(self):
        """Test search with page parameter."""
        with patch("invidious_proxy.fetch_json", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = []
            await search("test", page=3)
            call_args = mock_fetch.call_args[0][0]
            assert "page=3" in call_args


class TestGetChannel:
    """Tests for get_channel function."""

    @pytest.mark.asyncio
    async def test_returns_channel_data(self):
        """Test get_channel returns channel data."""
        channel_data = {"author": "Test Channel", "subCount": 1000}
        with patch("invidious_proxy.fetch_json", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = channel_data
            result = await get_channel("UC123")
            assert result == channel_data

    @pytest.mark.asyncio
    async def test_encodes_channel_id(self):
        """Test get_channel encodes channel ID."""
        with patch("invidious_proxy.fetch_json", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = {}
            await get_channel("@test_channel")
            call_args = mock_fetch.call_args[0][0]
            assert "%40test_channel" in call_args  # @ is encoded as %40


class TestGetChannelThumbnails:
    """Tests for get_channel_thumbnails function."""

    @pytest.mark.asyncio
    async def test_returns_empty_when_disabled(self):
        """Test returns empty list when Invidious is disabled."""
        with patch("invidious_proxy.is_enabled", return_value=False):
            result = await get_channel_thumbnails("UC123")
            assert result == []

    @pytest.mark.asyncio
    async def test_returns_thumbnails(self):
        """Test returns processed thumbnails."""
        channel_data = {
            "author": "Test",
            "authorThumbnails": [
                {"url": "/api/v1/channels/UC123/thumb.jpg", "width": 88, "height": 88, "quality": "default"},
            ],
        }
        with (
            patch("invidious_proxy.is_enabled", return_value=True),
            patch("invidious_proxy.get_channel", new_callable=AsyncMock) as mock_get,
            patch("invidious_proxy.get_base_url", return_value="https://inv.example.com"),
        ):
            mock_get.return_value = channel_data
            result = await get_channel_thumbnails("UC123")

            assert len(result) == 1
            assert result[0].url.startswith("https://inv.example.com")

    @pytest.mark.asyncio
    async def test_returns_empty_on_error(self):
        """Test returns empty list on error."""
        with (
            patch("invidious_proxy.is_enabled", return_value=True),
            patch("invidious_proxy.get_channel", new_callable=AsyncMock) as mock_get,
        ):
            mock_get.side_effect = InvidiousProxyError("Error")
            result = await get_channel_thumbnails("UC123")
            assert result == []


class TestGetChannelVideos:
    """Tests for get_channel_videos function."""

    @pytest.mark.asyncio
    async def test_calls_fetch_channel_tab(self):
        """Test get_channel_videos calls _fetch_channel_tab correctly."""
        with patch("invidious_proxy._fetch_channel_tab", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = {"videos": []}
            await get_channel_videos("UC123")
            mock_fetch.assert_called_once_with("UC123", "videos", None)

    @pytest.mark.asyncio
    async def test_passes_continuation(self):
        """Test get_channel_videos passes continuation token."""
        with patch("invidious_proxy._fetch_channel_tab", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = {"videos": []}
            await get_channel_videos("UC123", continuation="abc123")
            mock_fetch.assert_called_once_with("UC123", "videos", "abc123")


class TestGetChannelVideosMultiPage:
    """Tests for get_channel_videos_multi_page function."""

    @pytest.mark.asyncio
    async def test_returns_videos_with_metadata(self):
        """Test returns videos with pagination metadata."""
        with patch("invidious_proxy.get_channel_videos", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {"videos": [{"videoId": f"v{i}"} for i in range(30)]}
            result = await get_channel_videos_multi_page("UC123", max_videos=20)

            assert "videos" in result
            assert "total_fetched" in result
            assert "pages_fetched" in result
            assert "pagination_limited" in result
            assert len(result["videos"]) <= 20

    @pytest.mark.asyncio
    async def test_fetches_multiple_pages(self):
        """Test fetches multiple pages until max_videos."""
        call_count = 0

        async def mock_get_videos(channel_id, continuation=None):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {
                    "videos": [{"videoId": f"v{i}"} for i in range(30)],
                    "continuation": "next_page",
                }
            return {"videos": [{"videoId": f"v{30+i}"} for i in range(30)]}

        with patch("invidious_proxy.get_channel_videos", side_effect=mock_get_videos):
            result = await get_channel_videos_multi_page("UC123", max_videos=50)
            assert call_count == 2
            assert len(result["videos"]) == 50

    @pytest.mark.asyncio
    async def test_stops_on_no_continuation(self):
        """Test stops when no continuation token."""
        with patch("invidious_proxy.get_channel_videos", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {"videos": [{"videoId": "v1"}]}  # No continuation
            result = await get_channel_videos_multi_page("UC123", max_videos=100)
            assert result["limit_reason"] == "no_continuation"

    @pytest.mark.asyncio
    async def test_handles_414_error(self):
        """Test handles 414 URI Too Large error gracefully."""
        call_count = 0

        async def mock_get_videos(channel_id, continuation=None):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {
                    "videos": [{"videoId": f"v{i}"} for i in range(30)],
                    "continuation": "a" * 10000,  # Very long token
                }
            raise InvidiousProxyError("HTTP 414: URI Too Large")

        with patch("invidious_proxy.get_channel_videos", side_effect=mock_get_videos):
            result = await get_channel_videos_multi_page("UC123", max_videos=100)
            assert result["pagination_limited"] is True
            assert result["limit_reason"] == "414_error"
            assert len(result["videos"]) == 30

    @pytest.mark.asyncio
    async def test_returns_empty_on_no_data(self):
        """Test returns empty when no data returned."""
        with patch("invidious_proxy.get_channel_videos", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = None
            result = await get_channel_videos_multi_page("UC123")
            assert result["videos"] == []
            assert result["limit_reason"] == "no_data"


class TestInvidiousProxyError:
    """Tests for InvidiousProxyError exception."""

    def test_can_be_raised(self):
        """Test InvidiousProxyError can be raised."""
        with pytest.raises(InvidiousProxyError) as exc_info:
            raise InvidiousProxyError("Test error")
        assert "Test error" in str(exc_info.value)

    def test_inherits_from_exception(self):
        """Test InvidiousProxyError inherits from Exception."""
        assert issubclass(InvidiousProxyError, Exception)

    def test_has_status_code_attribute(self):
        """Test InvidiousProxyError has status_code attribute."""
        error = InvidiousProxyError("Test error", status_code=500)
        assert error.status_code == 500

    def test_has_is_retryable_attribute(self):
        """Test InvidiousProxyError has is_retryable attribute."""
        error = InvidiousProxyError("Test error", is_retryable=True)
        assert error.is_retryable is True

    def test_from_http_status_retryable_codes(self):
        """Test from_http_status marks retryable codes correctly."""
        retryable_codes = [500, 502, 503, 504, 408, 429]
        for code in retryable_codes:
            error = InvidiousProxyError.from_http_status(code, f"HTTP {code}")
            assert error.status_code == code
            assert error.is_retryable is True

    def test_from_http_status_non_retryable_codes(self):
        """Test from_http_status marks non-retryable codes correctly."""
        non_retryable_codes = [400, 401, 403, 404, 414]
        for code in non_retryable_codes:
            error = InvidiousProxyError.from_http_status(code, f"HTTP {code}")
            assert error.status_code == code
            assert error.is_retryable is False

    def test_from_connection_error(self):
        """Test from_connection_error creates retryable error."""
        error = InvidiousProxyError.from_connection_error("Connection refused")
        assert error.status_code is None
        assert error.is_retryable is True
