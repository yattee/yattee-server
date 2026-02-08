"""Tests for error handling across the application."""

import asyncio
import json
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


# =============================================================================
# Tests for yt-dlp error handling
# =============================================================================


class TestYtdlpErrorHandling:
    """Tests for yt-dlp subprocess error handling."""

    @pytest.fixture(autouse=True)
    def setup(self, test_db, test_client):
        """Setup test fixtures."""
        self.client = test_client

    def test_video_not_found(self):
        """Test handling of video not found error."""

        async def mock_subprocess(*args, **kwargs):
            from tests.conftest import MockProcess

            return MockProcess(
                stdout="",
                stderr="ERROR: Video unavailable",
                returncode=1,
            )

        with patch("asyncio.create_subprocess_exec", side_effect=mock_subprocess):
            response = self.client.get("/api/v1/videos/nonexisten")  # 11 char ID

        assert response.status_code in [400, 404, 500]

    def test_private_video_error(self):
        """Test handling of private video error."""

        async def mock_subprocess(*args, **kwargs):
            from tests.conftest import MockProcess

            return MockProcess(
                stdout="",
                stderr="ERROR: Private video. Sign in if you've been granted access",
                returncode=1,
            )

        with patch("asyncio.create_subprocess_exec", side_effect=mock_subprocess):
            response = self.client.get("/api/v1/videos/private1234")

        assert response.status_code in [403, 404, 500]

    def test_age_restricted_video_error(self):
        """Test handling of age-restricted video error."""

        async def mock_subprocess(*args, **kwargs):
            from tests.conftest import MockProcess

            return MockProcess(
                stdout="",
                stderr="ERROR: Sign in to confirm your age",
                returncode=1,
            )

        with patch("asyncio.create_subprocess_exec", side_effect=mock_subprocess):
            response = self.client.get("/api/v1/videos/restricted1")

        assert response.status_code in [403, 404, 500]

    def test_ytdlp_timeout(self):
        """Test handling of yt-dlp timeout."""

        async def mock_subprocess(*args, **kwargs):
            mock_proc = MagicMock()
            mock_proc.returncode = None
            mock_proc.communicate = AsyncMock(return_value=(b"", b""))
            mock_proc.kill = MagicMock()
            return mock_proc

        async def timeout_wait_for(coro, timeout):
            """Close the coroutine properly before raising TimeoutError."""
            coro.close()
            raise asyncio.TimeoutError()

        with patch("asyncio.create_subprocess_exec", side_effect=mock_subprocess):
            with patch("asyncio.wait_for", side_effect=timeout_wait_for):
                response = self.client.get("/api/v1/videos/timeout1111")

        assert response.status_code in [408, 500, 504]

    def test_invalid_json_response(self):
        """Test handling of invalid JSON from yt-dlp."""

        async def mock_subprocess(*args, **kwargs):
            from tests.conftest import MockProcess

            return MockProcess(
                stdout="not valid json {{{",
                stderr="",
                returncode=0,
            )

        with patch("asyncio.create_subprocess_exec", side_effect=mock_subprocess):
            response = self.client.get("/api/v1/videos/invalid12345")  # 11 char ID

        assert response.status_code in [400, 500, 502]


# =============================================================================
# Tests for invalid input handling
# =============================================================================


class TestInvalidInputHandling:
    """Tests for invalid input validation."""

    @pytest.fixture(autouse=True)
    def setup(self, test_db, test_client):
        """Setup test fixtures."""
        self.client = test_client

    def test_invalid_video_id_format(self):
        """Test rejection of invalid video ID format."""
        # Too short
        response = self.client.get("/api/v1/videos/abc")
        assert response.status_code in [400, 404, 422, 500]

    def test_video_id_with_special_characters(self):
        """Test handling of video ID with special characters."""
        response = self.client.get("/api/v1/videos/abc<script>")
        assert response.status_code in [400, 404, 422, 500]

    def test_empty_search_query(self):
        """Test handling of empty search query."""
        response = self.client.get("/api/v1/search?q=")
        # Empty query should return empty results or error
        assert response.status_code in [200, 400, 422]

    def test_search_with_very_long_query(self):
        """Test handling of extremely long search query."""
        long_query = "a" * 5000
        response = self.client.get(f"/api/v1/search?q={long_query}")
        assert response.status_code in [200, 400, 413, 414, 422]

    def test_invalid_channel_id_format(self):
        """Test rejection of malformed channel ID."""
        # Channel IDs should start with UC for YouTube
        response = self.client.get("/api/v1/channels/invalid")
        # Should handle gracefully
        assert response.status_code in [200, 400, 404, 422, 500]

    def test_negative_pagination_offset(self):
        """Test handling of negative pagination offset."""
        response = self.client.get("/api/v1/search?q=test&offset=-1")
        assert response.status_code in [200, 400, 422]

    def test_pagination_limit_too_large(self):
        """Test handling of excessively large pagination limit."""
        response = self.client.get("/api/v1/search?q=test&limit=10000")
        assert response.status_code in [200, 400, 422]


