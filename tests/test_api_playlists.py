"""Tests for routers/playlists.py - Playlist API endpoints (InnerTube-first)."""

import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


# =============================================================================
# Fixtures – InnerTube browse responses
# =============================================================================


def _playlist_video_entry(video_id: str, title: str, length_seconds: int = 120) -> dict:
    """Build a minimal playlistVideoRenderer entry."""
    return {
        "playlistVideoRenderer": {
            "videoId": video_id,
            "title": {"runs": [{"text": title}]},
            "shortBylineText": {
                "runs": [
                    {
                        "text": "Test Channel",
                        "navigationEndpoint": {
                            "browseEndpoint": {"browseId": "UCtestchannelid00000000"},
                        },
                    }
                ]
            },
            "lengthSeconds": str(length_seconds),
        }
    }


def _continuation_entry(token: str) -> dict:
    return {
        "continuationItemRenderer": {
            "continuationEndpoint": {"continuationCommand": {"token": token}}
        }
    }


@pytest.fixture
def innertube_playlist_response():
    """Legacy playlistHeaderRenderer shape with 3 videos and a continuation."""
    return {
        "header": {
            "playlistHeaderRenderer": {
                "title": {"simpleText": "My Test Playlist"},
                "descriptionText": {"simpleText": "A playlist for testing"},
                "ownerText": {
                    "runs": [
                        {
                            "text": "Test Owner",
                            "navigationEndpoint": {
                                "browseEndpoint": {"browseId": "UCowner000000000000000"},
                            },
                        }
                    ]
                },
                "numVideosText": {"simpleText": "5 videos"},
            }
        },
        "contents": {
            "twoColumnBrowseResultsRenderer": {
                "tabs": [
                    {
                        "tabRenderer": {
                            "content": {
                                "sectionListRenderer": {
                                    "contents": [
                                        {
                                            "itemSectionRenderer": {
                                                "contents": [
                                                    {
                                                        "playlistVideoListRenderer": {
                                                            "contents": [
                                                                _playlist_video_entry("vid0000001a", "First", 100),
                                                                _playlist_video_entry("vid0000002b", "Second", 200),
                                                                _playlist_video_entry("vid0000003c", "Third", 300),
                                                                _continuation_entry("TOKEN_PAGE_2"),
                                                            ]
                                                        }
                                                    }
                                                ]
                                            }
                                        }
                                    ]
                                }
                            }
                        }
                    }
                ]
            }
        },
    }


@pytest.fixture
def innertube_playlist_continuation_response():
    """Continuation response with 2 more videos and no further token."""
    return {
        "onResponseReceivedActions": [
            {
                "appendContinuationItemsAction": {
                    "continuationItems": [
                        _playlist_video_entry("vid0000004d", "Fourth", 400),
                        _playlist_video_entry("vid0000005e", "Fifth", 500),
                    ]
                }
            }
        ]
    }


@pytest.fixture
def innertube_playlist_newformat_response():
    """pageHeaderRenderer + lockupViewModel variant."""
    return {
        "header": {
            "pageHeaderRenderer": {
                "content": {
                    "pageHeaderViewModel": {
                        "title": {"dynamicTextViewModel": {"text": {"content": "New Format Playlist"}}},
                        "description": {
                            "descriptionPreviewViewModel": {"description": {"content": "Modern UI playlist"}}
                        },
                        "metadata": {
                            "contentMetadataViewModel": {
                                "metadataRows": [
                                    {
                                        "metadataParts": [
                                            {
                                                "text": {
                                                    "content": "New Owner",
                                                    "commandRuns": [
                                                        {
                                                            "onTap": {
                                                                "innertubeCommand": {
                                                                    "browseEndpoint": {
                                                                        "browseId": "UCnewowner00000000000"
                                                                    }
                                                                }
                                                            }
                                                        }
                                                    ],
                                                }
                                            }
                                        ]
                                    }
                                ]
                            }
                        },
                    }
                }
            }
        },
        "contents": {
            "twoColumnBrowseResultsRenderer": {
                "tabs": [
                    {
                        "tabRenderer": {
                            "content": {
                                "sectionListRenderer": {
                                    "contents": [
                                        {
                                            "itemSectionRenderer": {
                                                "contents": [
                                                    {
                                                        "playlistVideoListRenderer": {
                                                            "contents": [
                                                                _playlist_video_entry("vid000000aa", "Alpha", 111),
                                                                _playlist_video_entry("vid000000bb", "Beta", 222),
                                                            ]
                                                        }
                                                    }
                                                ]
                                            }
                                        }
                                    ]
                                }
                            }
                        }
                    }
                ]
            }
        },
    }


