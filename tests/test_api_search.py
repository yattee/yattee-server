"""Tests for routers/search.py - Search API endpoints."""

import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def sample_ytdlp_search_results():
    """Sample yt-dlp search results."""
    return [
        {
            "id": "video1xxxxx",
            "title": "First Video Result",
            "uploader": "Channel One",
            "channel": "Channel One",
            "channel_id": "UC111111111",
            "duration": 300,
            "view_count": 100000,
            "upload_date": "20240101",
            "thumbnail": "https://i.ytimg.com/vi/video1xxxxx/default.jpg",
        },
        {
            "id": "video2xxxxx",
            "title": "Second Video Result",
            "uploader": "Channel Two",
            "channel": "Channel Two",
            "channel_id": "UC222222222",
            "duration": 600,
            "view_count": 200000,
            "upload_date": "20240102",
            "thumbnail": "https://i.ytimg.com/vi/video2xxxxx/default.jpg",
        },
        {
            "id": "video3xxxxx",
            "title": "Third Video Result",
            "uploader": "Channel Three",
            "channel": "Channel Three",
            "channel_id": "UC333333333",
            "duration": 900,
            "view_count": 300000,
            "upload_date": "20240103",
            "thumbnail": "https://i.ytimg.com/vi/video3xxxxx/default.jpg",
        },
    ]


@pytest.fixture
def sample_invidious_channel_results():
    """Sample Invidious channel search results."""
    return [
        {
            "type": "channel",
            "authorId": "UCchannel1",
            "author": "First Channel",
            "authorThumbnails": [{"url": "/ggpht/abc", "width": 176, "height": 176}],
            "subCount": 100000,
            "videoCount": 500,
            "description": "First channel description",
        },
        {
            "type": "channel",
            "authorId": "UCchannel2",
            "author": "Second Channel",
            "authorThumbnails": [{"url": "/ggpht/def", "width": 176, "height": 176}],
            "subCount": 200000,
            "videoCount": 1000,
            "description": "Second channel description",
        },
    ]


@pytest.fixture
def sample_invidious_playlist_results():
    """Sample Invidious playlist search results."""
    return [
        {
            "type": "playlist",
            "playlistId": "PLabcdef123",
            "title": "First Playlist",
            "author": "Creator One",
            "authorId": "UCcreator1",
            "videoCount": 25,
            "playlistThumbnail": "/vi/thumb1/mqdefault.jpg",
        },
        {
            "type": "playlist",
            "playlistId": "PLghijkl456",
            "title": "Second Playlist",
            "author": "Creator Two",
            "authorId": "UCcreator2",
            "videoCount": 50,
            "playlistThumbnail": "/vi/thumb2/mqdefault.jpg",
        },
    ]


@pytest.fixture
def sample_invidious_video_results():
    """Sample Invidious video search results."""
    return [
        {
            "type": "video",
            "videoId": "invvideo1xx",
            "title": "Invidious Video 1",
            "author": "Author One",
            "authorId": "UCauthor1",
            "lengthSeconds": 300,
            "viewCount": 50000,
            "published": 1704067200,
            "videoThumbnails": [{"quality": "default", "url": "/vi/invvideo1xx/default.jpg"}],
        },
        {
            "type": "video",
            "videoId": "invvideo2xx",
            "title": "Invidious Video 2",
            "author": "Author Two",
            "authorId": "UCauthor2",
            "lengthSeconds": 600,
            "viewCount": 100000,
            "published": 1704153600,
            "videoThumbnails": [{"quality": "default", "url": "/vi/invvideo2xx/default.jpg"}],
        },
    ]


@pytest.fixture
def sample_trending_results():
    """Sample trending video results."""
    return [
        {
            "videoId": "trending1xx",
            "title": "Trending Video 1",
            "author": "Popular Creator",
            "authorId": "UCpopular1",
            "lengthSeconds": 420,
            "viewCount": 5000000,
            "videoThumbnails": [{"quality": "default", "url": "/vi/trending1xx/default.jpg"}],
        },
        {
            "videoId": "trending2xx",
            "title": "Trending Video 2",
            "author": "Another Creator",
            "authorId": "UCpopular2",
            "lengthSeconds": 180,
            "viewCount": 3000000,
            "videoThumbnails": [{"quality": "default", "url": "/vi/trending2xx/default.jpg"}],
        },
    ]


# =============================================================================
# Tests for GET /api/v1/search
# =============================================================================


