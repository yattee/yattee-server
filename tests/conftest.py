"""Shared test fixtures for Yattee Server tests."""

import asyncio
import base64
import json
import os
import sqlite3

# Add project root to path
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


# =============================================================================
# Test Database Fixtures
# =============================================================================


@pytest.fixture
def temp_db_path(tmp_path):
    """Create a temporary database file path."""
    # Use 'yattee.db' to match what Alembic expects (DATA_DIR/yattee.db)
    return str(tmp_path / "yattee.db")


@pytest.fixture
def test_db(temp_db_path, monkeypatch, tmp_path):
    """Create a fresh test database with schema initialized.

    This fixture patches the database connection to use a temporary file.
    """
    import config
    import database.connection
    import database.schema

    # Patch config.DATA_DIR for Alembic migrations
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))

    # Patch the DB_PATH and get_db_path function for direct database access
    monkeypatch.setattr(database.connection, "DB_PATH", temp_db_path)
    monkeypatch.setattr(database.connection, "get_db_path", lambda: temp_db_path)

    # Initialize the database schema
    database.schema.init_db()

    yield temp_db_path

    # Cleanup happens automatically with tmp_path


@pytest.fixture
def test_db_with_user(test_db):
    """Test database with a pre-created test user and basic auth enabled."""
    import database

    # Create a test user (password: "testpass")
    # Generated with: bcrypt.hashpw(b'testpass', bcrypt.gensalt()).decode()
    password_hash = "$2b$12$pJ5eMI//Nexk7FDlXOniB.0gEH0tVpZYPOEoBm97k83AsXrYVZKC2"
    database.create_user("testuser", password_hash, is_admin=False)
    database.create_user("adminuser", password_hash, is_admin=True)

    # Enable basic auth so authenticated endpoints work correctly
    database.set_basic_auth_enabled(True)

    return test_db


@pytest.fixture
def test_db_connection(test_db):
    """Get a test database connection."""
    conn = sqlite3.connect(test_db)
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()


# =============================================================================
# Mock yt-dlp Subprocess Fixtures
# =============================================================================


class MockProcess:
    """Mock asyncio subprocess for yt-dlp calls."""

    def __init__(
        self,
        stdout: str = "",
        stderr: str = "",
        returncode: int = 0,
    ):
        self.stdout = stdout.encode() if isinstance(stdout, str) else stdout
        self.stderr = stderr.encode() if isinstance(stderr, str) else stderr
        self.returncode = returncode
        self._killed = False

    async def communicate(self):
        return self.stdout, self.stderr

    async def wait(self):
        return self.returncode

    def kill(self):
        self._killed = True