@pytest.fixture
def innertube_empty_playlist_response():
    """Valid header but zero videos."""
    return {
        "header": {
            "playlistHeaderRenderer": {
                "title": {"simpleText": "Empty Playlist"},
                "ownerText": {"runs": [{"text": "Owner"}]},
                "numVideosText": {"simpleText": "0 videos"},
            }
        },
        "contents": {
            "twoColumnBrowseResultsRenderer": {
                "tabs": [
                    {
                        "tabRenderer": {
                            "content": {
                                "sectionListRenderer": {
                                    "contents": [
                                        {
                                            "itemSectionRenderer": {
                                                "contents": [{"playlistVideoListRenderer": {"contents": []}}]
                                            }
                                        }
                                    ]
                                }
                            }
                        }
                    }
                ]
            }
        },
    }


@pytest.fixture
def invidious_playlist_response():
    """Standard /api/v1/playlists/{id} shape."""
    return {
        "playlistId": "PLinvidiousxxxx",
        "title": "Invidious Playlist",
        "description": "From Invidious",
        "author": "Inv Owner",
        "authorId": "UCinvowner00000000000",
        "videoCount": 2,
        "videos": [
            {
                "videoId": "invvid00001",
                "title": "Inv 1",
                "author": "Inv Owner",
                "authorId": "UCinvowner00000000000",
                "lengthSeconds": 90,
                "videoThumbnails": [{"quality": "default", "url": "https://x/y.jpg", "width": 120, "height": 90}],
            },
            {
                "videoId": "invvid00002",
                "title": "Inv 2",
                "author": "Inv Owner",
                "authorId": "UCinvowner00000000000",
                "lengthSeconds": 180,
                "videoThumbnails": [],
            },
        ],
    }


@pytest.fixture
def ytdlp_playlist_response():
    """Raw yt-dlp --flat-playlist shape."""
    return {
        "id": "PLytdlpxxxxx",
        "title": "yt-dlp Playlist",
        "description": "From yt-dlp",
        "uploader": "yt Owner",
        "uploader_id": "UCytowner0000000000000",
        "entries": [
            {
                "id": "ytvid000001",
                "title": "Yt 1",
                "channel": "yt Owner",
                "channel_id": "UCytowner0000000000000",
                "duration": 60,
            }
        ],
    }


# =============================================================================
# Tests for GET /api/v1/playlists/{playlist_id}
# =============================================================================