class TestSearch:
    """Tests for GET /api/v1/search endpoint."""

    @pytest.fixture(autouse=True)
    def setup(self, test_db, test_client):
        """Setup test fixtures."""
        self.db_path = test_db
        self.client = test_client

    def test_search_videos_success(self, sample_ytdlp_search_results):
        """Test successful video search via yt-dlp."""
        with patch("routers.search.search_videos", new_callable=AsyncMock) as mock_search:
            mock_search.return_value = sample_ytdlp_search_results
            response = self.client.get("/api/v1/search?q=test+query")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 3
        assert data[0]["videoId"] == "video1xxxxx"
        assert data[0]["title"] == "First Video Result"

    def test_search_empty_query(self):
        """Test 400 error for empty query."""
        response = self.client.get("/api/v1/search?q=")
        assert response.status_code == 400
        assert "empty" in response.json()["detail"].lower()

    def test_search_whitespace_query(self):
        """Test 400 error for whitespace-only query."""
        response = self.client.get("/api/v1/search?q=   ")
        assert response.status_code == 400
        assert "empty" in response.json()["detail"].lower()

    def test_search_with_sort_filter(self, sample_ytdlp_search_results):
        """Test search with sort filter."""
        with patch("routers.search.search_videos", new_callable=AsyncMock) as mock_search:
            mock_search.return_value = sample_ytdlp_search_results
            response = self.client.get("/api/v1/search?q=test&sort=date")

        assert response.status_code == 200
        mock_search.assert_called_once()
        call_kwargs = mock_search.call_args.kwargs
        assert call_kwargs.get("sort") == "date"

    def test_search_with_date_filter(self, sample_ytdlp_search_results):
        """Test search with date filter."""
        with patch("routers.search.search_videos", new_callable=AsyncMock) as mock_search:
            mock_search.return_value = sample_ytdlp_search_results
            response = self.client.get("/api/v1/search?q=test&date=week")

        assert response.status_code == 200
        call_kwargs = mock_search.call_args.kwargs
        assert call_kwargs.get("date") == "week"

    def test_search_with_duration_filter(self, sample_ytdlp_search_results):
        """Test search with duration filter."""
        with patch("routers.search.search_videos", new_callable=AsyncMock) as mock_search:
            mock_search.return_value = sample_ytdlp_search_results
            response = self.client.get("/api/v1/search?q=test&duration=long")

        assert response.status_code == 200
        call_kwargs = mock_search.call_args.kwargs
        assert call_kwargs.get("duration") == "long"

    def test_search_with_all_filters(self, sample_ytdlp_search_results):
        """Test search with multiple filters."""
        with patch("routers.search.search_videos", new_callable=AsyncMock) as mock_search:
            mock_search.return_value = sample_ytdlp_search_results
            response = self.client.get("/api/v1/search?q=music&sort=views&date=month&duration=medium")

        assert response.status_code == 200
        call_kwargs = mock_search.call_args.kwargs
        assert call_kwargs.get("sort") == "views"
        assert call_kwargs.get("date") == "month"
        assert call_kwargs.get("duration") == "medium"

    def test_search_pagination(self, sample_ytdlp_search_results):
        """Test search pagination."""
        # Create 25 results for pagination test
        many_results = sample_ytdlp_search_results * 9  # 27 results

        with patch("routers.search.search_videos", new_callable=AsyncMock) as mock_search:
            mock_search.return_value = many_results
            with patch("routers.search.get_settings") as mock_settings:
                mock_settings.return_value = MagicMock(default_search_results=10)
                response = self.client.get("/api/v1/search?q=test&page=2")

        assert response.status_code == 200
        data = response.json()
        # Page 2 should have results 10-19
        assert len(data) == 10

    def test_search_channel_requires_invidious(self):
        """Test channel search requires Invidious proxy."""
        with patch("routers.search.invidious_proxy.is_enabled", return_value=False):
            response = self.client.get("/api/v1/search?q=test&type=channel")

        assert response.status_code == 501
        assert "requires Invidious" in response.json()["detail"]

    def test_search_channel_success(self, sample_invidious_channel_results):
        """Test successful channel search via Invidious."""
        with patch("routers.search.invidious_proxy.is_enabled", return_value=True):
            with patch("routers.search.invidious_proxy.search", new_callable=AsyncMock) as mock_search:
                mock_search.return_value = sample_invidious_channel_results
                with patch("routers.search.invidious_proxy.get_base_url", return_value="https://inv.example.com"):
                    response = self.client.get("/api/v1/search?q=test&type=channel")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["authorId"] == "UCchannel1"

    def test_search_playlist_requires_invidious(self):
        """Test playlist search requires Invidious proxy."""
        with patch("routers.search.invidious_proxy.is_enabled", return_value=False):
            response = self.client.get("/api/v1/search?q=test&type=playlist")

        assert response.status_code == 501
        assert "requires Invidious" in response.json()["detail"]

    def test_search_playlist_success(self, sample_invidious_playlist_results):
        """Test successful playlist search via Invidious."""
        with patch("routers.search.invidious_proxy.is_enabled", return_value=True):
            with patch("routers.search.invidious_proxy.search", new_callable=AsyncMock) as mock_search:
                mock_search.return_value = sample_invidious_playlist_results
                with patch("routers.search.invidious_proxy.get_base_url", return_value="https://inv.example.com"):
                    response = self.client.get("/api/v1/search?q=test&type=playlist")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["playlistId"] == "PLabcdef123"

    def test_search_all_types_mixed_results(self, sample_invidious_video_results, sample_invidious_channel_results):
        """Test type=all returns mixed results."""
        mixed_results = [
            {"type": "video", "videoId": "vid1", "title": "Video 1", "lengthSeconds": 100},
            {"type": "channel", "authorId": "UCch1", "author": "Channel 1"},
            {"type": "playlist", "playlistId": "PL1", "title": "Playlist 1", "videoCount": 10},
        ]

        with patch("routers.search.invidious_proxy.is_enabled", return_value=True):
            with patch("routers.search.invidious_proxy.search", new_callable=AsyncMock) as mock_search:
                mock_search.return_value = mixed_results
                with patch("routers.search.invidious_proxy.get_base_url", return_value="https://inv.example.com"):
                    response = self.client.get("/api/v1/search?q=test&type=all")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 3

    def test_search_invidious_proxy_error(self):
        """Test 502 error when Invidious proxy fails."""
        from invidious_proxy import InvidiousProxyError

        with patch("routers.search.invidious_proxy.is_enabled", return_value=True):
            with patch("routers.search.invidious_proxy.search", new_callable=AsyncMock) as mock_search:
                mock_search.side_effect = InvidiousProxyError("Connection failed")
                response = self.client.get("/api/v1/search?q=test&type=channel")

        assert response.status_code == 502
        assert "Invidious proxy error" in response.json()["detail"]

    def test_search_ytdlp_error(self):
        """Test 500 error when yt-dlp fails."""
        from ytdlp_wrapper import YtDlpError

        with patch("routers.search.search_videos", new_callable=AsyncMock) as mock_search:
            mock_search.side_effect = YtDlpError("Search failed")
            response = self.client.get("/api/v1/search?q=test")

        assert response.status_code == 500


