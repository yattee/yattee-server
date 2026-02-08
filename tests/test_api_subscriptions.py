"""Tests for routers/subscriptions.py - Stateless Feed API endpoints."""

import json
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
def sample_cached_videos():
    """Sample cached video data."""
    return [
        {
            "video_id": "video1xxxxx",
            "title": "First Video",
            "author": "Rick Astley",
            "author_id": "UCuAXFkgsw1L7xaCfnd5JJOw",
            "length_seconds": 300,
            "published": 1704067200,
            "published_text": "1 week ago",
            "view_count": 100000,
            "thumbnail_url": "https://i.ytimg.com/vi/video1/default.jpg",
            "thumbnail_data": json.dumps(
                [{"quality": "default", "url": "https://i.ytimg.com/vi/video1/default.jpg"}]
            ),
            "site": "youtube",
            "video_url": "https://www.youtube.com/watch?v=video1xxxxx",
            "subscription_channel_name": "Rick Astley",
        },
        {
            "video_id": "video2xxxxx",
            "title": "Second Video",
            "author": "Rick Astley",
            "author_id": "UCuAXFkgsw1L7xaCfnd5JJOw",
            "length_seconds": 600,
            "published": 1703462400,
            "published_text": "2 weeks ago",
            "view_count": 200000,
            "thumbnail_url": "https://i.ytimg.com/vi/video2/default.jpg",
            "thumbnail_data": None,
            "site": "youtube",
            "video_url": "https://www.youtube.com/watch?v=video2xxxxx",
            "subscription_channel_name": "Rick Astley",
        },
    ]


# =============================================================================
# Tests for POST /api/v1/feed (stateless)
# =============================================================================


class TestPostFeed:
    """Tests for POST /api/v1/feed endpoint (stateless)."""

    @pytest.fixture(autouse=True)
    def setup(self, test_db, test_client, mock_dns_public):
        """Setup test fixtures."""
        self.db_path = test_db
        self.client = test_client

    def test_post_feed_empty_channels(self):
        """Test posting empty channel list."""
        response = self.client.post("/api/v1/feed", json={"channels": []})

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ready"
        assert data["videos"] == []

    def test_post_feed_with_cached_channels(self, sample_cached_videos):
        """Test feed with cached channels."""
        channels = [
            {
                "channel_id": "UCchannel1",
                "site": "youtube",
                "channel_name": "Channel 1",
                "channel_url": "https://youtube.com/c/1",
            }
        ]

        with patch("database.upsert_watched_channels"):
            with patch(
                "database.get_cached_channel_ids", return_value={("UCchannel1", "youtube")}
            ):
                with patch("database.get_errored_channel_ids", return_value=set()):
                    with patch(
                        "database.get_feed_for_channels", return_value=sample_cached_videos
                    ):
                        with patch("database.get_feed_count_for_channels", return_value=2):
                            with patch("avatar_cache.get_cache") as mock_cache:
                                mock_cache.return_value.schedule_background_fetch = (
                                    MagicMock()
                                )
                                response = self.client.post(
                                    "/api/v1/feed", json={"channels": channels}
                                )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ready"
        assert data["ready_count"] == 1
        assert data["pending_count"] == 0

    def test_post_feed_with_uncached_channels(self):
        """Test feed with uncached channels triggers fetch."""
        channels = [
            {
                "channel_id": "UCnewchannel",
                "site": "youtube",
                "channel_name": "New Channel",
                "channel_url": "https://youtube.com/c/new",
            }
        ]

        with patch("database.upsert_watched_channels"):
            with patch("database.get_cached_channel_ids", return_value=set()):  # No cached
                with patch("database.get_errored_channel_ids", return_value=set()):
                    with patch("database.get_feed_for_channels", return_value=[]):
                        with patch("database.get_feed_count_for_channels", return_value=0):
                            with patch("avatar_cache.get_cache") as mock_cache:
                                mock_cache.return_value.schedule_background_fetch = (
                                    MagicMock()
                                )
                                with patch(
                                    "feed_fetcher.fetch_single_channel",
                                    new_callable=AsyncMock,
                                ):
                                    response = self.client.post(
                                        "/api/v1/feed", json={"channels": channels}
                                    )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "fetching"
        assert data["pending_count"] == 1
        assert data["eta_seconds"] is not None

    def test_post_feed_with_errored_channels(self):
        """Test feed counts errored channels separately."""
        channels = [
            {"channel_id": "UCerrored", "site": "youtube"},
            {"channel_id": "UCcached", "site": "youtube"},
        ]

        with patch("database.upsert_watched_channels"):
            with patch(
                "database.get_cached_channel_ids", return_value={("UCcached", "youtube")}
            ):
                with patch(
                    "database.get_errored_channel_ids",
                    return_value={("UCerrored", "youtube")},
                ):
                    with patch("database.get_feed_for_channels", return_value=[]):
                        with patch("database.get_feed_count_for_channels", return_value=0):
                            with patch("avatar_cache.get_cache") as mock_cache:
                                mock_cache.return_value.schedule_background_fetch = (
                                    MagicMock()
                                )
                                response = self.client.post(
                                    "/api/v1/feed", json={"channels": channels}
                                )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ready"
        assert data["ready_count"] == 1
        assert data["error_count"] == 1
        assert data["pending_count"] == 0


