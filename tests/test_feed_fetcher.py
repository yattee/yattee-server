"""Tests for feed_fetcher module."""

import os
import sys
from unittest.mock import AsyncMock, patch

import pytest

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from feed_fetcher import (
    _build_channel_url,
    _fetch_channel_metadata_invidious,
    _fetch_channel_metadata_ytdlp,
    _fetch_from_invidious,
    _fetch_from_ytdlp,
    _get_all_thumbnails,
    _get_all_ytdlp_thumbnails,
    _parse_timestamp,
    _process_invidious_video,
    _process_ytdlp_video,
    fetch_channel_feed,
)


class TestBuildChannelUrl:
    """Tests for _build_channel_url function."""

    def test_youtube_handle(self):
        """Test URL building for YouTube handle."""
        url = _build_channel_url("@username", "youtube", "https://youtube.com/@username")
        assert url == "https://www.youtube.com/@username/videos"

    def test_youtube_channel_id(self):
        """Test URL building for YouTube channel ID."""
        url = _build_channel_url("UCabcdef123", "youtube", "https://youtube.com/channel/UCabcdef123")
        assert url == "https://www.youtube.com/channel/UCabcdef123/videos"

    def test_youtube_other_id(self, mock_dns_public):
        """Test URL building for other YouTube IDs falls back to channel_url."""
        url = _build_channel_url("custom123", "youtube", "https://youtube.com/c/custom123")
        assert url == "https://youtube.com/c/custom123"

    def test_non_youtube_site(self, mock_dns_public):
        """Test URL building for non-YouTube sites uses channel_url."""
        url = _build_channel_url("channel123", "dailymotion", "https://dailymotion.com/channel123")
        assert url == "https://dailymotion.com/channel123"


class TestProcessInvidiousVideo:
    """Tests for _process_invidious_video function."""

    def test_processes_video(self):
        """Test processing Invidious video data."""
        video_data = {
            "videoId": "abc123",
            "title": "Test Video",
            "author": "Test Channel",
            "authorId": "UC123",
            "lengthSeconds": 300,
            "viewCount": 1000,
            "published": 1640000000,
            "publishedText": "1 week ago",
            "videoThumbnails": [
                {"url": "/thumb.jpg", "quality": "default", "width": 120, "height": 90}
            ],
        }

        result = _process_invidious_video(video_data, "UC123", "https://inv.example.com")

        assert result["video_id"] == "abc123"
        assert result["title"] == "Test Video"
        assert result["author"] == "Test Channel"
        assert result["author_id"] == "UC123"
        assert result["length_seconds"] == 300
        assert result["view_count"] == 1000
        assert result["published"] == 1640000000
        assert result["video_url"] == "https://www.youtube.com/watch?v=abc123"

    def test_resolves_thumbnail_urls(self):
        """Test that relative thumbnail URLs are resolved."""
        video_data = {
            "videoId": "abc123",
            "title": "Test",
            "videoThumbnails": [
                {"url": "/api/v1/thumbnails/abc123/thumb.jpg", "quality": "default"}
            ],
        }

        result = _process_invidious_video(video_data, "UC123", "https://inv.example.com")

        assert result["thumbnail_url"].startswith("https://inv.example.com")

    def test_handles_missing_fields(self):
        """Test handling of missing fields."""
        video_data = {"videoId": "abc123"}

        result = _process_invidious_video(video_data, "UC123", "https://inv.example.com")

        assert result["video_id"] == "abc123"
        assert result["title"] == ""
        assert result["author"] == ""
        assert result["length_seconds"] == 0


class TestProcessYtdlpVideo:
    """Tests for _process_ytdlp_video function."""

    def test_processes_video(self):
        """Test processing yt-dlp video data."""
        video_data = {
            "id": "abc123",
            "title": "Test Video",
            "channel": "Test Channel",
            "channel_id": "UC123",
            "duration": 300,
            "view_count": 1000,
            "timestamp": 1640000000,
            "upload_date": "20211220",
            "webpage_url": "https://youtube.com/watch?v=abc123",
            "thumbnails": [
                {"url": "https://i.ytimg.com/vi/abc123/default.jpg", "width": 120, "height": 90}
            ],
        }

        result = _process_ytdlp_video(video_data, "UC123")

        assert result["video_id"] == "abc123"
        assert result["title"] == "Test Video"
        assert result["author"] == "Test Channel"
        assert result["author_id"] == "UC123"
        assert result["length_seconds"] == 300
        assert result["view_count"] == 1000
        assert result["published"] == 1640000000

    def test_handles_missing_channel(self):
        """Test handling of missing channel field."""
        video_data = {
            "id": "abc123",
            "title": "Test",
            "uploader": "Uploader Name",
            "uploader_id": "uploader123",
        }

        result = _process_ytdlp_video(video_data, "channel123")

        assert result["author"] == "Uploader Name"
        assert result["author_id"] == "uploader123"