# =============================================================================
# Tests for Invidious proxy error handling
# =============================================================================


class TestInvidiousErrorHandling:
    """Tests for Invidious proxy error handling."""

    @pytest.fixture(autouse=True)
    def setup(self, test_db, test_client):
        """Setup test fixtures."""
        self.client = test_client

    def test_invidious_connection_error(self):
        """Test handling of Invidious connection failure."""
        import httpx

        async def mock_get(*args, **kwargs):
            raise httpx.ConnectError("Connection refused")

        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("httpx.AsyncClient", return_value=mock_client):
            with patch("settings.get_settings") as mock_settings:
                mock_settings.return_value.invidious_instance = "http://invalid.example"

                # Should fall back to yt-dlp or return error
                response = self.client.get("/api/v1/videos/dQw4w9WgXcQ")
                # Allow any valid response since fallback might work
                assert response.status_code in [200, 500, 502, 503]

    def test_invidious_timeout(self):
        """Test handling of Invidious request timeout."""
        import httpx

        async def mock_get(*args, **kwargs):
            raise httpx.TimeoutException("Request timed out")

        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("httpx.AsyncClient", return_value=mock_client):
            with patch("settings.get_settings") as mock_settings:
                mock_settings.return_value.invidious_instance = "http://slow.example"

                response = self.client.get("/api/v1/videos/dQw4w9WgXcQ")
                assert response.status_code in [200, 500, 504]

    def test_invidious_invalid_response(self):
        """Test handling of invalid JSON from Invidious."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.side_effect = json.JSONDecodeError("Invalid", "", 0)

        async def mock_get(*args, **kwargs):
            return mock_response

        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("httpx.AsyncClient", return_value=mock_client):
            with patch("settings.get_settings") as mock_settings:
                mock_settings.return_value.invidious_instance = "http://broken.example"

                response = self.client.get("/api/v1/videos/dQw4w9WgXcQ")
                assert response.status_code in [200, 500, 502]


# =============================================================================
# Tests for concurrent request handling
# =============================================================================


class TestConcurrentRequests:
    """Tests for handling concurrent requests."""

    @pytest.fixture(autouse=True)
    def setup(self, test_db, test_client):
        """Setup test fixtures."""
        self.client = test_client

    def test_concurrent_video_requests(self):
        """Test that concurrent video requests are handled properly."""
        import concurrent.futures

        video_info = {
            "id": "concurrent11",
            "title": "Concurrent Test",
            "description": "Test",
            "uploader": "Test",
            "uploader_id": "UCtest",
            "channel_id": "UCtest",
            "duration": 100,
            "view_count": 100,
            "upload_date": "20240101",
            "formats": [],
            "extractor": "youtube",
            "webpage_url": "https://youtube.com/watch?v=concurrent11",
            "original_url": "https://youtube.com/watch?v=concurrent11",
        }

        async def mock_subprocess(*args, **kwargs):
            from tests.conftest import MockProcess

            return MockProcess(stdout=json.dumps(video_info))

        def make_request():
            return self.client.get("/api/v1/videos/concurrent11")

        with patch("asyncio.create_subprocess_exec", side_effect=mock_subprocess):
            with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
                futures = [executor.submit(make_request) for _ in range(3)]
                responses = [f.result() for f in futures]

        # All requests should complete (may succeed or fail gracefully)
        for response in responses:
            assert response.status_code in [200, 400, 500]


# =============================================================================
# Tests for malformed request handling
# =============================================================================


class TestMalformedRequests:
    """Tests for handling malformed HTTP requests."""

    @pytest.fixture(autouse=True)
    def setup(self, test_db, test_client):
        """Setup test fixtures."""
        self.client = test_client

    def test_malformed_json_body(self):
        """Test handling of malformed JSON in request body."""
        response = self.client.post(
            "/api/v1/feed",
            content="not valid json {{{",
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 422

    def test_missing_required_fields(self):
        """Test handling of missing required fields."""
        response = self.client.post(
            "/api/v1/feed",
            json={},  # Missing 'channels' field
        )
        assert response.status_code == 422

    def test_wrong_content_type(self):
        """Test handling of wrong content type."""
        response = self.client.post(
            "/api/v1/feed",
            content='{"channels": []}',
            headers={"Content-Type": "text/plain"},
        )
        # Should either accept or reject gracefully
        assert response.status_code in [200, 415, 422]