class TestGetPlaylist:
    """Router-level tests for /api/v1/playlists/{playlist_id}."""

    @pytest.fixture(autouse=True)
    def setup(self, test_db, test_client):
        self.db_path = test_db
        self.client = test_client

    def test_playlist_innertube_happy_path(self, innertube_playlist_response, innertube_playlist_continuation_response):
        """InnerTube returns the playlist; Invidious + yt-dlp never called."""
        post_mock = AsyncMock(side_effect=[innertube_playlist_response, innertube_playlist_continuation_response])
        with (
            patch("innertube._playlists.innertube_post", post_mock),
            patch("routers.playlists.invidious_proxy.is_enabled", return_value=True) as inv_enabled,
            patch("routers.playlists.invidious_proxy.get_playlist", new_callable=AsyncMock) as inv_get,
            patch("routers.playlists.get_playlist_info", new_callable=AsyncMock) as ytdlp_get,
        ):
            response = self.client.get("/api/v1/playlists/PLxyz123")

        assert response.status_code == 200
        data = response.json()
        assert data["playlistId"] == "PLxyz123"
        assert data["title"] == "My Test Playlist"
        assert data["author"] == "Test Owner"
        assert data["authorId"] == "UCowner000000000000000"
        assert len(data["videos"]) == 5  # 3 + 2 continuation
        assert data["videos"][0]["videoId"] == "vid0000001a"
        assert data["videos"][4]["videoId"] == "vid0000005e"
        inv_get.assert_not_called()
        ytdlp_get.assert_not_called()
        # is_enabled may be checked or not; just ensure Invidious path wasn't used
        _ = inv_enabled

    def test_playlist_innertube_newformat(self, innertube_playlist_newformat_response):
        """pageHeaderRenderer path works for modern responses."""
        with (
            patch(
                "innertube._playlists.innertube_post",
                AsyncMock(return_value=innertube_playlist_newformat_response),
            ),
            patch("routers.playlists.invidious_proxy.is_enabled", return_value=False),
        ):
            response = self.client.get("/api/v1/playlists/PLnewfmt")

        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "New Format Playlist"
        assert data["author"] == "New Owner"
        assert data["authorId"] == "UCnewowner00000000000"
        assert len(data["videos"]) == 2

    def test_playlist_innertube_fail_invidious_success(self, invidious_playlist_response):
        """InnerTube raises -> Invidious returns the playlist."""
        from innertube import InnerTubeError

        with (
            patch("innertube._playlists.innertube_post", AsyncMock(side_effect=InnerTubeError("boom"))),
            patch("routers.playlists.get_settings") as mock_settings,
            patch("routers.playlists.invidious_proxy.is_enabled", return_value=True),
            patch(
                "routers.playlists.invidious_proxy.get_playlist",
                new_callable=AsyncMock,
                return_value=invidious_playlist_response,
            ),
            patch("routers.playlists.invidious_proxy.get_base_url", return_value="https://inv.example.com"),
            patch("routers.playlists.get_playlist_info", new_callable=AsyncMock) as ytdlp_get,
        ):
            mock_settings.return_value = MagicMock(invidious_proxy_playlists=True)
            response = self.client.get("/api/v1/playlists/PLinvidiousxxxx")

        assert response.status_code == 200
        data = response.json()
        assert data["playlistId"] == "PLinvidiousxxxx"
        assert data["author"] == "Inv Owner"
        assert len(data["videos"]) == 2
        ytdlp_get.assert_not_called()

    def test_playlist_invidious_flag_off_goes_to_ytdlp(self, ytdlp_playlist_response):
        """InnerTube fails + invidious_proxy_playlists=False -> yt-dlp serves."""
        from innertube import InnerTubeError

        with (
            patch("innertube._playlists.innertube_post", AsyncMock(side_effect=InnerTubeError("x"))),
            patch("routers.playlists.get_settings") as mock_settings,
            patch("routers.playlists.invidious_proxy.is_enabled", return_value=True),
            patch("routers.playlists.invidious_proxy.get_playlist", new_callable=AsyncMock) as inv_get,
            patch(
                "routers.playlists.get_playlist_info",
                new_callable=AsyncMock,
                return_value=ytdlp_playlist_response,
            ),
        ):
            mock_settings.return_value = MagicMock(invidious_proxy_playlists=False)
            response = self.client.get("/api/v1/playlists/PLytdlpxxxxx")

        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "yt-dlp Playlist"
        assert data["author"] == "yt Owner"
        assert len(data["videos"]) == 1
        inv_get.assert_not_called()

    def test_playlist_all_fail_raises_404(self):
        """All three tiers fail -> 404."""
        from innertube import InnerTubeError
        from invidious_proxy import InvidiousProxyError
        from ytdlp_wrapper import YtDlpError

        with (
            patch("innertube._playlists.innertube_post", AsyncMock(side_effect=InnerTubeError("x"))),
            patch("routers.playlists.get_settings") as mock_settings,
            patch("routers.playlists.invidious_proxy.is_enabled", return_value=True),
            patch(
                "routers.playlists.invidious_proxy.get_playlist",
                new_callable=AsyncMock,
                side_effect=InvidiousProxyError("nope"),
            ),
            patch(
                "routers.playlists.get_playlist_info",
                new_callable=AsyncMock,
                side_effect=YtDlpError("also nope"),
            ),
        ):
            mock_settings.return_value = MagicMock(invidious_proxy_playlists=True)
            response = self.client.get("/api/v1/playlists/PLmissing")

        assert response.status_code == 404

    def test_playlist_innertube_returns_none_falls_through(self, ytdlp_playlist_response):
        """InnerTube returns None -> fall through silently to yt-dlp."""
        with (
            patch("routers.playlists.innertube.get_playlist", new_callable=AsyncMock, return_value=None),
            patch("routers.playlists.get_settings") as mock_settings,
            patch("routers.playlists.invidious_proxy.is_enabled", return_value=False),
            patch(
                "routers.playlists.get_playlist_info",
                new_callable=AsyncMock,
                return_value=ytdlp_playlist_response,
            ),
        ):
            mock_settings.return_value = MagicMock(invidious_proxy_playlists=False)
            response = self.client.get("/api/v1/playlists/PLytdlpxxxxx")

        assert response.status_code == 200
        assert response.json()["title"] == "yt-dlp Playlist"

    def test_playlist_empty_innertube(self, innertube_empty_playlist_response):
        """Valid header + zero videos -> 200 with empty list."""
        with (
            patch(
                "innertube._playlists.innertube_post",
                AsyncMock(return_value=innertube_empty_playlist_response),
            ),
            patch("routers.playlists.invidious_proxy.is_enabled", return_value=False),
        ):
            response = self.client.get("/api/v1/playlists/PLempty")

        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Empty Playlist"
        # videoCount from header is 0; video list is empty
        assert data["videos"] == []

    def test_playlist_innertube_disabled_uses_invidious(self, invidious_playlist_response):
        """When innertube.is_enabled() is False, InnerTube branch is skipped."""
        with (
            patch("routers.playlists.innertube.is_enabled", return_value=False),
            patch("routers.playlists.innertube.get_playlist", new_callable=AsyncMock) as it_get,
            patch("routers.playlists.get_settings") as mock_settings,
            patch("routers.playlists.invidious_proxy.is_enabled", return_value=True),
            patch(
                "routers.playlists.invidious_proxy.get_playlist",
                new_callable=AsyncMock,
                return_value=invidious_playlist_response,
            ),
            patch("routers.playlists.invidious_proxy.get_base_url", return_value="https://inv.example.com"),
        ):
            mock_settings.return_value = MagicMock(invidious_proxy_playlists=True)
            response = self.client.get("/api/v1/playlists/PLinvidiousxxxx")

        assert response.status_code == 200
        assert response.json()["playlistId"] == "PLinvidiousxxxx"
        it_get.assert_not_called()


