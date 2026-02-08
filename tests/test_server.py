"""Tests for server.py - main application endpoints."""

import os
import sys

import pytest

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


# =============================================================================
# Tests for /info endpoint
# =============================================================================


class TestInfoEndpoint:
    """Tests for /info endpoint."""

    @pytest.fixture(autouse=True)
    def setup(self, test_db, test_settings, mock_ytdlp, monkeypatch):
        """Setup test fixtures with the real app."""
        from contextlib import asynccontextmanager

        from fastapi import FastAPI
        from fastapi.middleware.cors import CORSMiddleware
        from fastapi.testclient import TestClient

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
        from server import info

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

        # Register the /info endpoint from server.py
        app.get("/info")(info)

        with TestClient(app) as client:
            self.client = client
            yield

    def test_info_returns_name(self):
        """Test /info returns server name."""
        response = self.client.get("/info")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Yattee Server"

    def test_info_returns_version(self):
        """Test /info returns server version."""
        response = self.client.get("/info")
        assert response.status_code == 200
        data = response.json()
        assert "version" in data
        assert data["version"] == "1.0.0"

    def test_info_returns_dependencies(self):
        """Test /info returns dependencies section."""
        response = self.client.get("/info")
        assert response.status_code == 200
        data = response.json()
        assert "dependencies" in data
        assert "yt-dlp" in data["dependencies"]
        assert "ffmpeg" in data["dependencies"]

    def test_info_returns_config(self):
        """Test /info returns config section."""
        response = self.client.get("/info")
        assert response.status_code == 200
        data = response.json()
        assert "config" in data
        config = data["config"]
        assert "cache_video_ttl" in config
        assert "cache_search_ttl" in config
        assert "cache_channel_ttl" in config
        assert "ytdlp_timeout" in config
        assert "invidious_instance" in config

    def test_info_returns_allow_all_sites_flag(self):
        """Test /info returns allow_all_sites_for_extraction in config."""
        response = self.client.get("/info")
        assert response.status_code == 200
        data = response.json()
        assert "config" in data
        assert "allow_all_sites_for_extraction" in data["config"]
        # Should be a boolean
        assert isinstance(data["config"]["allow_all_sites_for_extraction"], bool)

    def test_info_returns_sites_list(self):
        """Test /info returns sites list."""
        response = self.client.get("/info")
        assert response.status_code == 200
        data = response.json()
        assert "sites" in data
        # Sites should be a list
        assert isinstance(data["sites"], list)

    def test_info_sites_structure(self):
        """Test /info sites have correct structure."""
        # First add a test site to the database
        from database.repositories.sites import create_site

        create_site(
            name="YouTube",
            extractor_pattern="youtube",
            enabled=True,
        )

        response = self.client.get("/info")
        assert response.status_code == 200
        data = response.json()

        # Should have at least one site now
        assert len(data["sites"]) >= 1

        # Each site should have name and extractor_pattern
        for site in data["sites"]:
            assert "name" in site
            assert "extractor_pattern" in site
            # Name should be a string
            assert isinstance(site["name"], str)
            # extractor_pattern should be a string (possibly empty)
            assert isinstance(site["extractor_pattern"], str)

    def test_info_sites_no_credentials_exposed(self):
        """Test /info does not expose site credentials."""
        # Add a site with credentials
        from database.repositories.sites import add_credential, create_site

        site_id = create_site(
            name="TestSite",
            extractor_pattern="testsite",
            enabled=True,
        )
        # Add credentials to the site
        add_credential(
            site_id=site_id,
            credential_type="userpass",
            value="secret_username:secret_password",
        )

        response = self.client.get("/info")
        assert response.status_code == 200
        data = response.json()

        # Find the test site
        test_site = next((s for s in data["sites"] if s["name"] == "TestSite"), None)
        assert test_site is not None

        # Credentials should not be in the response
        assert "credentials" not in test_site
        assert "cookies_source" not in test_site
        # The response text should not contain the secret
        assert "secret_username" not in response.text
        assert "secret_password" not in response.text


class TestInfoEndpointWithSites:
    """Tests for /info endpoint with different site configurations."""

    @pytest.fixture
    def app_with_info(self, test_db, test_settings, mock_ytdlp, monkeypatch):
        """Create app with /info endpoint."""
        from contextlib import asynccontextmanager

        from fastapi import FastAPI
        from fastapi.middleware.cors import CORSMiddleware

        import database
        from basic_auth import BasicAuthMiddleware
        from routers import admin
        from server import info

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
        app.include_router(admin.router)
        app.get("/info")(info)

        return app

    def test_info_with_multiple_enabled_sites(self, app_with_info):
        """Test /info returns multiple enabled sites."""
        from fastapi.testclient import TestClient

        from database.repositories.sites import create_site

        # Add multiple sites
        create_site(name="YouTube", extractor_pattern="youtube", enabled=True)
        create_site(name="Vimeo", extractor_pattern="vimeo", enabled=True)
        create_site(name="Twitter", extractor_pattern="twitter", enabled=False)  # Disabled

        with TestClient(app_with_info) as client:
            response = client.get("/info")
            assert response.status_code == 200
            data = response.json()

            # Should only return enabled sites
            site_names = [s["name"] for s in data["sites"]]
            assert "YouTube" in site_names
            assert "Vimeo" in site_names
            assert "Twitter" not in site_names  # Disabled sites not included

    def test_info_with_empty_extractor_pattern(self, app_with_info):
        """Test /info handles sites with empty extractor_pattern."""
        from fastapi.testclient import TestClient

        from database.repositories.sites import create_site

        # Add site with empty extractor_pattern
        create_site(name="GenericSite", extractor_pattern="", enabled=True)

        with TestClient(app_with_info) as client:
            response = client.get("/info")
            assert response.status_code == 200
            data = response.json()

            # Should not fail, extractor_pattern should be empty string
            generic_site = next((s for s in data["sites"] if s["name"] == "GenericSite"), None)
            assert generic_site is not None
            assert generic_site["extractor_pattern"] == ""