class TestGetAllThumbnails:
    """Tests for _get_all_thumbnails function."""

    def test_returns_best_url_first(self):
        """Test that best quality URL is returned first."""
        thumbnails = [
            {"url": "https://example.com/default.jpg", "quality": "default"},
            {"url": "https://example.com/maxres.jpg", "quality": "maxres"},
            {"url": "https://example.com/high.jpg", "quality": "high"},
        ]

        best_url, all_thumbs = _get_all_thumbnails(thumbnails)

        assert best_url == "https://example.com/maxres.jpg"
        assert len(all_thumbs) == 3

    def test_returns_empty_for_empty_list(self):
        """Test returns empty for empty thumbnail list."""
        best_url, all_thumbs = _get_all_thumbnails([])
        assert best_url == ""
        assert all_thumbs == []


class TestGetAllYtdlpThumbnails:
    """Tests for _get_all_ytdlp_thumbnails function."""

    def test_maps_quality_by_width(self):
        """Test quality is mapped based on width."""
        info = {
            "thumbnails": [
                {"url": "https://example.com/sd.jpg", "width": 640, "height": 480},
                {"url": "https://example.com/hd.jpg", "width": 1280, "height": 720},
            ]
        }

        best_url, all_thumbs = _get_all_ytdlp_thumbnails(info)

        assert best_url == "https://example.com/hd.jpg"
        # Check quality mapping
        qualities = {t["quality"] for t in all_thumbs}
        assert "maxres" in qualities or "sddefault" in qualities

    def test_fallback_to_thumbnail_field(self):
        """Test fallback to single thumbnail field."""
        info = {"thumbnail": "https://example.com/thumb.jpg"}

        best_url, all_thumbs = _get_all_ytdlp_thumbnails(info)

        assert best_url == "https://example.com/thumb.jpg"
        assert len(all_thumbs) == 1

    def test_returns_empty_when_no_thumbnails(self):
        """Test returns empty when no thumbnails available."""
        info = {}

        best_url, all_thumbs = _get_all_ytdlp_thumbnails(info)

        assert best_url == ""
        assert all_thumbs == []


class TestParseTimestamp:
    """Tests for _parse_timestamp function."""

    def test_parses_int(self):
        """Test parsing integer timestamp."""
        assert _parse_timestamp(1640000000) == 1640000000

    def test_parses_yyyymmdd_string(self):
        """Test parsing YYYYMMDD date string."""
        result = _parse_timestamp("20211220")
        assert result is not None
        assert isinstance(result, int)

    def test_parses_iso_format(self):
        """Test parsing ISO format date string."""
        result = _parse_timestamp("2021-12-20T12:00:00Z")
        assert result is not None
        assert isinstance(result, int)

    def test_returns_none_for_none(self):
        """Test returns None for None input."""
        assert _parse_timestamp(None) is None

    def test_returns_none_for_invalid(self):
        """Test returns None for invalid input."""
        assert _parse_timestamp("invalid") is None


