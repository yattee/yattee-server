"""Tests for routers/channels.py - Channel API endpoints."""

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
def sample_ytdlp_channel():
    """Sample yt-dlp channel response."""
    return {
        "id": "UCuAXFkgsw1L7xaCfnd5JJOw",
        "channel": "Rick Astley",
        "channel_id": "UCuAXFkgsw1L7xaCfnd5JJOw",
        "uploader": "Rick Astley",
        "uploader_id": "@RickAstleyYT",
        "description": "Official YouTube channel for Rick Astley",
        "channel_follower_count": 3500000,
        "view_count": 5000000000,
        "channel_is_verified": True,
    }


@pytest.fixture
def sample_invidious_channel():
    """Sample Invidious channel response."""
    return {
        "authorId": "UCuAXFkgsw1L7xaCfnd5JJOw",
        "author": "Rick Astley",
        "description": "Official YouTube channel for Rick Astley",
        "subCount": 3500000,
        "totalViews": 5000000000,
        "authorThumbnails": [
            {"quality": "default", "url": "/ggpht/thumb", "width": 176, "height": 176},
        ],
        "authorBanners": [
            {"quality": "default", "url": "/ggpht/banner", "width": 1060, "height": 175},
        ],
        "authorVerified": True,
    }


@pytest.fixture
def sample_channel_videos():
    """Sample channel videos response."""
    return [
        {
            "id": "video1xxxxx",
            "title": "First Video",
            "duration": 300,
            "view_count": 100000,
            "upload_date": "20240101",
        },
        {
            "id": "video2xxxxx",
            "title": "Second Video",
            "duration": 600,
            "view_count": 200000,
            "upload_date": "20240102",
        },
    ]


@pytest.fixture
def sample_invidious_videos():
    """Sample Invidious videos response."""
    return {
        "videos": [
            {
                "videoId": "invvideo1xx",
                "title": "Invidious Video 1",
                "lengthSeconds": 300,
                "viewCount": 100000,
            },
            {
                "videoId": "invvideo2xx",
                "title": "Invidious Video 2",
                "lengthSeconds": 600,
                "viewCount": 200000,
            },
        ],
        "continuation": "next_page_token",
    }


@pytest.fixture
def sample_playlists():
    """Sample playlist data."""
    return [
        {
            "id": "PL123abc",
            "title": "Playlist 1",
            "playlist_count": 10,
            "thumbnail": "https://i.ytimg.com/vi/thumb1/default.jpg",
        },
        {
            "id": "PL456def",
            "title": "Playlist 2",
            "playlist_count": 20,
            "thumbnail": "https://i.ytimg.com/vi/thumb2/default.jpg",
        },
    ]


# =============================================================================
# Tests for POST /api/v1/channels/metadata
# =============================================================================


class TestChannelsMetadata:
    """Tests for POST /api/v1/channels/metadata endpoint."""

    @pytest.fixture(autouse=True)
    def setup(self, test_db, test_client):
        """Setup test fixtures."""
        self.db_path = test_db
        self.client = test_client

    def test_metadata_success(self):
        """Test successful metadata retrieval."""
        import database

        # First create watched channels
        database.upsert_watched_channels([
            {"channel_id": "UCchannel1", "site": "youtube"},
            {"channel_id": "UCchannel2", "site": "youtube"},
        ])

        # Then update metadata
        database.update_channel_metadata("UCchannel1", "youtube", subscriber_count=1000000, is_verified=True)
        database.update_channel_metadata("UCchannel2", "youtube", subscriber_count=500000, is_verified=False)

        response = self.client.post(
            "/api/v1/channels/metadata", json={"channel_ids": ["UCchannel1", "UCchannel2"]}
        )

        assert response.status_code == 200
        data = response.json()
        assert "channels" in data
        assert len(data["channels"]) == 2

    def test_metadata_empty_request(self):
        """Test metadata with empty channel_ids."""
        response = self.client.post("/api/v1/channels/metadata", json={"channel_ids": []})

        assert response.status_code == 200
        assert response.json() == {"channels": []}

    def test_metadata_unknown_channels(self):
        """Test metadata for unknown channels returns empty results."""
        response = self.client.post(
            "/api/v1/channels/metadata", json={"channel_ids": ["UCunknown1", "UCunknown2"]}
        )

        assert response.status_code == 200
        data = response.json()
        assert "channels" in data