# =============================================================================
# Tests for GET /api/v1/search/suggestions
# =============================================================================


class TestSearchSuggestions:
    """Tests for GET /api/v1/search/suggestions endpoint."""

    @pytest.fixture(autouse=True)
    def setup(self, test_db, test_client):
        """Setup test fixtures."""
        self.db_path = test_db
        self.client = test_client

    def test_suggestions_success(self):
        """Test successful search suggestions."""
        suggestions = ["test video", "test music", "testing 123", "test tutorial"]

        with patch("routers.search.invidious_proxy.is_enabled", return_value=True):
            with patch("routers.search.invidious_proxy.get_search_suggestions", new_callable=AsyncMock) as mock_sugg:
                mock_sugg.return_value = suggestions
                response = self.client.get("/api/v1/search/suggestions?q=test")

        assert response.status_code == 200
        data = response.json()
        assert data == suggestions

    def test_suggestions_invidious_disabled(self):
        """Test empty suggestions when Invidious is disabled."""
        with patch("routers.search.invidious_proxy.is_enabled", return_value=False):
            response = self.client.get("/api/v1/search/suggestions?q=test")

        assert response.status_code == 200
        assert response.json() == []

    def test_suggestions_invidious_error_returns_empty(self):
        """Test empty suggestions on Invidious error."""
        from invidious_proxy import InvidiousProxyError

        with patch("routers.search.invidious_proxy.is_enabled", return_value=True):
            with patch("routers.search.invidious_proxy.get_search_suggestions", new_callable=AsyncMock) as mock_sugg:
                mock_sugg.side_effect = InvidiousProxyError("Failed")
                response = self.client.get("/api/v1/search/suggestions?q=test")

        assert response.status_code == 200
        assert response.json() == []