class TestFetchChannelMetadataInvidious:
    """Tests for _fetch_channel_metadata_invidious function."""

    @pytest.mark.asyncio
    async def test_returns_metadata(self):
        """Test returns channel metadata."""
        with patch("feed_fetcher.invidious_proxy.get_channel", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {"subCount": 1000, "authorVerified": True}
            result = await _fetch_channel_metadata_invidious("UC123")

            assert result is not None
            assert result["subscriber_count"] == 1000
            assert result["is_verified"] is True

    @pytest.mark.asyncio
    async def test_returns_none_on_error(self):
        """Test returns None on error."""
        with patch("feed_fetcher.invidious_proxy.get_channel", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = ValueError("Error")
            result = await _fetch_channel_metadata_invidious("UC123")
            assert result is None


class TestFetchChannelMetadataYtdlp:
    """Tests for _fetch_channel_metadata_ytdlp function."""

    @pytest.mark.asyncio
    async def test_returns_metadata(self):
        """Test returns channel metadata."""
        with patch("feed_fetcher.get_channel_info", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {"channel_follower_count": 1000, "channel_is_verified": True}
            result = await _fetch_channel_metadata_ytdlp("UC123")

            assert result is not None
            assert result["subscriber_count"] == 1000
            assert result["is_verified"] is True

    @pytest.mark.asyncio
    async def test_returns_none_on_error(self):
        """Test returns None on error."""
        with patch("feed_fetcher.get_channel_info", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = ValueError("Error")
            result = await _fetch_channel_metadata_ytdlp("UC123")
            assert result is None


class TestFetchFromInvidious:
    """Tests for _fetch_from_invidious function."""

    @pytest.mark.asyncio
    async def test_returns_videos_on_success(self):
        """Test returns videos on successful fetch."""
        mock_result = {
            "videos": [{"videoId": "abc123", "title": "Test", "videoThumbnails": []}],
            "total_fetched": 1,
            "pagination_limited": False,
        }

        with (
            patch("feed_fetcher.invidious_proxy.get_channel_videos_multi_page", new_callable=AsyncMock) as mock_fetch,
            patch("feed_fetcher.invidious_proxy.get_base_url", return_value="https://inv.example.com"),
            patch("feed_fetcher.get_settings") as mock_settings,
        ):
            mock_settings.return_value.feed_fallback_ytdlp_on_414 = False
            mock_fetch.return_value = mock_result

            videos, pagination_info, should_fallback, fallback_reason = await _fetch_from_invidious("UC123", 30)

            assert videos is not None
            assert len(videos) == 1
            assert should_fallback is False
            assert fallback_reason is None

    @pytest.mark.asyncio
    async def test_returns_fallback_on_414_error(self):
        """Test returns fallback when 414 error occurs."""
        mock_result = {
            "videos": [{"videoId": "abc123", "title": "Test", "videoThumbnails": []}],
            "pagination_limited": True,
            "limit_reason": "414_error",
            "total_fetched": 10,
        }

        with (
            patch("feed_fetcher.invidious_proxy.get_channel_videos_multi_page", new_callable=AsyncMock) as mock_fetch,
            patch("feed_fetcher.get_settings") as mock_settings,
        ):
            mock_settings.return_value.feed_fallback_ytdlp_on_414 = True
            mock_fetch.return_value = mock_result

            videos, pagination_info, should_fallback, fallback_reason = await _fetch_from_invidious("UC123", 30)

            assert should_fallback is True
            assert fallback_reason == "invidious_error_414"

    @pytest.mark.asyncio
    async def test_returns_fallback_on_empty_result(self):
        """Test returns fallback when no videos."""
        with patch("feed_fetcher.invidious_proxy.get_channel_videos_multi_page", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = None

            videos, pagination_info, should_fallback, fallback_reason = await _fetch_from_invidious("UC123", 30)

            assert should_fallback is True
            assert fallback_reason == "no_videos"

    @pytest.mark.asyncio
    async def test_returns_fallback_on_retryable_invidious_error(self):
        """Test returns fallback when Invidious returns retryable error (500, 502, etc.)."""
        from invidious_proxy import InvidiousProxyError

        with (
            patch("feed_fetcher.invidious_proxy.get_channel_videos_multi_page", new_callable=AsyncMock) as mock_fetch,
            patch("feed_fetcher.get_settings") as mock_settings,
        ):
            mock_settings.return_value.feed_fallback_ytdlp_on_error = True
            mock_fetch.side_effect = InvidiousProxyError.from_http_status(500, "HTTP 500: Internal Server Error")

            videos, pagination_info, should_fallback, fallback_reason = await _fetch_from_invidious("UC123", 30)

            assert should_fallback is True
            assert fallback_reason == "invidious_error_500"

    @pytest.mark.asyncio
    async def test_raises_on_non_retryable_invidious_error(self):
        """Test raises error when Invidious returns non-retryable error (400, 404, etc.)."""
        from invidious_proxy import InvidiousProxyError

        with (
            patch("feed_fetcher.invidious_proxy.get_channel_videos_multi_page", new_callable=AsyncMock) as mock_fetch,
            patch("feed_fetcher.get_settings") as mock_settings,
        ):
            mock_settings.return_value.feed_fallback_ytdlp_on_error = True
            mock_fetch.side_effect = InvidiousProxyError.from_http_status(404, "HTTP 404: Not Found")

            with pytest.raises(InvidiousProxyError):
                await _fetch_from_invidious("UC123", 30)

    @pytest.mark.asyncio
    async def test_raises_on_retryable_error_when_fallback_disabled(self):
        """Test raises error when fallback is disabled even for retryable errors."""
        from invidious_proxy import InvidiousProxyError

        with (
            patch("feed_fetcher.invidious_proxy.get_channel_videos_multi_page", new_callable=AsyncMock) as mock_fetch,
            patch("feed_fetcher.get_settings") as mock_settings,
        ):
            mock_settings.return_value.feed_fallback_ytdlp_on_error = False
            mock_fetch.side_effect = InvidiousProxyError.from_http_status(500, "HTTP 500: Internal Server Error")

            with pytest.raises(InvidiousProxyError):
                await _fetch_from_invidious("UC123", 30)

    @pytest.mark.asyncio
    async def test_returns_fallback_on_connection_error(self):
        """Test returns fallback on connection errors."""
        from invidious_proxy import InvidiousProxyError

        with (
            patch("feed_fetcher.invidious_proxy.get_channel_videos_multi_page", new_callable=AsyncMock) as mock_fetch,
            patch("feed_fetcher.get_settings") as mock_settings,
        ):
            mock_settings.return_value.feed_fallback_ytdlp_on_error = True
            mock_fetch.side_effect = InvidiousProxyError.from_connection_error("Connection refused")

            videos, pagination_info, should_fallback, fallback_reason = await _fetch_from_invidious("UC123", 30)

            assert should_fallback is True
            assert fallback_reason == "invidious_error_connection"


class TestFetchFromYtdlp:
    """Tests for _fetch_from_ytdlp function."""

    @pytest.mark.asyncio
    async def test_returns_videos(self):
        """Test returns videos from yt-dlp output."""
        ytdlp_output = '{"id": "abc123", "title": "Test", "channel": "Test Channel", "duration": 300}\n'

        with patch("feed_fetcher.run_ytdlp", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = ytdlp_output

            videos, metadata = await _fetch_from_ytdlp("UC123", "youtube", "https://youtube.com/@test", 30, False)

            assert len(videos) == 1
            assert videos[0]["video_id"] == "abc123"

    @pytest.mark.asyncio
    async def test_uses_flat_playlist_when_enabled(self):
        """Test uses --flat-playlist flag when enabled."""
        with patch("feed_fetcher.run_ytdlp", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = ""

            await _fetch_from_ytdlp("UC123", "youtube", "https://youtube.com/@test", 30, True)

            call_args = mock_run.call_args[0]
            assert "--flat-playlist" in call_args


class TestFetchChannelFeed:
    """Tests for fetch_channel_feed function."""

    @pytest.mark.asyncio
    async def test_uses_invidious_for_youtube(self):
        """Test uses Invidious for YouTube channels."""
        with (
            patch("feed_fetcher.get_settings") as mock_settings,
            patch("feed_fetcher.invidious_proxy.is_enabled", return_value=True),
            patch("feed_fetcher._fetch_from_invidious", new_callable=AsyncMock) as mock_invidious,
            patch("feed_fetcher._fetch_channel_metadata_invidious", new_callable=AsyncMock) as mock_meta,
        ):
            mock_settings.return_value.feed_max_videos = 30
            mock_settings.return_value.feed_ytdlp_use_flat_playlist = True
            mock_invidious.return_value = ([{"video_id": "abc123"}], {"total_fetched": 1}, False, None)
            mock_meta.return_value = {"subscriber_count": 1000}

            videos, pagination_info, metadata = await fetch_channel_feed("UC123", "youtube", "https://youtube.com/@test")

            assert len(videos) == 1
            mock_invidious.assert_called_once()

    @pytest.mark.asyncio
    async def test_falls_back_to_ytdlp(self):
        """Test falls back to yt-dlp when Invidious fails."""
        with (
            patch("feed_fetcher.get_settings") as mock_settings,
            patch("feed_fetcher.invidious_proxy.is_enabled", return_value=True),
            patch("feed_fetcher._fetch_from_invidious", new_callable=AsyncMock) as mock_invidious,
            patch("feed_fetcher._fetch_from_ytdlp", new_callable=AsyncMock) as mock_ytdlp,
        ):
            mock_settings.return_value.feed_max_videos = 30
            mock_settings.return_value.feed_ytdlp_use_flat_playlist = True
            mock_invidious.return_value = (None, None, True, "invidious_error_500")  # Should fallback
            mock_ytdlp.return_value = ([{"video_id": "abc123"}], None)

            videos, pagination_info, metadata = await fetch_channel_feed("UC123", "youtube", "https://youtube.com/@test")

            mock_ytdlp.assert_called_once()

    @pytest.mark.asyncio
    async def test_uses_ytdlp_for_non_youtube(self):
        """Test uses yt-dlp directly for non-YouTube sites."""
        with (
            patch("feed_fetcher.get_settings") as mock_settings,
            patch("feed_fetcher.invidious_proxy.is_enabled", return_value=True),
            patch("feed_fetcher._fetch_from_ytdlp", new_callable=AsyncMock) as mock_ytdlp,
        ):
            mock_settings.return_value.feed_max_videos = 30
            mock_settings.return_value.feed_ytdlp_use_flat_playlist = True
            mock_ytdlp.return_value = ([{"video_id": "abc123"}], None)

            videos, pagination_info, metadata = await fetch_channel_feed("channel123", "dailymotion", "https://dailymotion.com/channel123")

            mock_ytdlp.assert_called_once()