# =============================================================================
# Tests for POST /api/v1/feed/status
# =============================================================================


class TestPostFeedStatus:
    """Tests for POST /api/v1/feed/status endpoint."""

    @pytest.fixture(autouse=True)
    def setup(self, test_db, test_client):
        """Setup test fixtures."""
        self.db_path = test_db
        self.client = test_client

    def test_feed_status_empty(self):
        """Test feed status with empty channel list."""
        response = self.client.post("/api/v1/feed/status", json={"channels": []})

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ready"
        assert data["ready_count"] == 0
        assert data["pending_count"] == 0

    def test_feed_status_all_cached(self):
        """Test feed status when all channels are cached."""
        channels = [
            {"channel_id": "UCchannel1", "site": "youtube"},
            {"channel_id": "UCchannel2", "site": "youtube"},
        ]

        with patch(
            "database.get_cached_channel_ids",
            return_value={("UCchannel1", "youtube"), ("UCchannel2", "youtube")},
        ):
            with patch("database.get_errored_channel_ids", return_value=set()):
                response = self.client.post(
                    "/api/v1/feed/status", json={"channels": channels}
                )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ready"
        assert data["ready_count"] == 2
        assert data["pending_count"] == 0

    def test_feed_status_some_pending(self):
        """Test feed status with some pending channels."""
        channels = [
            {"channel_id": "UCcached", "site": "youtube"},
            {"channel_id": "UCpending", "site": "youtube"},
        ]

        with patch(
            "database.get_cached_channel_ids", return_value={("UCcached", "youtube")}
        ):
            with patch("database.get_errored_channel_ids", return_value=set()):
                response = self.client.post(
                    "/api/v1/feed/status", json={"channels": channels}
                )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "fetching"
        assert data["ready_count"] == 1
        assert data["pending_count"] == 1

    def test_feed_status_with_errors(self):
        """Test feed status with errored channels."""
        channels = [
            {"channel_id": "UCcached", "site": "youtube"},
            {"channel_id": "UCerrored", "site": "youtube"},
        ]

        with patch(
            "database.get_cached_channel_ids", return_value={("UCcached", "youtube")}
        ):
            with patch(
                "database.get_errored_channel_ids",
                return_value={("UCerrored", "youtube")},
            ):
                response = self.client.post(
                    "/api/v1/feed/status", json={"channels": channels}
                )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ready"  # No pending, so ready
        assert data["ready_count"] == 1
        assert data["error_count"] == 1
        assert data["pending_count"] == 0