@pytest.fixture
def mock_ytdlp_video():
    """Sample yt-dlp video info response."""
    return {
        "id": "dQw4w9WgXcQ",
        "title": "Test Video Title",
        "description": "Test video description",
        "uploader": "Test Channel",
        "uploader_id": "UCuAXFkgsw1L7xaCfnd5JJOw",
        "uploader_url": "https://www.youtube.com/channel/UCuAXFkgsw1L7xaCfnd5JJOw",
        "channel": "Test Channel",
        "channel_id": "UCuAXFkgsw1L7xaCfnd5JJOw",
        "duration": 212,
        "view_count": 1234567,
        "like_count": 12345,
        "upload_date": "20230615",
        "thumbnail": "https://i.ytimg.com/vi/dQw4w9WgXcQ/maxresdefault.jpg",
        "thumbnails": [
            {
                "url": "https://i.ytimg.com/vi/dQw4w9WgXcQ/default.jpg",
                "width": 120,
                "height": 90,
            },
            {
                "url": "https://i.ytimg.com/vi/dQw4w9WgXcQ/maxresdefault.jpg",
                "width": 1280,
                "height": 720,
            },
        ],
        "formats": [
            {
                "format_id": "18",
                "ext": "mp4",
                "url": "https://example.com/video.mp4",
                "width": 640,
                "height": 360,
                "vcodec": "avc1.42001E",
                "acodec": "mp4a.40.2",
                "fps": 30,
                "tbr": 500,
            },
            {
                "format_id": "137",
                "ext": "mp4",
                "url": "https://example.com/video_hd.mp4",
                "width": 1920,
                "height": 1080,
                "vcodec": "avc1.640028",
                "acodec": "none",
                "fps": 30,
                "tbr": 4000,
            },
            {
                "format_id": "140",
                "ext": "m4a",
                "url": "https://example.com/audio.m4a",
                "vcodec": "none",
                "acodec": "mp4a.40.2",
                "abr": 128,
            },
        ],
        "subtitles": {
            "en": [
                {"ext": "vtt", "url": "https://example.com/captions_en.vtt"},
            ],
        },
        "automatic_captions": {
            "en": [
                {"ext": "vtt", "url": "https://example.com/auto_captions_en.vtt"},
            ],
        },
        "extractor": "youtube",
        "extractor_key": "Youtube",
        "webpage_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    }


@pytest.fixture
def mock_ytdlp_search():
    """Sample yt-dlp search results (JSONL format)."""
    results = [
        {
            "id": "video1",
            "title": "Search Result 1",
            "uploader": "Channel 1",
            "channel_id": "UC1111111111111111111111",
            "duration": 120,
            "view_count": 1000,
        },
        {
            "id": "video2",
            "title": "Search Result 2",
            "uploader": "Channel 2",
            "channel_id": "UC2222222222222222222222",
            "duration": 240,
            "view_count": 2000,
        },
    ]
    return "\n".join(json.dumps(r) for r in results)


@pytest.fixture
def mock_ytdlp_channel():
    """Sample yt-dlp channel info response."""
    return {
        "uploader": "Test Channel",
        "uploader_id": "UCuAXFkgsw1L7xaCfnd5JJOw",
        "channel": "Test Channel",
        "channel_id": "UCuAXFkgsw1L7xaCfnd5JJOw",
        "channel_url": "https://www.youtube.com/channel/UCuAXFkgsw1L7xaCfnd5JJOw",
        "channel_follower_count": 1000000,
        "description": "Test channel description",
        "extractor": "youtube",
        "extractor_key": "Youtube",
    }


@pytest.fixture
def mock_ytdlp(mock_ytdlp_video, mock_ytdlp_search, mock_ytdlp_channel):
    """Mock yt-dlp subprocess execution.

    This fixture provides a mock for asyncio.create_subprocess_exec that
    returns appropriate responses based on the yt-dlp command arguments.
    """
    responses = {
        "video": mock_ytdlp_video,
        "search": mock_ytdlp_search,
        "channel": mock_ytdlp_channel,
    }

    async def mock_subprocess(*args, **kwargs):
        cmd_args = args
        cmd_str = " ".join(str(a) for a in cmd_args)

        # Determine response based on command pattern
        if "ytsearch" in cmd_str or "search_query" in cmd_str:
            return MockProcess(stdout=responses["search"])
        elif "watch?v=" in cmd_str:
            return MockProcess(stdout=json.dumps(responses["video"]))
        elif "/videos" in cmd_str or "/channel/" in cmd_str:
            return MockProcess(stdout=json.dumps(responses["channel"]))
        else:
            # Default: return video info
            return MockProcess(stdout=json.dumps(responses["video"]))

    with patch("asyncio.create_subprocess_exec", side_effect=mock_subprocess) as mock:
        mock.responses = responses
        yield mock


@pytest.fixture
def mock_ytdlp_error():
    """Mock yt-dlp subprocess that returns an error."""

    async def mock_subprocess(*args, **kwargs):
        return MockProcess(
            stdout="",
            stderr="ERROR: Video unavailable",
            returncode=1,
        )

    with patch("asyncio.create_subprocess_exec", side_effect=mock_subprocess):
        yield


@pytest.fixture
def mock_ytdlp_timeout():
    """Mock yt-dlp subprocess that times out."""

    async def mock_subprocess(*args, **kwargs):
        proc = MockProcess()

        async def slow_communicate():
            await asyncio.sleep(10)  # This will timeout
            return b"", b""

        proc.communicate = slow_communicate
        return proc

    with patch("asyncio.create_subprocess_exec", side_effect=mock_subprocess):
        yield


# =============================================================================
# Mock HTTP Client Fixtures (for Invidious proxy)
# =============================================================================


@pytest.fixture
def mock_invidious_video():
    """Sample Invidious video response."""
    return {
        "videoId": "dQw4w9WgXcQ",
        "title": "Test Video Title",
        "description": "Test video description",
        "author": "Test Channel",
        "authorId": "UCuAXFkgsw1L7xaCfnd5JJOw",
        "authorUrl": "/channel/UCuAXFkgsw1L7xaCfnd5JJOw",
        "lengthSeconds": 212,
        "viewCount": 1234567,
        "likeCount": 12345,
        "published": 1686787200,
        "publishedText": "6 months ago",
        "videoThumbnails": [
            {
                "quality": "maxres",
                "url": "https://invidious.example.com/vi/dQw4w9WgXcQ/maxres.jpg",
                "width": 1280,
                "height": 720,
            },
        ],
        "formatStreams": [
            {
                "itag": "18",
                "url": "https://example.com/video.mp4",
                "type": "video/mp4",
                "quality": "360p",
                "container": "mp4",
            },
        ],
        "adaptiveFormats": [
            {
                "itag": "137",
                "url": "https://example.com/video_hd.mp4",
                "type": "video/mp4",
                "bitrate": "4000000",
                "container": "mp4",
            },
        ],
        "captions": [
            {
                "label": "English",
                "language_code": "en",
                "url": "/api/v1/captions/dQw4w9WgXcQ?label=English",
            },
        ],
    }


@pytest.fixture
def mock_invidious_channel():
    """Sample Invidious channel response."""
    return {
        "author": "Test Channel",
        "authorId": "UCuAXFkgsw1L7xaCfnd5JJOw",
        "authorUrl": "/channel/UCuAXFkgsw1L7xaCfnd5JJOw",
        "authorThumbnails": [
            {
                "url": "https://invidious.example.com/ggpht/channel_avatar.jpg",
                "width": 100,
                "height": 100,
            },
        ],
        "subCount": 1000000,
        "totalViews": 500000000,
        "description": "Test channel description",
        "latestVideos": [
            {
                "videoId": "video1",
                "title": "Latest Video 1",
                "lengthSeconds": 300,
                "viewCount": 10000,
            },
        ],
    }


@pytest.fixture
def mock_httpx(mock_invidious_video, mock_invidious_channel):
    """Mock httpx.AsyncClient for Invidious proxy calls.

    Use pytest-httpx for more sophisticated mocking if needed.
    """
    mock_client = AsyncMock()

    async def mock_get(url, **kwargs):
        response = MagicMock()
        response.status_code = 200

        if "/api/v1/videos/" in url:
            response.json.return_value = mock_invidious_video
            response.text = json.dumps(mock_invidious_video)
        elif "/api/v1/channels/" in url:
            response.json.return_value = mock_invidious_channel
            response.text = json.dumps(mock_invidious_channel)
        else:
            response.json.return_value = {}
            response.text = "{}"

        response.raise_for_status = MagicMock()
        return response

    mock_client.get = mock_get
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("httpx.AsyncClient", return_value=mock_client):
        yield mock_client


# =============================================================================
# FastAPI TestClient Fixtures
# =============================================================================


@pytest.fixture
def test_settings(monkeypatch):
    """Override settings for tests."""
    from settings import Settings

    test_settings = Settings(
        ytdlp_path="yt-dlp",
        ytdlp_timeout=30,
        cache_video_ttl=60,
        cache_search_ttl=60,
        cache_channel_ttl=60,
        max_search_results=20,
        invidious_instance=None,
        invidious_timeout=10,
        invidious_author_thumbnails=False,
        feed_fetch_interval=1800,
        feed_channel_delay=2,
        feed_fallback_ytdlp_on_error=True,
        feed_video_max_age=30,
    )

    # Patch get_settings to return our test settings
    with patch("settings.get_settings", return_value=test_settings):
        with patch("settings._cached_settings", test_settings):
            yield test_settings


@pytest.fixture
def app_no_lifespan(test_db, test_settings, mock_ytdlp, monkeypatch):
    """Create FastAPI app without lifespan events (no background tasks)."""
    from contextlib import asynccontextmanager

    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware

    import database
    from basic_auth import BasicAuthMiddleware
    from routers import (
        admin,
        channels,
        comments,
        playlists,
        proxy,
        search,
        subscriptions,
        videos,
    )

    # Simple lifespan that skips background tasks
    @asynccontextmanager
    async def test_lifespan(app: FastAPI):
        database.init_db()
        yield

    app = FastAPI(lifespan=test_lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,  # Cannot use credentials with wildcard origin
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(BasicAuthMiddleware)

    app.include_router(videos.router, prefix="/api/v1")
    app.include_router(search.router, prefix="/api/v1")
    app.include_router(channels.router, prefix="/api/v1")
    app.include_router(playlists.router, prefix="/api/v1")
    app.include_router(proxy.router, prefix="/proxy")
    app.include_router(comments.router, prefix="/api/v1")
    app.include_router(subscriptions.router, prefix="/api/v1")
    app.include_router(admin.router)

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return app


@pytest.fixture
def test_client(app_no_lifespan):
    """FastAPI TestClient without authentication."""
    with TestClient(app_no_lifespan) as client:
        yield client


@pytest.fixture
def authenticated_client(app_no_lifespan, test_db_with_user):
    """FastAPI TestClient with Basic Auth headers for test user."""
    credentials = base64.b64encode(b"testuser:testpass").decode()
    auth_headers = {"Authorization": f"Basic {credentials}"}

    with TestClient(app_no_lifespan) as client:
        # Patch all requests to include auth header
        original_request = client.request

        def request_with_auth(method, url, **kwargs):
            # Handle headers properly - it might be None even if set
            request_headers = kwargs.get("headers") or {}
            request_headers.update(auth_headers)
            kwargs["headers"] = request_headers
            return original_request(method, url, **kwargs)

        client.request = request_with_auth
        yield client


@pytest.fixture
def admin_client(app_no_lifespan, test_db_with_user):
    """FastAPI TestClient with Basic Auth headers for admin user."""
    credentials = base64.b64encode(b"adminuser:testpass").decode()
    auth_headers = {"Authorization": f"Basic {credentials}"}

    with TestClient(app_no_lifespan) as client:
        original_request = client.request

        def request_with_auth(method, url, **kwargs):
            # Handle headers properly - it might be None even if set
            request_headers = kwargs.get("headers") or {}
            request_headers.update(auth_headers)
            kwargs["headers"] = request_headers
            return original_request(method, url, **kwargs)

        client.request = request_with_auth
        yield client


# =============================================================================
# Utility Fixtures
# =============================================================================


@pytest.fixture
def reset_caches():
    """Reset all yt-dlp caches before test."""
    import ytdlp_wrapper

    ytdlp_wrapper.reset_caches()
    yield
    ytdlp_wrapper.reset_caches()


@pytest.fixture
def sample_video_id():
    """Valid YouTube video ID for testing."""
    return "dQw4w9WgXcQ"


@pytest.fixture
def sample_channel_id():
    """Valid YouTube channel ID for testing."""
    return "UCuAXFkgsw1L7xaCfnd5JJOw"


@pytest.fixture
def sample_playlist_id():
    """Valid YouTube playlist ID for testing."""
    return "PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf"


# =============================================================================
# Pytest Configuration
# =============================================================================


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_dns_public():
    """Mock DNS resolution to return public IP addresses.

    This is needed because pytest-httpx mocks return IPs in the 198.18.0.0/15 range
    which are classified as private by Python's ipaddress module. For tests that
    need to verify SSRF protection allows public URLs, we mock DNS to return
    actual public IPs.
    """
    import socket

    from security import clear_dns_cache

    # Clear DNS cache before and after test
    clear_dns_cache()

    # Mock DNS resolution to return public IP (8.8.8.8 - Google's DNS)
    def mock_getaddrinfo(hostname, port, family=0, type=0, proto=0, flags=0):
        # Return a public IP for any hostname
        return [(socket.AF_INET, socket.SOCK_STREAM, 0, '', ('8.8.8.8', 80))]

    original_getaddrinfo = socket.getaddrinfo

    socket.getaddrinfo = mock_getaddrinfo
    yield
    socket.getaddrinfo = original_getaddrinfo
    clear_dns_cache()


# Configure pytest-asyncio
pytest_plugins = ["pytest_asyncio"]
