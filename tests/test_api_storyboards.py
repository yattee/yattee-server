"""Tests for routers/storyboards.py - Storyboards endpoint (InnerTube-first)."""

import os
import sys
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


VIDEO_ID = "dQw4w9WgXcQ"


def _storyboard_dict(width: int = 48, height: int = 27) -> dict:
    """Build an Invidious-shaped storyboard entry."""
    return {
        "url": f"https://i.ytimg.com/sb/{VIDEO_ID}/storyboard3_L0/M0.jpg?sigh=abc",
        "templateUrl": f"https://i.ytimg.com/sb/{VIDEO_ID}/storyboard3_L0/M$M.jpg?sigh=abc",
        "width": width,
        "height": height,
        "count": 100,
        "interval": 5000,
        "storyboardWidth": 10,
        "storyboardHeight": 10,
        "storyboardCount": 1,
    }


def _ytdlp_storyboard_format() -> dict:
    """Build a yt-dlp storyboard format entry."""
    return {
        "ext": "mhtml",
        "vcodec": "images",
        "width": 160,
        "height": 90,
        "columns": 5,
        "rows": 5,
        "fragments": [
            {"url": f"https://i.ytimg.com/sb/{VIDEO_ID}/storyboard3_L2/M0.jpg", "duration": 10.0},
            {"url": f"https://i.ytimg.com/sb/{VIDEO_ID}/storyboard3_L2/M1.jpg", "duration": 10.0},
        ],
    }


class TestGetStoryboards:
    @pytest.fixture(autouse=True)
    def setup(self, test_db, test_client):
        self.db_path = test_db
        self.client = test_client

    def test_innertube_happy_path(self):
        """InnerTube returns storyboards; yt-dlp and Invidious are not called."""
        it_response = {"storyboards": [_storyboard_dict(48, 27), _storyboard_dict(160, 90)]}

        with (
            patch("routers.storyboards.innertube.is_enabled", return_value=True),
            patch(
                "routers.storyboards.innertube.get_video_player_next",
                new_callable=AsyncMock,
                return_value=it_response,
            ),
            patch("routers.storyboards.get_video_info", new_callable=AsyncMock) as ytdlp_get,
            patch(
                "routers.storyboards.invidious_proxy.is_enabled", return_value=True
            ),
            patch(
                "routers.storyboards.invidious_proxy.fetch_json", new_callable=AsyncMock
            ) as inv_fetch,
        ):
            response = self.client.get(f"/api/v1/storyboards/{VIDEO_ID}")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["width"] == 48
        assert data[1]["width"] == 160
        assert data[0]["storyboardWidth"] == 10
        ytdlp_get.assert_not_called()
        inv_fetch.assert_not_called()

    def test_innertube_fails_ytdlp_success(self):
        """InnerTube raises -> yt-dlp produces storyboards. Invidious not called."""
        from innertube import InnerTubeError

        with (
            patch("routers.storyboards.innertube.is_enabled", return_value=True),
            patch(
                "routers.storyboards.innertube.get_video_player_next",
                new_callable=AsyncMock,
                side_effect=InnerTubeError("boom"),
            ),
            patch(
                "routers.storyboards.get_video_info",
                new_callable=AsyncMock,
                return_value={"formats": [_ytdlp_storyboard_format()]},
            ),
            patch("routers.storyboards.invidious_proxy.is_enabled", return_value=True),
            patch(
                "routers.storyboards.invidious_proxy.fetch_json", new_callable=AsyncMock
            ) as inv_fetch,
        ):
            response = self.client.get(f"/api/v1/storyboards/{VIDEO_ID}")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["width"] == 160
        assert data[0]["storyboardWidth"] == 5
        assert data[0]["storyboardCount"] == 2
        inv_fetch.assert_not_called()

    def test_innertube_empty_ytdlp_empty_invidious_success(self):
        """Both InnerTube and yt-dlp return empty -> Invidious passthrough."""
        invidious_payload = [_storyboard_dict(48, 27)]

        with (
            patch("routers.storyboards.innertube.is_enabled", return_value=True),
            patch(
                "routers.storyboards.innertube.get_video_player_next",
                new_callable=AsyncMock,
                return_value={"storyboards": []},
            ),
            patch(
                "routers.storyboards.get_video_info",
                new_callable=AsyncMock,
                return_value={"formats": []},
            ),
            patch("routers.storyboards.invidious_proxy.is_enabled", return_value=True),
            patch(
                "routers.storyboards.invidious_proxy.fetch_json",
                new_callable=AsyncMock,
                return_value=invidious_payload,
            ),
        ):
            response = self.client.get(f"/api/v1/storyboards/{VIDEO_ID}")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["width"] == 48

    def test_all_tiers_fail_returns_502(self):
        """InnerTube + yt-dlp + Invidious all fail -> 502."""
        from innertube import InnerTubeError
        from invidious_proxy import InvidiousProxyError
        from ytdlp_wrapper import YtDlpError

        with (
            patch("routers.storyboards.innertube.is_enabled", return_value=True),
            patch(
                "routers.storyboards.innertube.get_video_player_next",
                new_callable=AsyncMock,
                side_effect=InnerTubeError("boom"),
            ),
            patch(
                "routers.storyboards.get_video_info",
                new_callable=AsyncMock,
                side_effect=YtDlpError("nope"),
            ),
            patch("routers.storyboards.invidious_proxy.is_enabled", return_value=True),
            patch(
                "routers.storyboards.invidious_proxy.fetch_json",
                new_callable=AsyncMock,
                side_effect=InvidiousProxyError("also nope"),
            ),
        ):
            response = self.client.get(f"/api/v1/storyboards/{VIDEO_ID}")

        assert response.status_code == 502

    def test_all_tiers_empty_returns_empty_list(self):
        """No errors but no storyboards from any tier -> 200 with []."""
        with (
            patch("routers.storyboards.innertube.is_enabled", return_value=True),
            patch(
                "routers.storyboards.innertube.get_video_player_next",
                new_callable=AsyncMock,
                return_value={"storyboards": []},
            ),
            patch(
                "routers.storyboards.get_video_info",
                new_callable=AsyncMock,
                return_value={"formats": []},
            ),
            patch("routers.storyboards.invidious_proxy.is_enabled", return_value=True),
            patch(
                "routers.storyboards.invidious_proxy.fetch_json",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            response = self.client.get(f"/api/v1/storyboards/{VIDEO_ID}")

        assert response.status_code == 200
        assert response.json() == []

    def test_invalid_video_id_returns_400(self):
        """Malformed video ID -> 400."""
        response = self.client.get("/api/v1/storyboards/not-a-valid-id-too-long")
        assert response.status_code == 400
