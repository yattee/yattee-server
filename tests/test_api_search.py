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

    def _mock_innertube_search_empty(self):
        """Helper: mock InnerTube search to return empty so fallbacks are used."""
        return patch("routers.search.innertube.search", new_callable=AsyncMock, return_value=[])

    def _mock_innertube_search_fail(self):
        """Helper: mock InnerTube search to raise error."""
        from innertube import InnerTubeError

        return patch("routers.search.innertube.search", new_callable=AsyncMock, side_effect=InnerTubeError("x"))

    def test_search_videos_innertube_success(self):
        """Test successful video search via InnerTube."""
        innertube_results = [
            {"type": "video", "videoId": "vid1xxxxxxx", "title": "InnerTube Result", "lengthSeconds": 300},
        ]
        with patch("routers.search.innertube.search", new_callable=AsyncMock) as mock_it:
            mock_it.return_value = innertube_results
            response = self.client.get("/api/v1/search?q=test+query")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["videoId"] == "vid1xxxxxxx"

    def test_search_videos_ytdlp_fallback(self, sample_ytdlp_search_results):
        """Test video search falls back to yt-dlp when InnerTube returns empty."""
        with self._mock_innertube_search_empty():
            with patch("routers.search.invidious_proxy.is_enabled", return_value=False):
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
        """Test search with sort filter falls through to yt-dlp."""
        with self._mock_innertube_search_empty():
            with patch("routers.search.invidious_proxy.is_enabled", return_value=False):
                with patch("routers.search.search_videos", new_callable=AsyncMock) as mock_search:
                    mock_search.return_value = sample_ytdlp_search_results
                    response = self.client.get("/api/v1/search?q=test&sort=date")

        assert response.status_code == 200
        mock_search.assert_called_once()
        call_kwargs = mock_search.call_args.kwargs
        assert call_kwargs.get("sort") == "date"

    def test_search_with_date_filter(self, sample_ytdlp_search_results):
        """Test search with date filter."""
        with self._mock_innertube_search_empty():
            with patch("routers.search.invidious_proxy.is_enabled", return_value=False):
                with patch("routers.search.search_videos", new_callable=AsyncMock) as mock_search:
                    mock_search.return_value = sample_ytdlp_search_results
                    response = self.client.get("/api/v1/search?q=test&date=week")

        assert response.status_code == 200
        call_kwargs = mock_search.call_args.kwargs
        assert call_kwargs.get("date") == "week"

    def test_search_with_duration_filter(self, sample_ytdlp_search_results):
        """Test search with duration filter."""
        with self._mock_innertube_search_empty():
            with patch("routers.search.invidious_proxy.is_enabled", return_value=False):
                with patch("routers.search.search_videos", new_callable=AsyncMock) as mock_search:
                    mock_search.return_value = sample_ytdlp_search_results
                    response = self.client.get("/api/v1/search?q=test&duration=long")

        assert response.status_code == 200
        call_kwargs = mock_search.call_args.kwargs
        assert call_kwargs.get("duration") == "long"

    def test_search_with_all_filters(self, sample_ytdlp_search_results):
        """Test search with multiple filters."""
        with self._mock_innertube_search_empty():
            with patch("routers.search.invidious_proxy.is_enabled", return_value=False):
                with patch("routers.search.search_videos", new_callable=AsyncMock) as mock_search:
                    mock_search.return_value = sample_ytdlp_search_results
                    response = self.client.get("/api/v1/search?q=music&sort=views&date=month&duration=medium")

        assert response.status_code == 200
        call_kwargs = mock_search.call_args.kwargs
        assert call_kwargs.get("sort") == "views"
        assert call_kwargs.get("date") == "month"
        assert call_kwargs.get("duration") == "medium"

    def test_search_pagination(self, sample_ytdlp_search_results):
        """Test search pagination via yt-dlp fallback (InnerTube returns empty for page > 1)."""
        many_results = sample_ytdlp_search_results * 9  # 27 results

        # InnerTube returns [] for page > 1, so yt-dlp is used
        with self._mock_innertube_search_empty():
            with patch("routers.search.invidious_proxy.is_enabled", return_value=False):
                with patch("routers.search.search_videos", new_callable=AsyncMock) as mock_search:
                    mock_search.return_value = many_results
                    with patch("routers.search.get_settings") as mock_settings:
                        mock_settings.return_value = MagicMock(default_search_results=10)
                        response = self.client.get("/api/v1/search?q=test&page=2")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 10

    def test_search_channel_innertube_success(self):
        """Test channel search via InnerTube."""
        innertube_results = [
            {"type": "channel", "authorId": "UCchannel1", "author": "First Channel"},
            {"type": "channel", "authorId": "UCchannel2", "author": "Second Channel"},
        ]
        with patch("routers.search.innertube.search", new_callable=AsyncMock) as mock_it:
            mock_it.return_value = innertube_results
            response = self.client.get("/api/v1/search?q=test&type=channel")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["authorId"] == "UCchannel1"

    def test_search_channel_invidious_fallback(self, sample_invidious_channel_results):
        """Test channel search falls back to Invidious when InnerTube fails."""
        with self._mock_innertube_search_fail():
            with patch("routers.search.invidious_proxy.is_enabled", return_value=True):
                with patch("routers.search.invidious_proxy.search", new_callable=AsyncMock) as mock_search:
                    mock_search.return_value = sample_invidious_channel_results
                    with patch("routers.search.invidious_proxy.get_base_url", return_value="https://inv.example.com"):
                        response = self.client.get("/api/v1/search?q=test&type=channel")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["authorId"] == "UCchannel1"

    def test_search_channel_all_fail_returns_empty(self):
        """Test channel search returns empty when all sources fail."""
        with self._mock_innertube_search_fail():
            with patch("routers.search.invidious_proxy.is_enabled", return_value=False):
                response = self.client.get("/api/v1/search?q=test&type=channel")

        assert response.status_code == 200
        assert response.json() == []

    def test_search_playlist_invidious_fallback(self, sample_invidious_playlist_results):
        """Test successful playlist search via Invidious fallback."""
        with self._mock_innertube_search_empty():
            with patch("routers.search.invidious_proxy.is_enabled", return_value=True):
                with patch("routers.search.invidious_proxy.search", new_callable=AsyncMock) as mock_search:
                    mock_search.return_value = sample_invidious_playlist_results
                    with patch("routers.search.invidious_proxy.get_base_url", return_value="https://inv.example.com"):
                        response = self.client.get("/api/v1/search?q=test&type=playlist")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["playlistId"] == "PLabcdef123"

    def test_search_all_types_innertube_mixed(self):
        """Test type=all returns mixed results from InnerTube."""
        mixed_results = [
            {"type": "video", "videoId": "vid1", "title": "Video 1", "lengthSeconds": 100},
            {"type": "channel", "authorId": "UCch1", "author": "Channel 1"},
            {"type": "playlist", "playlistId": "PL1", "title": "Playlist 1", "videoCount": 10},
        ]

        with patch("routers.search.innertube.search", new_callable=AsyncMock) as mock_it:
            mock_it.return_value = mixed_results
            response = self.client.get("/api/v1/search?q=test&type=all")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 3

    def test_search_all_types_invidious_fallback(self):
        """Test type=all falls back to Invidious when InnerTube fails."""
        mixed_results = [
            {"type": "video", "videoId": "vid1", "title": "Video 1", "lengthSeconds": 100},
            {"type": "channel", "authorId": "UCch1", "author": "Channel 1"},
            {"type": "playlist", "playlistId": "PL1", "title": "Playlist 1", "videoCount": 10},
        ]

        with self._mock_innertube_search_fail():
            with patch("routers.search.invidious_proxy.is_enabled", return_value=True):
                with patch("routers.search.invidious_proxy.search", new_callable=AsyncMock) as mock_search:
                    mock_search.return_value = mixed_results
                    with patch("routers.search.invidious_proxy.get_base_url", return_value="https://inv.example.com"):
                        response = self.client.get("/api/v1/search?q=test&type=all")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 3

    def test_search_graceful_fallthrough(self):
        """Test all sources failing returns empty list, not error."""
        from ytdlp_wrapper import YtDlpError

        with self._mock_innertube_search_fail():
            with patch("routers.search.invidious_proxy.is_enabled", return_value=False):
                with patch("routers.search.search_videos", new_callable=AsyncMock) as mock_ytdlp:
                    mock_ytdlp.side_effect = YtDlpError("failed")
                    response = self.client.get("/api/v1/search?q=test&type=all")

        assert response.status_code == 200
        assert response.json() == []

    def test_search_ytdlp_fallback_on_all_prior_failures(self, sample_ytdlp_search_results):
        """Test yt-dlp is used as last resort for video/all searches."""
        from invidious_proxy import InvidiousProxyError

        with self._mock_innertube_search_fail():
            with patch("routers.search.invidious_proxy.is_enabled", return_value=True):
                with patch("routers.search.invidious_proxy.search", new_callable=AsyncMock) as mock_inv:
                    mock_inv.side_effect = InvidiousProxyError("down")
                    with patch("routers.search.search_videos", new_callable=AsyncMock) as mock_ytdlp:
                        mock_ytdlp.return_value = sample_ytdlp_search_results
                        response = self.client.get("/api/v1/search?q=test")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 3


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

    def test_suggestions_success_innertube(self):
        """Test successful search suggestions via InnerTube."""
        suggestions = ["test video", "test music", "testing 123", "test tutorial"]

        with patch("routers.search.innertube.get_search_suggestions", new_callable=AsyncMock) as mock_it:
            mock_it.return_value = suggestions
            response = self.client.get("/api/v1/search/suggestions?q=test")

        assert response.status_code == 200
        data = response.json()
        assert data == suggestions

    def test_suggestions_innertube_fails_invidious_fallback(self):
        """Test suggestions fall back to Invidious when InnerTube fails."""
        from innertube import InnerTubeError

        suggestions = ["test video", "test music"]

        with patch("routers.search.innertube.get_search_suggestions", new_callable=AsyncMock) as mock_it:
            mock_it.side_effect = InnerTubeError("Failed")
            with patch("routers.search.invidious_proxy.is_enabled", return_value=True):
                with patch(
                    "routers.search.invidious_proxy.get_search_suggestions", new_callable=AsyncMock
                ) as mock_sugg:
                    mock_sugg.return_value = suggestions
                    response = self.client.get("/api/v1/search/suggestions?q=test")

        assert response.status_code == 200
        data = response.json()
        assert data == suggestions

    def test_suggestions_both_fail_returns_empty(self):
        """Test empty suggestions when both InnerTube and Invidious fail."""
        from innertube import InnerTubeError
        from invidious_proxy import InvidiousProxyError

        with patch("routers.search.innertube.get_search_suggestions", new_callable=AsyncMock) as mock_it:
            mock_it.side_effect = InnerTubeError("Failed")
            with patch("routers.search.invidious_proxy.is_enabled", return_value=True):
                with patch(
                    "routers.search.invidious_proxy.get_search_suggestions", new_callable=AsyncMock
                ) as mock_sugg:
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

    def _mock_innertube_trending_fail(self):
        """Helper: mock InnerTube trending to fail so Invidious fallback is used."""
        from innertube import InnerTubeError

        return patch("routers.search.innertube.get_trending", new_callable=AsyncMock, side_effect=InnerTubeError("x"))

    def test_trending_success(self, sample_trending_results):
        """Test successful trending videos via Invidious fallback."""
        with self._mock_innertube_trending_fail():
            with patch("routers.search.invidious_proxy.is_enabled", return_value=True):
                with patch(
                    "routers.search.invidious_proxy.get_trending", new_callable=AsyncMock
                ) as mock_trending:
                    mock_trending.return_value = sample_trending_results
                    with patch(
                        "routers.search.invidious_proxy.get_base_url", return_value="https://inv.example.com"
                    ):
                        response = self.client.get("/api/v1/trending")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["videoId"] == "trending1xx"

    def test_trending_innertube_success(self, sample_trending_results):
        """Test successful trending videos via InnerTube."""
        with patch("routers.search.innertube.get_trending", new_callable=AsyncMock) as mock_it:
            mock_it.return_value = sample_trending_results
            response = self.client.get("/api/v1/trending")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2

    def test_trending_with_region(self, sample_trending_results):
        """Test trending with region parameter."""
        with self._mock_innertube_trending_fail():
            with patch("routers.search.invidious_proxy.is_enabled", return_value=True):
                with patch(
                    "routers.search.invidious_proxy.get_trending", new_callable=AsyncMock
                ) as mock_trending:
                    mock_trending.return_value = sample_trending_results
                    with patch(
                        "routers.search.invidious_proxy.get_base_url", return_value="https://inv.example.com"
                    ):
                        response = self.client.get("/api/v1/trending?region=GB")

        assert response.status_code == 200
        mock_trending.assert_called_once_with("GB")

    def test_trending_default_region_us(self, sample_trending_results):
        """Test trending defaults to US region."""
        with self._mock_innertube_trending_fail():
            with patch("routers.search.invidious_proxy.is_enabled", return_value=True):
                with patch(
                    "routers.search.invidious_proxy.get_trending", new_callable=AsyncMock
                ) as mock_trending:
                    mock_trending.return_value = sample_trending_results
                    with patch(
                        "routers.search.invidious_proxy.get_base_url", return_value="https://inv.example.com"
                    ):
                        self.client.get("/api/v1/trending")

        mock_trending.assert_called_once_with("US")

    def test_trending_both_disabled_returns_empty(self):
        """Test empty trending when both InnerTube and Invidious fail."""
        with self._mock_innertube_trending_fail():
            with patch("routers.search.invidious_proxy.is_enabled", return_value=False):
                response = self.client.get("/api/v1/trending")

        assert response.status_code == 200
        assert response.json() == []

    def test_trending_both_error_returns_empty(self):
        """Test empty trending when both sources error."""
        from invidious_proxy import InvidiousProxyError

        with self._mock_innertube_trending_fail():
            with patch("routers.search.invidious_proxy.is_enabled", return_value=True):
                with patch(
                    "routers.search.invidious_proxy.get_trending", new_callable=AsyncMock
                ) as mock_trending:
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

    def _mock_innertube_popular_fail(self):
        """Helper: mock InnerTube popular to fail so Invidious fallback is used."""
        from innertube import InnerTubeError

        return patch("routers.search.innertube.get_popular", new_callable=AsyncMock, side_effect=InnerTubeError("x"))

    def test_popular_success(self, sample_trending_results):
        """Test successful popular videos via Invidious fallback."""
        with self._mock_innertube_popular_fail():
            with patch("routers.search.invidious_proxy.is_enabled", return_value=True):
                with patch(
                    "routers.search.invidious_proxy.get_popular", new_callable=AsyncMock
                ) as mock_popular:
                    mock_popular.return_value = sample_trending_results
                    with patch(
                        "routers.search.invidious_proxy.get_base_url", return_value="https://inv.example.com"
                    ):
                        response = self.client.get("/api/v1/popular")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2

    def test_popular_both_disabled_returns_empty(self):
        """Test empty popular when both InnerTube and Invidious are unavailable."""
        with self._mock_innertube_popular_fail():
            with patch("routers.search.invidious_proxy.is_enabled", return_value=False):
                response = self.client.get("/api/v1/popular")

        assert response.status_code == 200
        assert response.json() == []

    def test_popular_both_error_returns_empty(self):
        """Test empty popular when both sources error."""
        from invidious_proxy import InvidiousProxyError

        with self._mock_innertube_popular_fail():
            with patch("routers.search.invidious_proxy.is_enabled", return_value=True):
                with patch(
                    "routers.search.invidious_proxy.get_popular", new_callable=AsyncMock
                ) as mock_popular:
                    mock_popular.side_effect = InvidiousProxyError("Failed")
                    response = self.client.get("/api/v1/popular")

        assert response.status_code == 200
        assert response.json() == []


