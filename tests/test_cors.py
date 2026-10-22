"""Tests for CORS configuration security."""

import os
import sys

from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import config
from server import configure_cors


class TestCorsConfiguration:
    """Tests for CORS middleware configuration."""

    def test_cors_disabled_by_default(self, monkeypatch):
        """Test that CORS is disabled when no configuration is provided."""
        monkeypatch.setattr(config, "CORS_ORIGINS", "")
        monkeypatch.setattr(config, "CORS_ALLOW_ALL", False)

        app = FastAPI()
        configure_cors(app)

        @app.get("/test")
        def test_endpoint():
            return {"status": "ok"}

        client = TestClient(app)
        response = client.get("/test", headers={"Origin": "https://evil.example.com"})

        # No CORS headers should be present
        assert "access-control-allow-origin" not in response.headers

    def test_cors_with_specific_origins(self, monkeypatch):
        """Test CORS with specific allowed origins."""
        monkeypatch.setattr(config, "CORS_ORIGINS", "https://app.example.com,https://admin.example.com")
        monkeypatch.setattr(config, "CORS_ALLOW_ALL", False)
        monkeypatch.setattr(config, "CORS_ALLOW_CREDENTIALS", True)

        app = FastAPI()
        configure_cors(app)

        @app.get("/test")
        def test_endpoint():
            return {"status": "ok"}

        client = TestClient(app)

        # Allowed origin should work
        response = client.get("/test", headers={"Origin": "https://app.example.com"})
        assert response.headers.get("access-control-allow-origin") == "https://app.example.com"
        assert response.headers.get("access-control-allow-credentials") == "true"

        # Disallowed origin should be blocked
        response = client.get("/test", headers={"Origin": "https://evil.example.com"})
        assert response.headers.get("access-control-allow-origin") != "https://evil.example.com"

    def test_cors_allow_all_disables_credentials(self, monkeypatch):
        """Test that CORS_ALLOW_ALL mode disables credentials for security."""
        monkeypatch.setattr(config, "CORS_ORIGINS", "")
        monkeypatch.setattr(config, "CORS_ALLOW_ALL", True)
        monkeypatch.setattr(config, "CORS_ALLOW_CREDENTIALS", True)  # Should be ignored

        app = FastAPI()
        configure_cors(app)

        @app.get("/test")
        def test_endpoint():
            return {"status": "ok"}

        client = TestClient(app)
        response = client.get("/test", headers={"Origin": "https://any-origin.example.com"})

        # Origin should be allowed
        assert response.headers.get("access-control-allow-origin") == "*"
        # Credentials should NOT be allowed (security requirement)
        assert response.headers.get("access-control-allow-credentials") != "true"

    def test_cors_origins_takes_precedence_over_allow_all(self, monkeypatch):
        """Test that CORS_ORIGINS takes precedence when both are set."""
        monkeypatch.setattr(config, "CORS_ORIGINS", "https://app.example.com")
        monkeypatch.setattr(config, "CORS_ALLOW_ALL", True)
        monkeypatch.setattr(config, "CORS_ALLOW_CREDENTIALS", True)

        app = FastAPI()
        configure_cors(app)

        @app.get("/test")
        def test_endpoint():
            return {"status": "ok"}

        client = TestClient(app)

        # Only the specific origin should work, not wildcard
        response = client.get("/test", headers={"Origin": "https://app.example.com"})
        assert response.headers.get("access-control-allow-origin") == "https://app.example.com"
        assert response.headers.get("access-control-allow-credentials") == "true"

    def test_cors_preflight_request(self, monkeypatch):
        """Test CORS preflight (OPTIONS) request handling."""
        monkeypatch.setattr(config, "CORS_ORIGINS", "https://app.example.com")
        monkeypatch.setattr(config, "CORS_ALLOW_ALL", False)
        monkeypatch.setattr(config, "CORS_ALLOW_CREDENTIALS", True)

        app = FastAPI()
        configure_cors(app)

        @app.post("/api/data")
        def post_endpoint():
            return {"status": "created"}

        client = TestClient(app)

        # Preflight request
        response = client.options(
            "/api/data",
            headers={
                "Origin": "https://app.example.com",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Content-Type, Authorization",
            },
        )

        assert response.status_code == 200
        assert response.headers.get("access-control-allow-origin") == "https://app.example.com"
        assert "POST" in response.headers.get("access-control-allow-methods", "")
        assert response.headers.get("access-control-allow-credentials") == "true"

    def test_cors_credentials_disabled(self, monkeypatch):
        """Test CORS with credentials explicitly disabled."""
        monkeypatch.setattr(config, "CORS_ORIGINS", "https://app.example.com")
        monkeypatch.setattr(config, "CORS_ALLOW_ALL", False)
        monkeypatch.setattr(config, "CORS_ALLOW_CREDENTIALS", False)

        app = FastAPI()
        configure_cors(app)

        @app.get("/test")
        def test_endpoint():
            return {"status": "ok"}

        client = TestClient(app)
        response = client.get("/test", headers={"Origin": "https://app.example.com"})

        assert response.headers.get("access-control-allow-origin") == "https://app.example.com"
        # Credentials header should not be present or should be false
        assert response.headers.get("access-control-allow-credentials") != "true"


class TestMiddlewareOrder:
    """CORS has to answer before Basic Auth rejects requests without credentials."""

    def _app(self, monkeypatch):
        from server import configure_middleware

        monkeypatch.setattr(config, "CORS_ORIGINS", "https://app.example.com")
        monkeypatch.setattr(config, "CORS_ALLOW_ALL", False)
        monkeypatch.setattr(config, "CORS_ALLOW_CREDENTIALS", True)

        app = FastAPI()

        @app.get("/api/v1/search")
        def search():
            return []

        configure_middleware(app)
        return TestClient(app)

    def test_preflight_is_answered_without_credentials(self, monkeypatch, test_db_with_user):
        response = self._app(monkeypatch).options(
            "/api/v1/search",
            headers={
                "Origin": "https://app.example.com",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "Authorization",
            },
        )

        assert response.status_code == 200
        assert response.headers.get("access-control-allow-origin") == "https://app.example.com"
        assert "authorization" in response.headers.get("access-control-allow-headers", "").lower()

    def test_authentication_errors_are_readable_cross_origin(self, monkeypatch, test_db_with_user):
        response = self._app(monkeypatch).get("/api/v1/search", headers={"Origin": "https://app.example.com"})

        assert response.status_code == 401
        assert response.headers.get("access-control-allow-origin") == "https://app.example.com"