# =============================================================================
# Unit tests for innertube._playlists + playlist_video_renderer_to_invidious
# =============================================================================


class TestGetPlaylistUnit:
    """Direct unit tests for the InnerTube playlist parser."""

    @pytest.mark.asyncio
    async def test_get_playlist_parses_legacy_header(self, innertube_playlist_response):
        from innertube._playlists import get_playlist

        # Provide no continuation so we don't hit page 2
        response = dict(innertube_playlist_response)
        tab = response["contents"]["twoColumnBrowseResultsRenderer"]["tabs"][0]
        tab["tabRenderer"]["content"]["sectionListRenderer"]["contents"][0]["itemSectionRenderer"]["contents"][0][
            "playlistVideoListRenderer"
        ]["contents"] = response["contents"]["twoColumnBrowseResultsRenderer"]["tabs"][0]["tabRenderer"]["content"][
            "sectionListRenderer"
        ]["contents"][0]["itemSectionRenderer"]["contents"][0]["playlistVideoListRenderer"]["contents"][:3]

        with patch("innertube._playlists.innertube_post", AsyncMock(return_value=response)):
            result = await get_playlist("PLxyz")

        assert result is not None
        assert result["playlistId"] == "PLxyz"
        assert result["title"] == "My Test Playlist"
        assert result["author"] == "Test Owner"
        assert result["authorId"] == "UCowner000000000000000"
        assert len(result["videos"]) == 3
        assert result["videos"][0]["videoId"] == "vid0000001a"
        assert result["videos"][0]["lengthSeconds"] == 100

    @pytest.mark.asyncio
    async def test_get_playlist_pagination_stops_at_cap(self):
        """An infinite continuation loop must terminate at _MAX_PAGES."""
        from innertube import _playlists

        infinite_page = {
            "onResponseReceivedActions": [
                {
                    "appendContinuationItemsAction": {
                        "continuationItems": [
                            _playlist_video_entry("vidloop0001", "Loop"),
                            _continuation_entry("LOOP_FOREVER"),
                        ]
                    }
                }
            ]
        }
        first_page = {
            "header": {
                "playlistHeaderRenderer": {
                    "title": {"simpleText": "Loopy"},
                    "ownerText": {"runs": [{"text": "L"}]},
                }
            },
            "contents": {
                "twoColumnBrowseResultsRenderer": {
                    "tabs": [
                        {
                            "tabRenderer": {
                                "content": {
                                    "sectionListRenderer": {
                                        "contents": [
                                            {
                                                "itemSectionRenderer": {
                                                    "contents": [
                                                        {
                                                            "playlistVideoListRenderer": {
                                                                "contents": [
                                                                    _playlist_video_entry("vidloop0000", "Seed"),
                                                                    _continuation_entry("LOOP_FOREVER"),
                                                                ]
                                                            }
                                                        }
                                                    ]
                                                }
                                            }
                                        ]
                                    }
                                }
                            }
                        }
                    ]
                }
            },
        }

        with (
            patch.object(_playlists, "_MAX_PAGES", 3),
            patch(
                "innertube._playlists.innertube_post",
                AsyncMock(side_effect=[first_page] + [infinite_page] * 10),
            ),
        ):
            result = await _playlists.get_playlist("PLloop")

        assert result is not None
        # First page (1 video) + 2 continuation pages (1 each) = 3 videos
        assert len(result["videos"]) == 3

    def test_playlist_video_renderer_to_invidious_defaults(self):
        """Minimal renderer yields sensible defaults."""
        from innertube._converters import playlist_video_renderer_to_invidious

        result = playlist_video_renderer_to_invidious(
            {"videoId": "abc1234xxxx", "title": {"simpleText": "Bare Title"}}
        )

        assert result["type"] == "video"
        assert result["videoId"] == "abc1234xxxx"
        assert result["title"] == "Bare Title"
        assert result["lengthSeconds"] == 0
        assert result["viewCount"] == 0
        assert result["liveNow"] is False
        assert result["videoThumbnails"]  # standard CDN fallback populated

    def test_playlist_video_renderer_live_detection(self):
        """LIVE thumbnail overlay sets liveNow=True."""
        from innertube._converters import playlist_video_renderer_to_invidious

        result = playlist_video_renderer_to_invidious(
            {
                "videoId": "livexxxx001",
                "title": {"simpleText": "Live Now"},
                "thumbnailOverlays": [
                    {"thumbnailOverlayTimeStatusRenderer": {"style": "LIVE"}},
                ],
            }
        )

        assert result["liveNow"] is True