# =============================================================================
# Tests for GET /api/v1/channels/{channel_id}
# =============================================================================


class TestGetChannel:
    """Tests for GET /api/v1/channels/{channel_id} endpoint."""

    @pytest.fixture(autouse=True)
    def setup(self, test_db, test_client):
        """Setup test fixtures."""
        self.db_path = test_db
        self.client = test_client

    def test_get_channel_ytdlp_success(self, sample_ytdlp_channel):
        """Test successful channel retrieval via yt-dlp."""
        with patch("routers.channels.invidious_proxy.is_enabled", return_value=False):
            with patch("routers.channels.get_channel_info", new_callable=AsyncMock) as mock_info:
                mock_info.return_value = sample_ytdlp_channel
                with patch("invidious_proxy.get_channel_thumbnails", new_callable=AsyncMock) as mock_thumbs:
                    mock_thumbs.return_value = []
                    with patch("routers.channels.get_channel_avatar", new_callable=AsyncMock) as mock_avatar:
                        mock_avatar.return_value = "https://example.com/avatar.jpg"
                        response = self.client.get("/api/v1/channels/UCuAXFkgsw1L7xaCfnd5JJOw")

        assert response.status_code == 200
        data = response.json()
        assert data["authorId"] == "UCuAXFkgsw1L7xaCfnd5JJOw"
        assert data["author"] == "Rick Astley"
        assert data["authorVerified"] is True

    def test_get_channel_invidious_success(self, sample_invidious_channel):
        """Test successful channel retrieval via Invidious."""
        with patch("routers.channels.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(invidious_proxy_channels=True)
            with patch("routers.channels.invidious_proxy.is_enabled", return_value=True):
                with patch("routers.channels.invidious_proxy.get_channel", new_callable=AsyncMock) as mock_channel:
                    mock_channel.return_value = sample_invidious_channel
                    with patch("routers.channels.invidious_proxy.get_base_url", return_value="https://inv.example.com"):
                        response = self.client.get("/api/v1/channels/UCuAXFkgsw1L7xaCfnd5JJOw")

        assert response.status_code == 200
        data = response.json()
        assert data["authorId"] == "UCuAXFkgsw1L7xaCfnd5JJOw"
        assert data["author"] == "Rick Astley"

    def test_get_channel_by_handle(self, sample_ytdlp_channel):
        """Test channel retrieval by @handle."""
        with patch("routers.channels.invidious_proxy.is_enabled", return_value=False):
            with patch("routers.channels.get_channel_info", new_callable=AsyncMock) as mock_info:
                mock_info.return_value = sample_ytdlp_channel
                with patch("invidious_proxy.get_channel_thumbnails", new_callable=AsyncMock) as mock_thumbs:
                    mock_thumbs.return_value = []
                    with patch("routers.channels.get_channel_avatar", new_callable=AsyncMock) as mock_avatar:
                        mock_avatar.return_value = None
                        response = self.client.get("/api/v1/channels/@RickAstleyYT")

        assert response.status_code == 200

    def test_get_channel_not_found(self):
        """Test 404 error when channel is not found."""
        from ytdlp_wrapper import YtDlpError

        with patch("routers.channels.invidious_proxy.is_enabled", return_value=False):
            with patch("routers.channels.get_channel_info", new_callable=AsyncMock) as mock_info:
                mock_info.side_effect = YtDlpError("Channel not found")
                response = self.client.get("/api/v1/channels/UCinvalidchannelidhere")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_get_non_youtube_channel_subscribed(self):
        """Test non-YouTube channel returns data from subscription."""
        import database

        # Create a non-YouTube watched channel (acts as subscription)
        database.upsert_watched_channels([{
            "channel_id": "vimeo_12345",
            "site": "vimeo",
            "channel_name": "Vimeo Creator",
            "channel_url": "https://vimeo.com/creator",
            "avatar_url": "https://vimeo.com/avatar.jpg",
        }])

        response = self.client.get("/api/v1/channels/vimeo_12345")

        assert response.status_code == 200
        data = response.json()
        assert data["authorId"] == "vimeo_12345"
        assert data["author"] == "Vimeo Creator"

    def test_get_non_youtube_channel_not_subscribed(self):
        """Test 404 for non-YouTube channel without subscription."""
        response = self.client.get("/api/v1/channels/vimeo_unknown")

        assert response.status_code == 404
        assert "must be subscribed" in response.json()["detail"]


# =============================================================================
# Tests for GET /api/v1/channels/{channel_id}/videos
# =============================================================================


class TestGetChannelVideos:
    """Tests for GET /api/v1/channels/{channel_id}/videos endpoint."""

    @pytest.fixture(autouse=True)
    def setup(self, test_db, test_client):
        """Setup test fixtures."""
        self.db_path = test_db
        self.client = test_client

    def test_get_videos_ytdlp_success(self, sample_channel_videos):
        """Test successful video retrieval via yt-dlp."""
        with patch("routers.channels.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(invidious_proxy_channels=False)
            with patch("routers.channels.get_channel_videos", new_callable=AsyncMock) as mock_videos:
                mock_videos.return_value = sample_channel_videos
                response = self.client.get("/api/v1/channels/UCuAXFkgsw1L7xaCfnd5JJOw/videos")

        assert response.status_code == 200
        data = response.json()
        assert "videos" in data
        assert len(data["videos"]) == 2
        assert data["continuation"] == "2"

    def test_get_videos_invidious_success(self, sample_invidious_videos):
        """Test successful video retrieval via Invidious."""
        with patch("routers.channels.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(invidious_proxy_channels=True)
            with patch("routers.channels.invidious_proxy.is_enabled", return_value=True):
                with patch(
                    "routers.channels.invidious_proxy.get_channel_videos", new_callable=AsyncMock
                ) as mock_videos:
                    mock_videos.return_value = sample_invidious_videos
                    with patch(
                        "routers.channels.invidious_proxy.get_base_url", return_value="https://inv.example.com"
                    ):
                        response = self.client.get("/api/v1/channels/UCuAXFkgsw1L7xaCfnd5JJOw/videos")

        assert response.status_code == 200
        data = response.json()
        assert "videos" in data
        assert data["continuation"] == "next_page_token"

    def test_get_videos_with_continuation(self, sample_channel_videos):
        """Test pagination with continuation token."""
        with patch("routers.channels.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(invidious_proxy_channels=False)
            with patch("routers.channels.get_channel_videos", new_callable=AsyncMock) as mock_videos:
                mock_videos.return_value = sample_channel_videos
                response = self.client.get("/api/v1/channels/UCuAXFkgsw1L7xaCfnd5JJOw/videos?continuation=2")

        assert response.status_code == 200
        mock_videos.assert_called_once()
        # Verify page number was passed correctly
        call_args = mock_videos.call_args
        assert call_args[0][1] == 2 or call_args[1].get("page") == 2

    def test_get_videos_channel_not_found(self):
        """Test 404 error when channel is not found."""
        from ytdlp_wrapper import YtDlpError

        with patch("routers.channels.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(invidious_proxy_channels=False)
            with patch("routers.channels.get_channel_videos", new_callable=AsyncMock) as mock_videos:
                mock_videos.side_effect = YtDlpError("Channel not found")
                response = self.client.get("/api/v1/channels/UCinvalidid1234567890/videos")

        assert response.status_code == 404


# =============================================================================
# Tests for GET /api/v1/channels/{channel_id}/playlists
# =============================================================================


class TestGetChannelPlaylists:
    """Tests for GET /api/v1/channels/{channel_id}/playlists endpoint."""

    @pytest.fixture(autouse=True)
    def setup(self, test_db, test_client):
        """Setup test fixtures."""
        self.db_path = test_db
        self.client = test_client

    def test_get_playlists_success(self, sample_playlists):
        """Test successful playlist retrieval."""
        with patch("routers.channels.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(invidious_proxy_channel_tabs=False)
            with patch("routers.channels.get_channel_tab", new_callable=AsyncMock) as mock_tab:
                mock_tab.return_value = sample_playlists
                response = self.client.get("/api/v1/channels/UCuAXFkgsw1L7xaCfnd5JJOw/playlists")

        assert response.status_code == 200
        data = response.json()
        assert "playlists" in data
        assert len(data["playlists"]) == 2

    def test_get_playlists_invidious_success(self):
        """Test playlist retrieval via Invidious."""
        invidious_playlists = {
            "playlists": [
                {"playlistId": "PL123", "title": "Playlist 1", "videoCount": 10},
            ],
            "continuation": "next_token",
        }

        with patch("routers.channels.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(invidious_proxy_channel_tabs=True)
            with patch("routers.channels.invidious_proxy.is_enabled", return_value=True):
                with patch("routers.channels.invidious_proxy.get_channel_playlists", new_callable=AsyncMock) as mock_pl:
                    mock_pl.return_value = invidious_playlists
                    with patch("routers.channels.invidious_proxy.get_base_url", return_value="https://inv.example.com"):
                        response = self.client.get("/api/v1/channels/UCuAXFkgsw1L7xaCfnd5JJOw/playlists")

        assert response.status_code == 200
        data = response.json()
        assert data["continuation"] == "next_token"


# =============================================================================
# Tests for GET /api/v1/channels/{channel_id}/shorts
# =============================================================================


class TestGetChannelShorts:
    """Tests for GET /api/v1/channels/{channel_id}/shorts endpoint."""

    @pytest.fixture(autouse=True)
    def setup(self, test_db, test_client):
        """Setup test fixtures."""
        self.db_path = test_db
        self.client = test_client

    def test_get_shorts_success(self, sample_channel_videos):
        """Test successful shorts retrieval."""
        with patch("routers.channels.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(invidious_proxy_channel_tabs=False)
            with patch("routers.channels.get_channel_tab", new_callable=AsyncMock) as mock_tab:
                mock_tab.return_value = sample_channel_videos
                response = self.client.get("/api/v1/channels/UCuAXFkgsw1L7xaCfnd5JJOw/shorts")

        assert response.status_code == 200
        data = response.json()
        assert "videos" in data

    def test_get_shorts_with_pagination(self, sample_channel_videos):
        """Test shorts with continuation token."""
        with patch("routers.channels.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(invidious_proxy_channel_tabs=False)
            with patch("routers.channels.get_channel_tab", new_callable=AsyncMock) as mock_tab:
                mock_tab.return_value = sample_channel_videos
                response = self.client.get("/api/v1/channels/UCuAXFkgsw1L7xaCfnd5JJOw/shorts?continuation=3")

        assert response.status_code == 200
        mock_tab.assert_called_once()
        call_args = mock_tab.call_args
        assert call_args[0][2] == 3  # page number


# =============================================================================
# Tests for GET /api/v1/channels/{channel_id}/streams
# =============================================================================


class TestGetChannelStreams:
    """Tests for GET /api/v1/channels/{channel_id}/streams endpoint."""

    @pytest.fixture(autouse=True)
    def setup(self, test_db, test_client):
        """Setup test fixtures."""
        self.db_path = test_db
        self.client = test_client

    def test_get_streams_success(self, sample_channel_videos):
        """Test successful streams retrieval."""
        with patch("routers.channels.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(invidious_proxy_channel_tabs=False)
            with patch("routers.channels.get_channel_tab", new_callable=AsyncMock) as mock_tab:
                mock_tab.return_value = sample_channel_videos
                response = self.client.get("/api/v1/channels/UCuAXFkgsw1L7xaCfnd5JJOw/streams")

        assert response.status_code == 200
        data = response.json()
        assert "videos" in data


# =============================================================================
# Tests for GET /api/v1/channels/{channel_id}/search
# =============================================================================


class TestChannelSearch:
    """Tests for GET /api/v1/channels/{channel_id}/search endpoint."""

    @pytest.fixture(autouse=True)
    def setup(self, test_db, test_client):
        """Setup test fixtures."""
        self.db_path = test_db
        self.client = test_client

    def test_channel_search_success(self, sample_channel_videos):
        """Test successful channel search."""
        with patch("routers.channels.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(invidious_proxy_channels=False)
            with patch("routers.channels.ytdlp_search_channel", new_callable=AsyncMock) as mock_search:
                mock_search.return_value = sample_channel_videos
                response = self.client.get("/api/v1/channels/UCuAXFkgsw1L7xaCfnd5JJOw/search?q=test")

        assert response.status_code == 200
        data = response.json()
        assert "videos" in data
        assert len(data["videos"]) == 2

    def test_channel_search_empty_query(self):
        """Test 400 error for empty search query."""
        response = self.client.get("/api/v1/channels/UCuAXFkgsw1L7xaCfnd5JJOw/search?q=")
        assert response.status_code == 400
        assert "required" in response.json()["detail"].lower()

    def test_channel_search_missing_query(self):
        """Test error when query parameter is missing."""
        response = self.client.get("/api/v1/channels/UCuAXFkgsw1L7xaCfnd5JJOw/search")
        assert response.status_code == 422  # FastAPI validation error

    def test_channel_search_with_pagination(self, sample_channel_videos):
        """Test channel search with pagination."""
        with patch("routers.channels.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(invidious_proxy_channels=False)
            with patch("routers.channels.ytdlp_search_channel", new_callable=AsyncMock) as mock_search:
                mock_search.return_value = sample_channel_videos
                response = self.client.get("/api/v1/channels/UCuAXFkgsw1L7xaCfnd5JJOw/search?q=test&page=2")

        assert response.status_code == 200
        mock_search.assert_called_once()
        call_args = mock_search.call_args
        assert call_args[0][2] == 2  # page number

    def test_channel_search_invidious_success(self, sample_invidious_videos):
        """Test channel search via Invidious."""
        with patch("routers.channels.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(invidious_proxy_channels=True)
            with patch("routers.channels.invidious_proxy.is_enabled", return_value=True):
                with patch("routers.channels.invidious_proxy.search_channel", new_callable=AsyncMock) as mock_search:
                    mock_search.return_value = sample_invidious_videos
                    with patch("routers.channels.invidious_proxy.get_base_url", return_value="https://inv.example.com"):
                        response = self.client.get("/api/v1/channels/UCuAXFkgsw1L7xaCfnd5JJOw/search?q=test")

        assert response.status_code == 200


# =============================================================================
# Tests for _is_youtube_channel_id helper
# =============================================================================


class TestIsYouTubeChannelId:
    """Tests for _is_youtube_channel_id helper function."""

    def test_valid_uc_channel_id(self):
        """Test valid UC-style channel ID."""
        from routers.channels import _is_youtube_channel_id

        assert _is_youtube_channel_id("UCuAXFkgsw1L7xaCfnd5JJOw") is True

    def test_valid_handle(self):
        """Test valid @handle."""
        from routers.channels import _is_youtube_channel_id

        assert _is_youtube_channel_id("@RickAstley") is True

    def test_invalid_short_id(self):
        """Test invalid short ID."""
        from routers.channels import _is_youtube_channel_id

        assert _is_youtube_channel_id("UCshort") is False

    def test_non_youtube_id(self):
        """Test non-YouTube channel ID."""
        from routers.channels import _is_youtube_channel_id

        assert _is_youtube_channel_id("vimeo_12345") is False
        assert _is_youtube_channel_id("dailymotion_abc") is False

    def test_handle_without_at(self):
        """Test handle without @ prefix."""
        from routers.channels import _is_youtube_channel_id

        assert _is_youtube_channel_id("RickAstley") is False


# =============================================================================
# Tests for GET /api/v1/channels/{channel_id}/avatar/{size}.jpg
# =============================================================================


class TestChannelAvatar:
    """Tests for GET /api/v1/channels/{channel_id}/avatar/{size}.jpg endpoint."""

    @pytest.fixture(autouse=True)
    def setup(self, test_db, test_client):
        """Setup test fixtures."""
        self.db_path = test_db
        self.client = test_client

    def test_avatar_cache_hit(self):
        """Test avatar retrieval from cache."""
        thumbnails = [{"url": "https://example.com/avatar.jpg", "width": 176, "height": 176}]

        with patch("routers.channels.avatar_cache.get_cache") as mock_cache:
            mock_cache_instance = MagicMock()
            mock_cache_instance.get = AsyncMock(return_value=thumbnails)
            mock_cache.return_value = mock_cache_instance

            with patch("routers.channels.httpx.AsyncClient") as mock_httpx:
                mock_response = MagicMock()
                mock_response.content = b"fake_image_data"
                mock_response.headers = {"content-type": "image/jpeg"}
                mock_response.raise_for_status = MagicMock()

                mock_client = MagicMock()
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=None)
                mock_client.get = AsyncMock(return_value=mock_response)
                mock_httpx.return_value = mock_client

                response = self.client.get("/api/v1/channels/UCuAXFkgsw1L7xaCfnd5JJOw/avatar/176.jpg")

        assert response.status_code == 200
        assert response.headers["content-type"] == "image/jpeg"

    def test_avatar_not_found(self):
        """Test 404 when avatar is not found."""
        with patch("routers.channels.avatar_cache.get_cache") as mock_cache:
            mock_cache_instance = MagicMock()
            mock_cache_instance.get = AsyncMock(return_value=None)
            mock_cache_instance.fetch_and_cache = AsyncMock(return_value=None)
            mock_cache.return_value = mock_cache_instance

            response = self.client.get("/api/v1/channels/UCunknownid1234567890123/avatar/176.jpg")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_avatar_selects_closest_size(self):
        """Test avatar selection picks closest size."""
        thumbnails = [
            {"url": "https://example.com/small.jpg", "width": 48, "height": 48},
            {"url": "https://example.com/medium.jpg", "width": 176, "height": 176},
            {"url": "https://example.com/large.jpg", "width": 512, "height": 512},
        ]

        with patch("routers.channels.avatar_cache.get_cache") as mock_cache:
            mock_cache_instance = MagicMock()
            mock_cache_instance.get = AsyncMock(return_value=thumbnails)
            mock_cache.return_value = mock_cache_instance

            with patch("routers.channels.httpx.AsyncClient") as mock_httpx:
                mock_response = MagicMock()
                mock_response.content = b"fake_image_data"
                mock_response.headers = {"content-type": "image/jpeg"}
                mock_response.raise_for_status = MagicMock()

                mock_client = MagicMock()
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=None)
                mock_client.get = AsyncMock(return_value=mock_response)
                mock_httpx.return_value = mock_client

                # Request size 100 - should pick 176 (closest)
                response = self.client.get("/api/v1/channels/UCuAXFkgsw1L7xaCfnd5JJOw/avatar/100.jpg")

        assert response.status_code == 200
        # The mock client.get should have been called with the medium URL
        mock_client.get.assert_called_once()
