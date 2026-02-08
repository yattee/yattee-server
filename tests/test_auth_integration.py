"""Tests for authentication integration - middleware, rate limiting, public paths."""

import base64
import os
import sys
import time
from unittest.mock import patch

import pytest

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


# =============================================================================
# Tests for Basic Auth middleware
# =============================================================================


class TestBasicAuthMiddleware:
    """Tests for Basic Auth middleware behavior."""

    @pytest.fixture(autouse=True)
    def setup(self, test_db_with_user, test_client, authenticated_client):
        """Setup test fixtures."""
        self.client = test_client
        self.auth_client = authenticated_client

    def test_unauthenticated_request_to_protected_endpoint(self):
        """Test that unauthenticated requests to protected endpoints return 401."""
        response = self.client.get("/api/v1/search?q=test")
        assert response.status_code == 401
        assert "WWW-Authenticate" in response.headers

    def test_authenticated_request_succeeds(self):
        """Test that authenticated requests succeed."""
        with patch("routers.search.search", return_value=[]):
            response = self.auth_client.get("/api/v1/search?q=test")
        assert response.status_code == 200

    def test_invalid_credentials(self):
        """Test that invalid credentials return 401."""
        credentials = base64.b64encode(b"testuser:wrongpassword").decode()
        response = self.client.get(
            "/api/v1/search?q=test",
            headers={"Authorization": f"Basic {credentials}"},
        )
        assert response.status_code == 401

    def test_nonexistent_user(self):
        """Test that nonexistent user returns 401."""
        credentials = base64.b64encode(b"nobody:password").decode()
        response = self.client.get(
            "/api/v1/search?q=test",
            headers={"Authorization": f"Basic {credentials}"},
        )
        assert response.status_code == 401

    def test_malformed_authorization_header(self):
        """Test handling of malformed Authorization header."""
        response = self.client.get(
            "/api/v1/search?q=test",
            headers={"Authorization": "NotBasic invalid"},
        )
        assert response.status_code == 401

    def test_empty_authorization_header(self):
        """Test handling of empty Authorization header."""
        response = self.client.get(
            "/api/v1/search?q=test",
            headers={"Authorization": ""},
        )
        assert response.status_code == 401

    def test_basic_auth_without_colon(self):
        """Test handling of Basic auth without colon separator."""
        invalid_creds = base64.b64encode(b"userwithoutpassword").decode()
        response = self.client.get(
            "/api/v1/search?q=test",
            headers={"Authorization": f"Basic {invalid_creds}"},
        )
        assert response.status_code == 401


# =============================================================================
# Tests for public endpoints
# =============================================================================


class TestPublicEndpoints:
    """Tests for public endpoints that don't require authentication."""

    @pytest.fixture(autouse=True)
    def setup(self, test_db, test_client):
        """Setup test fixtures - uses test_db without users."""
        self.client = test_client

    def test_health_endpoint_public(self):
        """Test that health endpoint is public."""
        response = self.client.get("/health")
        assert response.status_code == 200

    def test_post_feed_stateless_public(self):
        """Test that stateless feed endpoint is public."""
        response = self.client.post("/api/v1/feed", json={"channels": []})
        assert response.status_code == 200

    def test_feed_status_public(self):
        """Test that feed status endpoint is public."""
        response = self.client.post("/api/v1/feed/status", json={"channels": []})
        assert response.status_code == 200


class TestPublicEndpointsWithUsers:
    """Tests for public endpoints when users exist."""

    @pytest.fixture(autouse=True)
    def setup(self, test_db_with_user, test_client):
        """Setup test fixtures - uses test_db with users."""
        self.client = test_client

    def test_health_endpoint_still_public(self):
        """Test that health endpoint remains public when users exist."""
        response = self.client.get("/health")
        assert response.status_code == 200

    def test_post_feed_requires_auth_when_users_exist(self):
        """Test that stateless feed requires auth when users exist (not in PUBLIC_PATHS)."""
        # When users exist and basic auth is enabled, all non-public endpoints require auth
        response = self.client.post("/api/v1/feed", json={"channels": []})
        # This endpoint is not in PUBLIC_PATHS, so it requires auth
        assert response.status_code == 401