# =============================================================================
# Tests for InnerTube search continuation pagination (innertube._search.search)
# =============================================================================


def _innertube_page_response(video_ids, continuation=None, initial_shape=True):
    """Build a minimal InnerTube /search response containing the given video IDs.

    initial_shape=True uses the first-page contents path; False uses the
    continuation-response path (onResponseReceivedCommands).
    """
    item_contents = [
        {
            "videoRenderer": {
                "videoId": vid,
                "title": {"runs": [{"text": f"Video {vid}"}]},
            }
        }
        for vid in video_ids
    ]
    section_contents = [{"itemSectionRenderer": {"contents": item_contents}}]
    if continuation:
        section_contents.append(
            {
                "continuationItemRenderer": {
                    "continuationEndpoint": {
                        "continuationCommand": {"token": continuation},
                    }
                }
            }
        )

    if initial_shape:
        return {
            "contents": {
                "twoColumnSearchResultsRenderer": {
                    "primaryContents": {
                        "sectionListRenderer": {"contents": section_contents},
                    }
                }
            }
        }

    return {
        "onResponseReceivedCommands": [
            {"appendContinuationItemsAction": {"continuationItems": section_contents}}
        ]
    }


@pytest.fixture(autouse=True)
def _reset_search_cache():
    """Ensure the continuation cache is empty between tests."""
    from innertube import _search

    _search._continuation_cache.clear()
    yield
    _search._continuation_cache.clear()