# =============================================================================
# Tests for GET /api/v1/trending
# =============================================================================


class TestTrending:
    """Tests for GET /api/v1/trending endpoint."""

    @pytest.fixture(autouse=True)
    def setup(self, test_db, test_client):
        """Setup test fixtures."""
        self.db_path = test_db
        self.client = test_client

    def test_trending_success(self, sample_trending_results):
        """Test successful trending videos."""
        with patch("routers.search.invidious_proxy.is_enabled", return_value=True):
            with patch("routers.search.invidious_proxy.get_trending", new_callable=AsyncMock) as mock_trending:
                mock_trending.return_value = sample_trending_results
                with patch("routers.search.invidious_proxy.get_base_url", return_value="https://inv.example.com"):
                    response = self.client.get("/api/v1/trending")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["videoId"] == "trending1xx"

    def test_trending_with_region(self, sample_trending_results):
        """Test trending with region parameter."""
        with patch("routers.search.invidious_proxy.is_enabled", return_value=True):
            with patch("routers.search.invidious_proxy.get_trending", new_callable=AsyncMock) as mock_trending:
                mock_trending.return_value = sample_trending_results
                with patch("routers.search.invidious_proxy.get_base_url", return_value="https://inv.example.com"):
                    response = self.client.get("/api/v1/trending?region=GB")

        assert response.status_code == 200
        mock_trending.assert_called_once_with("GB")

    def test_trending_default_region_us(self, sample_trending_results):
        """Test trending defaults to US region."""
        with patch("routers.search.invidious_proxy.is_enabled", return_value=True):
            with patch("routers.search.invidious_proxy.get_trending", new_callable=AsyncMock) as mock_trending:
                mock_trending.return_value = sample_trending_results
                with patch("routers.search.invidious_proxy.get_base_url", return_value="https://inv.example.com"):
                    self.client.get("/api/v1/trending")

        mock_trending.assert_called_once_with("US")

    def test_trending_invidious_disabled(self):
        """Test empty trending when Invidious is disabled."""
        with patch("routers.search.invidious_proxy.is_enabled", return_value=False):
            response = self.client.get("/api/v1/trending")

        assert response.status_code == 200
        assert response.json() == []

    def test_trending_invidious_error_returns_empty(self):
        """Test empty trending on Invidious error."""
        from invidious_proxy import InvidiousProxyError

        with patch("routers.search.invidious_proxy.is_enabled", return_value=True):
            with patch("routers.search.invidious_proxy.get_trending", new_callable=AsyncMock) as mock_trending:
                mock_trending.side_effect = InvidiousProxyError("Failed")
                response = self.client.get("/api/v1/trending")

        assert response.status_code == 200
        assert response.json() == []


# =============================================================================
# Tests for GET /api/v1/popular
# =============================================================================


class TestPopular:
    """Tests for GET /api/v1/popular endpoint."""

    @pytest.fixture(autouse=True)
    def setup(self, test_db, test_client):
        """Setup test fixtures."""
        self.db_path = test_db
        self.client = test_client

    def test_popular_success(self, sample_trending_results):
        """Test successful popular videos."""
        with patch("routers.search.invidious_proxy.is_enabled", return_value=True):
            with patch("routers.search.invidious_proxy.get_popular", new_callable=AsyncMock) as mock_popular:
                mock_popular.return_value = sample_trending_results
                with patch("routers.search.invidious_proxy.get_base_url", return_value="https://inv.example.com"):
                    response = self.client.get("/api/v1/popular")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2

    def test_popular_invidious_disabled(self):
        """Test empty popular when Invidious is disabled."""
        with patch("routers.search.invidious_proxy.is_enabled", return_value=False):
            response = self.client.get("/api/v1/popular")

        assert response.status_code == 200
        assert response.json() == []

    def test_popular_invidious_error_returns_empty(self):
        """Test empty popular on Invidious error."""
        from invidious_proxy import InvidiousProxyError

        with patch("routers.search.invidious_proxy.is_enabled", return_value=True):
            with patch("routers.search.invidious_proxy.get_popular", new_callable=AsyncMock) as mock_popular:
                mock_popular.side_effect = InvidiousProxyError("Failed")
                response = self.client.get("/api/v1/popular")

        assert response.status_code == 200
        assert response.json() == []
