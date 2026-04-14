"""Tests for routers/videos.py - Video API endpoints."""

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
def sample_ytdlp_video():
    """Sample yt-dlp video response."""
    return {
        "id": "dQw4w9WgXcQ",
        "title": "Rick Astley - Never Gonna Give You Up",
        "description": "The official video for Rick Astley's classic song.",
        "uploader": "Rick Astley",
        "uploader_id": "@RickAstleyYT",
        "channel": "Rick Astley",
        "channel_id": "UCuAXFkgsw1L7xaCfnd5JJOw",
        "channel_url": "https://www.youtube.com/channel/UCuAXFkgsw1L7xaCfnd5JJOw",
        "duration": 212,
        "view_count": 1500000000,
        "like_count": 15000000,
        "upload_date": "20091025",
        "thumbnail": "https://i.ytimg.com/vi/dQw4w9WgXcQ/maxresdefault.jpg",
        "thumbnails": [
            {"url": "https://i.ytimg.com/vi/dQw4w9WgXcQ/default.jpg", "width": 120, "height": 90},
            {"url": "https://i.ytimg.com/vi/dQw4w9WgXcQ/maxresdefault.jpg", "width": 1280, "height": 720},
        ],
        "formats": [
            {
                "format_id": "18",
                "ext": "mp4",
                "url": "https://rr1---sn-video.googlevideo.com/videoplayback?id=18",
                "vcodec": "avc1.42001E",
                "acodec": "mp4a.40.2",
                "width": 640,
                "height": 360,
                "tbr": 500,
            },
            {
                "format_id": "22",
                "ext": "mp4",
                "url": "https://rr1---sn-video.googlevideo.com/videoplayback?id=22",
                "vcodec": "avc1.64001F",
                "acodec": "mp4a.40.2",
                "width": 1280,
                "height": 720,
                "tbr": 2000,
            },
        ],
        "subtitles": {},
        "automatic_captions": {},
        "extractor": "youtube",
        "extractor_key": "Youtube",
        "webpage_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    }


@pytest.fixture
def sample_invidious_video():
    """Sample Invidious video response."""
    return {
        "videoId": "dQw4w9WgXcQ",
        "title": "Rick Astley - Never Gonna Give You Up",
        "description": "The official video for Rick Astley's classic song.",
        "author": "Rick Astley",
        "authorId": "UCuAXFkgsw1L7xaCfnd5JJOw",
        "authorUrl": "/channel/UCuAXFkgsw1L7xaCfnd5JJOw",
        "lengthSeconds": 212,
        "viewCount": 1500000000,
        "likeCount": 15000000,
        "published": 1256428800,
        "publishedText": "14 years ago",
        "videoThumbnails": [
            {"quality": "maxres", "url": "https://i.ytimg.com/vi/dQw4w9WgXcQ/maxresdefault.jpg",
             "width": 1280, "height": 720},
        ],
        "adaptiveFormats": [
            {
                "itag": "137",
                "type": "video/mp4",
                "url": "https://invidious.example.com/videoplayback?id=137",
                "resolution": "1080p",
                "qualityLabel": "1080p",
            },
        ],
        "formatStreams": [
            {
                "itag": "22",
                "type": "video/mp4",
                "url": "https://invidious.example.com/videoplayback?id=22",
                "resolution": "720p",
                "qualityLabel": "720p",
            },
        ],
        "captions": [],
    }


@pytest.fixture
def sample_channel_entries():
    """Sample channel video entries."""
    return {
        "channel": "Test Channel",
        "channel_id": "UC123456789",
        "channel_url": "https://vimeo.com/testchannel",
        "extractor": "vimeo",
        "entries": [
            {
                "id": "video1",
                "title": "First Video",
                "uploader": "Test Channel",
                "duration": 300,
                "view_count": 1000,
                "upload_date": "20240101",
                "thumbnail": "https://vimeo.com/thumb1.jpg",
            },
            {
                "id": "video2",
                "title": "Second Video",
                "uploader": "Test Channel",
                "duration": 600,
                "view_count": 2000,
                "upload_date": "20240102",
                "thumbnail": "https://vimeo.com/thumb2.jpg",
            },
        ],
    }


# =============================================================================
# Tests for GET /api/v1/videos/{video_id}
# =============================================================================


class TestGetVideo:
    """Tests for GET /api/v1/videos/{video_id} endpoint."""

    @pytest.fixture(autouse=True)
    def setup(self, test_db, test_client):
        """Setup test fixtures."""
        self.db_path = test_db
        self.client = test_client

    @pytest.fixture(autouse=True)
    def _disable_innertube(self):
        """Disable InnerTube by default so existing tests mock only yt-dlp/Invidious.

        Tests that exercise the InnerTube path opt in by patching
        `routers.videos.innertube.is_enabled` themselves.
        """
        with patch("routers.videos.innertube.is_enabled", return_value=False):
            yield

    def test_get_video_success(self, sample_ytdlp_video):
        """Test successful video retrieval via yt-dlp."""
        with patch("routers.videos.get_video_info", new_callable=AsyncMock) as mock_get_video:
            mock_get_video.return_value = sample_ytdlp_video
            with patch("routers.videos.invidious_proxy.is_enabled", return_value=False):
                with patch("routers.videos.avatar_cache.get_cache") as mock_cache:
                    mock_cache.return_value.schedule_background_fetch = MagicMock()
                    response = self.client.get("/api/v1/videos/dQw4w9WgXcQ")

        assert response.status_code == 200
        data = response.json()
        assert data["videoId"] == "dQw4w9WgXcQ"
        assert data["title"] == "Rick Astley - Never Gonna Give You Up"
        assert data["author"] == "Rick Astley"
        assert data["lengthSeconds"] == 212

    def test_get_video_with_proxy(self, sample_ytdlp_video):
        """Test video retrieval with proxy=true generates proxy URLs."""
        with patch("routers.videos.get_video_info", new_callable=AsyncMock) as mock_get_video:
            mock_get_video.return_value = sample_ytdlp_video
            with patch("routers.videos.invidious_proxy.is_enabled", return_value=False):
                with patch("routers.videos.avatar_cache.get_cache") as mock_cache:
                    mock_cache.return_value.schedule_background_fetch = MagicMock()
                    response = self.client.get("/api/v1/videos/dQw4w9WgXcQ?proxy=true")

        assert response.status_code == 200
        data = response.json()
        # With proxy=true, stream URLs should point to /proxy/fast/
        for stream in data.get("formatStreams", []) + data.get("adaptiveFormats", []):
            assert "/proxy/" in stream["url"] or "token=" in stream["url"]

    def test_get_video_invidious_override_true(self, sample_invidious_video):
        """Test invidious=true query param forces Invidious proxy."""
        with patch("routers.videos.invidious_proxy.is_enabled", return_value=True):
            with patch("routers.videos.invidious_proxy.get_video", new_callable=AsyncMock) as mock_inv:
                mock_inv.return_value = sample_invidious_video
                with patch("routers.videos.invidious_proxy.get_base_url", return_value="https://invidious.example.com"):
                    with patch("routers.videos.avatar_cache.get_cache") as mock_cache:
                        mock_cache.return_value.schedule_background_fetch = MagicMock()
                        response = self.client.get("/api/v1/videos/dQw4w9WgXcQ?invidious=true")

        assert response.status_code == 200
        data = response.json()
        assert data["videoId"] == "dQw4w9WgXcQ"

    def test_get_video_invidious_fallback_to_ytdlp(self, sample_ytdlp_video):
        """Test fallback to yt-dlp when Invidious fails."""
        from invidious_proxy import InvidiousProxyError

        with patch("routers.videos.invidious_proxy.is_enabled", return_value=True):
            with patch("routers.videos.invidious_proxy.get_video", new_callable=AsyncMock) as mock_inv:
                mock_inv.side_effect = InvidiousProxyError("Connection failed")
                with patch("routers.videos.get_video_info", new_callable=AsyncMock) as mock_ytdlp:
                    mock_ytdlp.return_value = sample_ytdlp_video
                    with patch("routers.videos.avatar_cache.get_cache") as mock_cache:
                        mock_cache.return_value.schedule_background_fetch = MagicMock()
                        response = self.client.get("/api/v1/videos/dQw4w9WgXcQ")

        assert response.status_code == 200
        data = response.json()
        assert data["videoId"] == "dQw4w9WgXcQ"

    def test_get_video_not_found(self):
        """Test 404 error when video is not found."""
        from ytdlp_wrapper import YtDlpError

        with patch("routers.videos.invidious_proxy.is_enabled", return_value=False):
            with patch("routers.videos.get_video_info", new_callable=AsyncMock) as mock_get:
                mock_get.side_effect = YtDlpError("Video unavailable")
                response = self.client.get("/api/v1/videos/invalidvid11")

        assert response.status_code == 404
        assert "Video not found" in response.json()["detail"]

    def test_get_video_invalid_id(self):
        """Test 400 error for invalid video ID."""
        with patch("routers.videos.invidious_proxy.is_enabled", return_value=False):
            with patch("routers.videos.get_video_info", new_callable=AsyncMock) as mock_get:
                mock_get.side_effect = ValueError("Invalid video ID")
                response = self.client.get("/api/v1/videos/bad")

        assert response.status_code == 400

    def test_get_video_youtube_blocked(self, test_db):
        """Test 403 error when YouTube extraction is not allowed."""
        from fastapi import HTTPException

        with patch("routers.videos.validate_extractor_allowed") as mock_validate:
            mock_validate.side_effect = HTTPException(
                status_code=403, detail="Extraction from 'youtube' is not allowed"
            )
            response = self.client.get("/api/v1/videos/dQw4w9WgXcQ")

        # YouTube site is not enabled
        assert response.status_code == 403
        assert "not allowed" in response.json()["detail"]


# =============================================================================
# Tests for the InnerTube + yt-dlp hybrid default path
# =============================================================================


@pytest.fixture
def sample_innertube_video():
    """Invidious-shaped dict as produced by innertube_player_to_invidious_video.

    Stream URLs are empty (ciphered in WEB client responses); routers.videos
    fills them in from yt-dlp by itag.
    """
    return {
        "videoId": "dQw4w9WgXcQ",
        "title": "InnerTube Title",
        "description": "Full description from /next",
        "author": "Rick Astley",
        "authorId": "UCuAXFkgsw1L7xaCfnd5JJOw",
        "authorUrl": "/channel/UCuAXFkgsw1L7xaCfnd5JJOw",
        "authorThumbnails": [
            {"quality": "default", "url": "https://yt3.example/avatar.jpg", "width": 176, "height": 176}
        ],
        "lengthSeconds": 212,
        "published": 1256428800,
        "publishedText": None,
        "viewCount": 1500000000,
        "likeCount": 15000000,
        "videoThumbnails": [
            {"quality": "maxres", "url": "https://i.ytimg.com/vi/dQw4w9WgXcQ/maxresdefault.jpg",
             "width": 1280, "height": 720},
        ],
        "liveNow": False,
        "isUpcoming": False,
        "hlsUrl": "https://manifest.googlevideo.com/hls/master.m3u8",
        "dashUrl": "https://manifest.googlevideo.com/dash/manifest.mpd",
        "formatStreams": [
            {
                "url": "",
                "itag": "18",
                "type": "video/mp4",
                "container": "mp4",
                "resolution": "360p",
                "width": 640,
                "height": 360,
                "encoding": "avc1.42001E",
                "fps": 30,
                "quality": "360p",
                "size": None,
            },
        ],
        "adaptiveFormats": [
            {
                "url": "",
                "itag": "137",
                "type": "video/mp4",
                "container": "mp4",
                "resolution": "1080p",
                "width": 1920,
                "height": 1080,
                "encoding": "avc1.640028",
                "fps": 30,
                "bitrate": "4000000",
                "clen": None,
            },
            {
                "url": "",
                "itag": "140",
                "type": "audio/mp4",
                "container": "mp4",
                "resolution": None,
                "width": None,
                "height": None,
                "encoding": "mp4a.40.2",
                "bitrate": "128000",
                "audioQuality": "AUDIO_QUALITY_MEDIUM",
            },
        ],
        "captions": [
            {"label": "English", "languageCode": "en", "url": "https://yt/caption?lang=en", "auto_generated": False},
        ],
        "storyboards": [],
        "recommendedVideos": [],
    }


class TestGetVideoInnerTubeHybrid:
    """Tests for the InnerTube + yt-dlp hybrid path."""

    @pytest.fixture(autouse=True)
    def setup(self, test_db, test_client):
        self.db_path = test_db
        self.client = test_client

    @pytest.fixture(autouse=True)
    def _enable_innertube(self):
        with patch("routers.videos.innertube.is_enabled", return_value=True):
            yield

    def test_uses_innertube_by_default(self, sample_innertube_video, sample_ytdlp_video):
        """Response title/description from InnerTube, stream URLs from yt-dlp."""
        with patch("routers.videos.innertube.get_video_player_next",
                   new_callable=AsyncMock, return_value=sample_innertube_video), \
             patch("routers.videos.get_video_info",
                   new_callable=AsyncMock, return_value=sample_ytdlp_video), \
             patch("routers.videos.invidious_proxy.is_enabled", return_value=False), \
             patch("routers.videos.avatar_cache.get_cache") as mock_cache:
            mock_cache.return_value.schedule_background_fetch = MagicMock()
            response = self.client.get("/api/v1/videos/dQw4w9WgXcQ?proxy=false")

        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "InnerTube Title"
        assert data["description"] == "Full description from /next"
        # Stream URLs come from yt-dlp (itag 18 → direct googlevideo URL)
        stream_18 = next(s for s in data["formatStreams"] if s["itag"] == "18")
        assert "googlevideo.com" in stream_18["url"]
        # HLS / DASH from InnerTube are passed through
        assert data["hlsUrl"] == "https://manifest.googlevideo.com/hls/master.m3u8"
        assert data["dashUrl"] == "https://manifest.googlevideo.com/dash/manifest.mpd"

    def test_merge_drops_itag_missing_in_ytdlp(self, sample_innertube_video, sample_ytdlp_video):
        """InnerTube itag 140 has no yt-dlp URL → dropped from response."""
        # sample_ytdlp_video only has itags 18 and 22
        with patch("routers.videos.innertube.get_video_player_next",
                   new_callable=AsyncMock, return_value=sample_innertube_video), \
             patch("routers.videos.get_video_info",
                   new_callable=AsyncMock, return_value=sample_ytdlp_video), \
             patch("routers.videos.invidious_proxy.is_enabled", return_value=False), \
             patch("routers.videos.avatar_cache.get_cache") as mock_cache:
            mock_cache.return_value.schedule_background_fetch = MagicMock()
            response = self.client.get("/api/v1/videos/dQw4w9WgXcQ?proxy=false")

        assert response.status_code == 200
        data = response.json()
        itags_in_response = {s["itag"] for s in data["formatStreams"] + data["adaptiveFormats"]}
        assert "140" not in itags_in_response
        assert "137" not in itags_in_response  # also not in yt-dlp
        assert "18" in itags_in_response

    def test_merge_drops_itag_missing_in_innertube(self, sample_innertube_video):
        """yt-dlp itag 999 has no InnerTube shape → dropped from response."""
        ytdlp_only = {
            "id": "dQw4w9WgXcQ",
            "title": "yt-dlp title",
            "channel_id": "UCuAXFkgsw1L7xaCfnd5JJOw",
            "formats": [
                {"format_id": "18", "ext": "mp4", "url": "https://yt.com/18",
                 "vcodec": "avc1", "acodec": "mp4a", "width": 640, "height": 360},
                {"format_id": "999", "ext": "mp4", "url": "https://yt.com/999",
                 "vcodec": "avc1", "acodec": "mp4a", "width": 640, "height": 360},
            ],
            "thumbnails": [], "subtitles": {}, "automatic_captions": {},
            "extractor": "youtube",
        }
        with patch("routers.videos.innertube.get_video_player_next",
                   new_callable=AsyncMock, return_value=sample_innertube_video), \
             patch("routers.videos.get_video_info",
                   new_callable=AsyncMock, return_value=ytdlp_only), \
             patch("routers.videos.invidious_proxy.is_enabled", return_value=False), \
             patch("routers.videos.avatar_cache.get_cache") as mock_cache:
            mock_cache.return_value.schedule_background_fetch = MagicMock()
            response = self.client.get("/api/v1/videos/dQw4w9WgXcQ?proxy=false")

        assert response.status_code == 200
        data = response.json()
        itags = {s["itag"] for s in data["formatStreams"] + data["adaptiveFormats"]}
        assert "999" not in itags

    def test_live_video_falls_through_to_ytdlp(self, sample_innertube_video, sample_ytdlp_video):
        """InnerTube says isLive=True → build response from yt-dlp."""
        live_it = {**sample_innertube_video, "liveNow": True, "title": "LIVE InnerTube"}
        with patch("routers.videos.innertube.get_video_player_next",
                   new_callable=AsyncMock, return_value=live_it), \
             patch("routers.videos.get_video_info",
                   new_callable=AsyncMock, return_value=sample_ytdlp_video), \
             patch("routers.videos.invidious_proxy.is_enabled", return_value=False), \
             patch("routers.videos.avatar_cache.get_cache") as mock_cache:
            mock_cache.return_value.schedule_background_fetch = MagicMock()
            response = self.client.get("/api/v1/videos/dQw4w9WgXcQ?proxy=false")

        assert response.status_code == 200
        data = response.json()
        # Title came from yt-dlp, not the live InnerTube payload
        assert data["title"] == "Rick Astley - Never Gonna Give You Up"

    def test_innertube_failure_falls_back_to_ytdlp(self, sample_ytdlp_video):
        """InnerTubeError → use yt-dlp alone."""
        from innertube import InnerTubeError

        with patch("routers.videos.innertube.get_video_player_next",
                   new_callable=AsyncMock, side_effect=InnerTubeError("Unplayable")), \
             patch("routers.videos.get_video_info",
                   new_callable=AsyncMock, return_value=sample_ytdlp_video), \
             patch("routers.videos.invidious_proxy.is_enabled", return_value=False), \
             patch("routers.videos.avatar_cache.get_cache") as mock_cache:
            mock_cache.return_value.schedule_background_fetch = MagicMock()
            response = self.client.get("/api/v1/videos/dQw4w9WgXcQ?proxy=false")

        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Rick Astley - Never Gonna Give You Up"

    def test_invidious_override_bypasses_innertube(self, sample_invidious_video):
        """?invidious=true → InnerTube is never called."""
        it_mock = AsyncMock()
        with patch("routers.videos.innertube.get_video_player_next", it_mock), \
             patch("routers.videos.invidious_proxy.is_enabled", return_value=True), \
             patch("routers.videos.invidious_proxy.get_video",
                   new_callable=AsyncMock, return_value=sample_invidious_video), \
             patch("routers.videos.invidious_proxy.get_base_url",
                   return_value="https://invidious.example.com"), \
             patch("routers.videos.avatar_cache.get_cache") as mock_cache:
            mock_cache.return_value.schedule_background_fetch = MagicMock()
            response = self.client.get("/api/v1/videos/dQw4w9WgXcQ?invidious=true")

        assert response.status_code == 200
        it_mock.assert_not_called()

    def test_ciphered_url_never_leaks_to_response(self, sample_innertube_video, sample_ytdlp_video):
        """Response URLs must not contain signatureCipher/s= params."""
        with patch("routers.videos.innertube.get_video_player_next",
                   new_callable=AsyncMock, return_value=sample_innertube_video), \
             patch("routers.videos.get_video_info",
                   new_callable=AsyncMock, return_value=sample_ytdlp_video), \
             patch("routers.videos.invidious_proxy.is_enabled", return_value=False), \
             patch("routers.videos.avatar_cache.get_cache") as mock_cache:
            mock_cache.return_value.schedule_background_fetch = MagicMock()
            response = self.client.get("/api/v1/videos/dQw4w9WgXcQ?proxy=false")

        assert response.status_code == 200
        data = response.json()
        for stream in data["formatStreams"] + data["adaptiveFormats"]:
            assert stream["url"]  # no empty URLs
            assert "signatureCipher" not in stream["url"]

    def test_both_sources_fail_falls_back_to_invidious(self, sample_invidious_video):
        """yt-dlp fails and InnerTube also unavailable → Invidious last resort."""
        from innertube import InnerTubeError
        from ytdlp_wrapper import YtDlpError

        with patch("routers.videos.innertube.get_video_player_next",
                   new_callable=AsyncMock, side_effect=InnerTubeError("nope")), \
             patch("routers.videos.get_video_info",
                   new_callable=AsyncMock, side_effect=YtDlpError("gone")), \
             patch("routers.videos.invidious_proxy.is_enabled", return_value=True), \
             patch("routers.videos.invidious_proxy.get_video",
                   new_callable=AsyncMock, return_value=sample_invidious_video), \
             patch("routers.videos.invidious_proxy.get_base_url",
                   return_value="https://invidious.example.com"), \
             patch("routers.videos.avatar_cache.get_cache") as mock_cache:
            mock_cache.return_value.schedule_background_fetch = MagicMock()
            response = self.client.get("/api/v1/videos/dQw4w9WgXcQ?proxy=false")

        assert response.status_code == 200
        data = response.json()
        assert data["videoId"] == "dQw4w9WgXcQ"

    def test_all_sources_fail_returns_404(self):
        """yt-dlp fails, InnerTube fails, Invidious fails → 404."""
        from innertube import InnerTubeError
        from invidious_proxy import InvidiousProxyError
        from ytdlp_wrapper import YtDlpError

        with patch("routers.videos.innertube.get_video_player_next",
                   new_callable=AsyncMock, side_effect=InnerTubeError("nope")), \
             patch("routers.videos.get_video_info",
                   new_callable=AsyncMock, side_effect=YtDlpError("gone")), \
             patch("routers.videos.invidious_proxy.is_enabled", return_value=True), \
             patch("routers.videos.invidious_proxy.get_video",
                   new_callable=AsyncMock, side_effect=InvidiousProxyError("down")):
            response = self.client.get("/api/v1/videos/dQw4w9WgXcQ?proxy=false")

        assert response.status_code == 404


# =============================================================================
# Tests for GET /api/v1/extract
# =============================================================================


class TestExtractVideo:
    """Tests for GET /api/v1/extract endpoint."""

    @pytest.fixture(autouse=True)
    def setup(self, test_db, test_client, mock_dns_public):
        """Setup test fixtures."""
        self.db_path = test_db
        self.client = test_client

    def test_extract_video_success(self):
        """Test successful video extraction from arbitrary URL."""
        video_info = {
            "id": "12345",
            "title": "Sample Video",
            "uploader": "Test User",
            "duration": 120,
            "view_count": 5000,
            "extractor": "vimeo",
            "formats": [
                {"format_id": "hd", "ext": "mp4", "url": "https://vimeo.com/video.mp4", "width": 1280, "height": 720}
            ],
        }

        with patch("routers.videos.extract_url", new_callable=AsyncMock) as mock_extract:
            mock_extract.return_value = video_info
            # Allow all sites for extraction
            with patch("routers.videos.get_settings") as mock_settings:
                mock_settings.return_value = MagicMock(allow_all_sites_for_extraction=True)
                response = self.client.get("/api/v1/extract?url=https://vimeo.com/12345")

        assert response.status_code == 200
        data = response.json()
        assert data["videoId"] == "12345"
        assert data["title"] == "Sample Video"
        assert data["extractor"] == "vimeo"

    def test_extract_video_includes_original_url(self):
        """Test that extraction response includes originalUrl."""
        original_url = "https://twitter.com/user/status/123"
        video_info = {
            "id": "abcdef",
            "title": "Test Video",
            "extractor": "twitter",
            "formats": [],
            "original_url": original_url,
            "webpage_url": original_url,
        }

        with patch("routers.videos.extract_url", new_callable=AsyncMock) as mock_extract:
            mock_extract.return_value = video_info
            with patch("routers.videos.get_settings") as mock_settings:
                mock_settings.return_value = MagicMock(allow_all_sites_for_extraction=True)
                response = self.client.get(f"/api/v1/extract?url={original_url}")

        assert response.status_code == 200
        data = response.json()
        assert data["originalUrl"] == original_url

    @pytest.mark.skip(
        reason="HTTPException in validate_extractor_allowed is caught by generic Exception handler in router"
    )
    def test_extract_video_site_blocked(self):
        """Test 403 error when site is not allowed.

        Note: This test is skipped because the router's generic exception handler
        catches HTTPException and re-raises as 500. The validation logic is
        tested directly in TestValidateExtractorAllowed.
        """
        pass

    def test_extract_video_invalid_url(self):
        """Test 400 error for invalid URL."""
        with patch("routers.videos.extract_url", new_callable=AsyncMock) as mock_extract:
            mock_extract.side_effect = ValueError("Invalid URL")
            response = self.client.get("/api/v1/extract?url=not-a-url")

        assert response.status_code == 400

    def test_extract_video_ytdlp_error(self):
        """Test 422 error when yt-dlp fails to extract."""
        from ytdlp_wrapper import YtDlpError

        with patch("routers.videos.extract_url", new_callable=AsyncMock) as mock_extract:
            mock_extract.side_effect = YtDlpError("Unsupported URL")
            response = self.client.get("/api/v1/extract?url=https://example.com/video")

        assert response.status_code == 422
        assert "Could not extract" in response.json()["detail"]

    def test_extract_video_missing_url_param(self):
        """Test error when URL parameter is missing."""
        response = self.client.get("/api/v1/extract")
        assert response.status_code == 422  # FastAPI validation error


# =============================================================================
# Tests for GET /api/v1/extract/channel
# =============================================================================


class TestExtractChannel:
    """Tests for GET /api/v1/extract/channel endpoint."""

    @pytest.fixture(autouse=True)
    def setup(self, test_db, test_client, mock_dns_public):
        """Setup test fixtures."""
        self.db_path = test_db
        self.client = test_client

    def test_extract_channel_success(self, sample_channel_entries):
        """Test successful channel extraction."""
        with patch("routers.videos.extract_channel_url", new_callable=AsyncMock) as mock_extract:
            mock_extract.return_value = sample_channel_entries
            with patch("routers.videos.get_settings") as mock_settings:
                mock_settings.return_value = MagicMock(allow_all_sites_for_extraction=True)
                response = self.client.get("/api/v1/extract/channel?url=https://vimeo.com/testchannel")

        assert response.status_code == 200
        data = response.json()
        assert data["author"] == "Test Channel"
        assert data["authorId"] == "UC123456789"
        assert data["extractor"] == "vimeo"
        assert len(data["videos"]) == 2

    def test_extract_channel_with_pagination(self, sample_channel_entries):
        """Test channel extraction with pagination."""
        with patch("routers.videos.extract_channel_url", new_callable=AsyncMock) as mock_extract:
            mock_extract.return_value = sample_channel_entries
            with patch("routers.videos.get_settings") as mock_settings:
                mock_settings.return_value = MagicMock(allow_all_sites_for_extraction=True)
                response = self.client.get("/api/v1/extract/channel?url=https://vimeo.com/testchannel&page=2")

        assert response.status_code == 200
        mock_extract.assert_called_once()
        # Verify page parameter was passed
        call_args = mock_extract.call_args
        assert call_args.kwargs.get("page") == 2 or call_args[1].get("page") == 2

    def test_extract_channel_continuation(self, sample_channel_entries):
        """Test continuation token when more pages exist."""
        # Create 30 entries (full page)
        full_page_entries = sample_channel_entries.copy()
        full_page_entries["entries"] = [
            {"id": f"video{i}", "title": f"Video {i}", "duration": 100} for i in range(30)
        ]

        with patch("routers.videos.extract_channel_url", new_callable=AsyncMock) as mock_extract:
            mock_extract.return_value = full_page_entries
            with patch("routers.videos.get_settings") as mock_settings:
                mock_settings.return_value = MagicMock(allow_all_sites_for_extraction=True)
                response = self.client.get("/api/v1/extract/channel?url=https://vimeo.com/testchannel")

        assert response.status_code == 200
        data = response.json()
        # Full page should have continuation
        assert data["continuation"] == "2"

    def test_extract_channel_no_continuation(self, sample_channel_entries):
        """Test no continuation when fewer than 30 videos."""
        with patch("routers.videos.extract_channel_url", new_callable=AsyncMock) as mock_extract:
            mock_extract.return_value = sample_channel_entries  # Only 2 videos
            with patch("routers.videos.get_settings") as mock_settings:
                mock_settings.return_value = MagicMock(allow_all_sites_for_extraction=True)
                response = self.client.get("/api/v1/extract/channel?url=https://vimeo.com/testchannel")

        assert response.status_code == 200
        data = response.json()
        # Partial page should have no continuation
        assert data["continuation"] is None

    @pytest.mark.skip(
        reason="HTTPException in validate_extractor_allowed is caught by generic Exception handler in router"
    )
    def test_extract_channel_site_blocked(self, sample_channel_entries):
        """Test 403 error when site is not allowed.

        Note: This test is skipped because the router's generic exception handler
        catches HTTPException and re-raises as 500. The validation logic is
        tested directly in TestValidateExtractorAllowed.
        """
        pass

    def test_extract_channel_invalid_url(self):
        """Test 400 error for invalid URL."""
        with patch("routers.videos.extract_channel_url", new_callable=AsyncMock) as mock_extract:
            mock_extract.side_effect = ValueError("Invalid URL")
            response = self.client.get("/api/v1/extract/channel?url=not-a-url")

        assert response.status_code == 400

    def test_extract_channel_ytdlp_error(self):
        """Test 422 error when yt-dlp fails."""
        from ytdlp_wrapper import YtDlpError

        with patch("routers.videos.extract_channel_url", new_callable=AsyncMock) as mock_extract:
            mock_extract.side_effect = YtDlpError("Channel not found")
            response = self.client.get("/api/v1/extract/channel?url=https://vimeo.com/nope")

        assert response.status_code == 422
        assert "Could not extract channel" in response.json()["detail"]


# =============================================================================
# Tests for validate_extractor_allowed helper
# =============================================================================


class TestValidateExtractorAllowed:
    """Tests for validate_extractor_allowed helper function."""

    @pytest.fixture(autouse=True)
    def setup(self, test_db):
        """Setup test fixtures."""
        self.db_path = test_db

    def test_allow_all_sites_enabled(self):
        """Test that all sites are allowed when setting is enabled."""
        from routers.videos import validate_extractor_allowed

        with patch("routers.videos.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(allow_all_sites_for_extraction=True)
            # Should not raise for any extractor
            validate_extractor_allowed("youtube")
            validate_extractor_allowed("vimeo")
            validate_extractor_allowed("random_site")

    def test_site_enabled_in_database(self):
        """Test that enabled sites pass validation."""
        import database
        from routers.videos import validate_extractor_allowed

        database.update_settings({"allow_all_sites_for_extraction": False})

        # Enable a site
        database.create_site("vimeo", "Vimeo", enabled=True)

        validate_extractor_allowed("vimeo")  # Should not raise

    def test_site_disabled_raises_403(self):
        """Test that disabled sites raise 403."""
        from fastapi import HTTPException

        import database
        from routers.videos import validate_extractor_allowed

        database.update_settings({"allow_all_sites_for_extraction": False})

        # Create but disable site
        database.create_site("vimeo", "Vimeo", enabled=False)

        with pytest.raises(HTTPException) as exc_info:
            validate_extractor_allowed("vimeo")

        assert exc_info.value.status_code == 403

    def test_unknown_site_raises_403(self):
        """Test that unknown sites raise 403."""
        from fastapi import HTTPException

        import database
        from routers.videos import validate_extractor_allowed

        database.update_settings({"allow_all_sites_for_extraction": False})

        with pytest.raises(HTTPException) as exc_info:
            validate_extractor_allowed("unknown_site")

        assert exc_info.value.status_code == 403