# =============================================================================
# Tests for rate limiting
# =============================================================================


class TestRateLimiting:
    """Tests for authentication rate limiting."""

    @pytest.fixture(autouse=True)
    def setup(self, test_db_with_user, test_client):
        """Setup test fixtures."""
        self.client = test_client
        # Clear rate limiting state
        import basic_auth

        basic_auth._failed_attempts.clear()

    def test_rate_limit_after_failed_attempts(self):
        """Test that rate limiting kicks in after multiple failed attempts."""
        from settings import get_settings

        s = get_settings()

        # Simulate multiple failed attempts
        for _ in range(s.rate_limit_max_failures):
            bad_creds = base64.b64encode(b"testuser:wrongpass").decode()
            self.client.get(
                "/api/v1/search?q=test",
                headers={"Authorization": f"Basic {bad_creds}"},
            )

        # Next request should be rate limited
        bad_creds = base64.b64encode(b"testuser:wrongpass").decode()
        response = self.client.get(
            "/api/v1/search?q=test",
            headers={"Authorization": f"Basic {bad_creds}"},
        )
        assert response.status_code == 429
        assert "Too many failed" in response.json()["detail"]

    def test_rate_limit_expires(self):
        """Test that rate limit expires after window."""
        import basic_auth
        from settings import get_settings

        s = get_settings()

        # Set up old failed attempts (outside the window)
        old_time = time.time() - s.rate_limit_window - 10
        basic_auth._failed_attempts["testclient"] = [old_time] * s.rate_limit_max_failures

        # Request should not be rate limited
        bad_creds = base64.b64encode(b"testuser:wrongpass").decode()
        response = self.client.get(
            "/api/v1/search?q=test",
            headers={"Authorization": f"Basic {bad_creds}"},
        )
        # Should be 401 (invalid creds) not 429 (rate limited)
        assert response.status_code == 401


# =============================================================================
# Tests for setup/no-user mode
# =============================================================================


class TestSetupMode:
    """Tests for behavior when no users exist (setup mode)."""

    @pytest.fixture(autouse=True)
    def setup(self, test_db, test_client):
        """Setup test fixtures - uses test_db without users."""
        self.client = test_client

    def test_protected_endpoints_accessible_without_users(self):
        """Test that protected endpoints work when no users exist (setup mode)."""
        # When no users exist, middleware allows access
        with patch("routers.search.search", return_value=[]):
            response = self.client.get("/api/v1/search?q=test")
        # Should work without auth since no users exist
        assert response.status_code == 200

    def test_feed_accessible_without_users(self):
        """Test that feed endpoint works without users."""
        response = self.client.post("/api/v1/feed", json={"channels": []})
        assert response.status_code == 200


# =============================================================================
# Tests for admin-specific access
# =============================================================================


class TestAdminAccess:
    """Tests for admin-specific endpoint access."""

    @pytest.fixture(autouse=True)
    def setup(self, test_db_with_user, authenticated_client, admin_client):
        """Setup test fixtures."""
        self.user_client = authenticated_client
        self.admin_client = admin_client

    def test_admin_can_access_admin_endpoints(self):
        """Test that admin users can access admin endpoints."""
        # Test getting settings (admin endpoint)
        response = self.admin_client.get("/admin/settings")
        # Should succeed or return settings
        assert response.status_code in [200, 404]

    def test_regular_user_cannot_access_admin_endpoints(self):
        """Test that regular users cannot access admin endpoints."""
        response = self.user_client.get("/admin/settings")
        # Should be forbidden
        assert response.status_code in [401, 403, 404]