class TestInnertubeSearchPagination:
    """Exercises the cache + sequential-walk logic in innertube._search.search()."""

    @pytest.mark.asyncio
    async def test_page_1_caches_continuation_token(self):
        from innertube import _search

        responses = [_innertube_page_response(["aaaaaaaaaaa"], continuation="TOKEN_P1")]

        async def fake_post(endpoint, body):
            return responses.pop(0)

        with patch("innertube._search.innertube_post", side_effect=fake_post):
            results = await _search.search("python", search_type="video", page=1)

        assert [r["videoId"] for r in results] == ["aaaaaaaaaaa"]
        cached = _search._cache_get(("python", "video", None, None, None, 1))
        assert cached == "TOKEN_P1"

    @pytest.mark.asyncio
    async def test_page_2_uses_cached_token(self):
        from innertube import _search

        # Prime cache so page 2 should be a single continuation call.
        _search._cache_set(("python", "video", None, None, None, 1), "TOKEN_P1")

        calls = []

        async def fake_post(endpoint, body):
            calls.append(body)
            return _innertube_page_response(
                ["bbbbbbbbbbb"], continuation="TOKEN_P2", initial_shape=False
            )

        with patch("innertube._search.innertube_post", side_effect=fake_post):
            results = await _search.search("python", search_type="video", page=2)

        assert len(calls) == 1
        assert calls[0] == {"continuation": "TOKEN_P1"}
        assert [r["videoId"] for r in results] == ["bbbbbbbbbbb"]
        # Next token should be cached for page 2.
        assert _search._cache_get(("python", "video", None, None, None, 2)) == "TOKEN_P2"

    @pytest.mark.asyncio
    async def test_cold_cache_page_3_triggers_sequential_walk(self):
        from innertube import _search

        responses = [
            _innertube_page_response(["aaa"], continuation="TOKEN_P1"),
            _innertube_page_response(["bbb"], continuation="TOKEN_P2", initial_shape=False),
            _innertube_page_response(["ccc"], continuation="TOKEN_P3", initial_shape=False),
        ]
        calls = []

        async def fake_post(endpoint, body):
            calls.append(body)
            return responses.pop(0)

        with patch("innertube._search.innertube_post", side_effect=fake_post):
            results = await _search.search("python", search_type="video", page=3)

        assert len(calls) == 3
        assert "query" in calls[0]
        assert calls[1] == {"continuation": "TOKEN_P1"}
        assert calls[2] == {"continuation": "TOKEN_P2"}
        assert [r["videoId"] for r in results] == ["ccc"]
        # All intermediate pages' tokens should have been cached on the walk.
        assert _search._cache_get(("python", "video", None, None, None, 1)) == "TOKEN_P1"
        assert _search._cache_get(("python", "video", None, None, None, 2)) == "TOKEN_P2"
        assert _search._cache_get(("python", "video", None, None, None, 3)) == "TOKEN_P3"

    @pytest.mark.asyncio
    async def test_filter_change_uses_separate_cache_entry(self):
        from innertube import _search

        # Warm the cache for sort=date.
        _search._cache_set(("python", "video", "date", None, None, 1), "TOKEN_DATE")

        responses = [
            _innertube_page_response(["aaa"], continuation="TOKEN_V1"),
            _innertube_page_response(["bbb"], continuation="TOKEN_V2", initial_shape=False),
        ]
        calls = []

        async def fake_post(endpoint, body):
            calls.append(body)
            return responses.pop(0)

        # Changing sort to 'views' should miss the cache and trigger a walk.
        with patch("innertube._search.innertube_post", side_effect=fake_post):
            results = await _search.search("python", search_type="video", page=2, sort="views")

        assert len(calls) == 2
        assert "query" in calls[0]
        assert calls[1] == {"continuation": "TOKEN_V1"}
        assert [r["videoId"] for r in results] == ["bbb"]

    @pytest.mark.asyncio
    async def test_stale_token_falls_back_to_walk(self):
        from innertube import _search
        from innertube._client import InnerTubeError

        _search._cache_set(("python", "video", None, None, None, 1), "STALE_TOKEN")

        responses = [
            _innertube_page_response(["aaa"], continuation="TOKEN_P1"),
            _innertube_page_response(["bbb"], continuation="TOKEN_P2", initial_shape=False),
        ]
        calls = []

        async def fake_post(endpoint, body):
            calls.append(body)
            if body.get("continuation") == "STALE_TOKEN":
                raise InnerTubeError("expired", status_code=400, is_retryable=False)
            return responses.pop(0)

        with patch("innertube._search.innertube_post", side_effect=fake_post):
            results = await _search.search("python", search_type="video", page=2)

        # First call = stale continuation, then walk from page 1 → page 2.
        assert len(calls) == 3
        assert calls[0] == {"continuation": "STALE_TOKEN"}
        assert "query" in calls[1]
        assert calls[2] == {"continuation": "TOKEN_P1"}
        assert [r["videoId"] for r in results] == ["bbb"]

    @pytest.mark.asyncio
    async def test_walk_returns_empty_when_token_exhausts_early(self):
        from innertube import _search

        # Page 1 returns a token, page 2 returns no continuation token — so page 3 is unreachable.
        responses = [
            _innertube_page_response(["aaa"], continuation="TOKEN_P1"),
            _innertube_page_response(["bbb"], continuation=None, initial_shape=False),
        ]

        async def fake_post(endpoint, body):
            return responses.pop(0)

        with patch("innertube._search.innertube_post", side_effect=fake_post):
            results = await _search.search("python", search_type="video", page=3)

        assert results == []
