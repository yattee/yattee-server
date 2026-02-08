"""Tests for basic_auth.py - HTTP Basic Authentication utilities."""

import os
import sys
import time

import pytest

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from basic_auth import (
    MINIMAL_INFO_PATHS,
    PUBLIC_PATHS,
    _cleanup_old_attempts,
    _is_minimal_info_path,
    _is_public_path,
    _is_rate_limited,
    _record_failed_attempt,
    parse_basic_auth,
)

# =============================================================================
# Tests for parse_basic_auth
# =============================================================================


class TestParseBasicAuth:
    """Tests for parse_basic_auth function."""

    def test_valid_basic_auth(self):
        """Test parsing valid Basic Auth header."""
        import base64

        credentials = base64.b64encode(b"username:password").decode()
        result = parse_basic_auth(f"Basic {credentials}")
        assert result == ("username", "password")

    def test_valid_with_colon_in_password(self):
        """Test password containing colons."""
        import base64

        credentials = base64.b64encode(b"user:pass:word:with:colons").decode()
        result = parse_basic_auth(f"Basic {credentials}")
        assert result == ("user", "pass:word:with:colons")

    def test_empty_password(self):
        """Test empty password."""
        import base64

        credentials = base64.b64encode(b"username:").decode()
        result = parse_basic_auth(f"Basic {credentials}")
        assert result == ("username", "")

    def test_empty_username(self):
        """Test empty username."""
        import base64

        credentials = base64.b64encode(b":password").decode()
        result = parse_basic_auth(f"Basic {credentials}")
        assert result == ("", "password")

    def test_empty_header(self):
        """Test empty authorization header."""
        result = parse_basic_auth("")
        assert result is None

    def test_none_header(self):
        """Test None authorization header."""
        result = parse_basic_auth(None)
        assert result is None

    def test_missing_basic_prefix(self):
        """Test missing 'Basic' prefix."""
        import base64

        credentials = base64.b64encode(b"user:pass").decode()
        result = parse_basic_auth(credentials)
        assert result is None

    def test_wrong_auth_type(self):
        """Test wrong authentication type."""
        import base64

        credentials = base64.b64encode(b"user:pass").decode()
        result = parse_basic_auth(f"Bearer {credentials}")
        assert result is None

    def test_invalid_base64(self):
        """Test invalid base64 encoding."""
        result = parse_basic_auth("Basic not_valid_base64!!!")
        assert result is None

    def test_no_colon_in_credentials(self):
        """Test credentials without colon separator."""
        import base64

        credentials = base64.b64encode(b"usernamepassword").decode()
        result = parse_basic_auth(f"Basic {credentials}")
        assert result is None

    def test_case_insensitive_basic(self):
        """Test that 'Basic' is case-insensitive."""
        import base64

        credentials = base64.b64encode(b"user:pass").decode()
        result = parse_basic_auth(f"basic {credentials}")
        assert result == ("user", "pass")

    def test_unicode_credentials(self):
        """Test unicode username and password."""
        import base64

        credentials = base64.b64encode("用户:密码".encode("utf-8")).decode()
        result = parse_basic_auth(f"Basic {credentials}")
        assert result == ("用户", "密码")


# =============================================================================
# Tests for _is_public_path
# =============================================================================


class TestIsPublicPath:
    """Tests for _is_public_path function."""

    def test_health_endpoint(self):
        """Test /health is public."""
        assert _is_public_path("/health") is True

    def test_setup_endpoint(self):
        """Test /setup is public."""
        assert _is_public_path("/setup") is True

    def test_setup_status(self):
        """Test /setup/status is public."""
        assert _is_public_path("/setup/status") is True

    def test_static_files(self):
        """Test /static/* paths are public."""
        assert _is_public_path("/static/") is True
        assert _is_public_path("/static/css/style.css") is True
        assert _is_public_path("/static/js/app.js") is True

    def test_favicon(self):
        """Test /favicon.ico is public."""
        assert _is_public_path("/favicon.ico") is True

    def test_proxy_endpoint(self):
        """Test /proxy/* paths are public (they validate tokens internally)."""
        assert _is_public_path("/proxy/") is True
        assert _is_public_path("/proxy/fast/abc123") is True

    def test_thumbnails_endpoint(self):
        """Test /api/v1/thumbnails/* bypasses basic auth (validates tokens at endpoint level)."""
        assert _is_public_path("/api/v1/thumbnails/") is True
        assert _is_public_path("/api/v1/thumbnails/abc123/maxres.jpg") is True

    def test_captions_endpoint(self):
        """Test /api/v1/captions/* bypasses basic auth (validates tokens at endpoint level)."""
        assert _is_public_path("/api/v1/captions/") is True
        assert _is_public_path("/api/v1/captions/abc123") is True
        assert _is_public_path("/api/v1/captions/abc123/content?lang=en") is True

    def test_api_endpoints_not_public(self):
        """Test regular API endpoints are not public."""
        assert _is_public_path("/api/v1/videos/abc123") is False
        assert _is_public_path("/api/v1/search") is False
        assert _is_public_path("/api/v1/channels/UC123") is False

    def test_admin_not_public(self):
        """Test /admin is not public."""
        assert _is_public_path("/admin") is False
        assert _is_public_path("/admin/settings") is False

    def test_root_not_public(self):
        """Test root path is not public."""
        assert _is_public_path("/") is False


# =============================================================================
# Tests for _is_minimal_info_path
# =============================================================================


class TestIsMinimalInfoPath:
    """Tests for _is_minimal_info_path function."""

    def test_info_endpoint(self):
        """Test /info is a minimal info path."""
        assert _is_minimal_info_path("/info") is True

    def test_other_paths_not_minimal(self):
        """Test other paths are not minimal info paths."""
        assert _is_minimal_info_path("/health") is False
        assert _is_minimal_info_path("/api/v1/videos") is False
        assert _is_minimal_info_path("/admin") is False

    def test_info_subpath_not_minimal(self):
        """Test /info subpaths are not minimal info paths."""
        assert _is_minimal_info_path("/info/details") is False


# =============================================================================
# Tests for rate limiting functions
# =============================================================================


class TestRateLimiting:
    """Tests for rate limiting functions."""

    @pytest.fixture(autouse=True)
    def reset_failed_attempts(self):
        """Reset failed attempts before each test."""
        import basic_auth

        basic_auth._failed_attempts.clear()
        yield
        basic_auth._failed_attempts.clear()

    def test_record_failed_attempt(self):
        """Test recording a failed attempt."""
        import basic_auth

        _record_failed_attempt("192.168.1.1")
        assert "192.168.1.1" in basic_auth._failed_attempts
        assert len(basic_auth._failed_attempts["192.168.1.1"]) == 1

    def test_multiple_failed_attempts(self):
        """Test recording multiple failed attempts."""
        import basic_auth

        for _ in range(3):
            _record_failed_attempt("192.168.1.1")
        assert len(basic_auth._failed_attempts["192.168.1.1"]) == 3

    def test_is_rate_limited_below_threshold(self):
        """Test that IP is not rate limited below threshold."""
        for _ in range(4):  # Below the limit of 5
            _record_failed_attempt("192.168.1.1")
        assert _is_rate_limited("192.168.1.1") is False

    def test_is_rate_limited_at_threshold(self):
        """Test that IP is rate limited at threshold."""
        for _ in range(5):  # At the limit
            _record_failed_attempt("192.168.1.1")
        assert _is_rate_limited("192.168.1.1") is True

    def test_is_rate_limited_above_threshold(self):
        """Test that IP is rate limited above threshold."""
        for _ in range(10):  # Well above the limit
            _record_failed_attempt("192.168.1.1")
        assert _is_rate_limited("192.168.1.1") is True

    def test_is_rate_limited_unknown_ip(self):
        """Test that unknown IP is not rate limited."""
        assert _is_rate_limited("10.0.0.1") is False

    def test_cleanup_old_attempts(self):
        """Test that old attempts are cleaned up."""
        import basic_auth

        # Record some attempts
        _record_failed_attempt("192.168.1.1")

        # Manually set the timestamp to old
        basic_auth._failed_attempts["192.168.1.1"] = [time.time() - 120]  # 2 minutes ago

        # Cleanup should remove old attempts
        _cleanup_old_attempts("192.168.1.1")
        assert "192.168.1.1" not in basic_auth._failed_attempts

    def test_cleanup_removes_only_old(self):
        """Test that cleanup only removes old attempts."""
        import basic_auth

        # Add one old and one recent attempt
        old_time = time.time() - 120  # 2 minutes ago
        recent_time = time.time() - 10  # 10 seconds ago
        basic_auth._failed_attempts["192.168.1.1"] = [old_time, recent_time]

        _cleanup_old_attempts("192.168.1.1")
        assert len(basic_auth._failed_attempts["192.168.1.1"]) == 1

    def test_different_ips_independent(self):
        """Test that rate limiting is per-IP."""
        for _ in range(5):
            _record_failed_attempt("192.168.1.1")

        assert _is_rate_limited("192.168.1.1") is True
        assert _is_rate_limited("192.168.1.2") is False


# =============================================================================
# Tests for PUBLIC_PATHS and MINIMAL_INFO_PATHS constants
# =============================================================================


class TestPathConstants:
    """Tests for path constant lists."""

    def test_public_paths_contains_health(self):
        """Test PUBLIC_PATHS contains expected paths."""
        assert "/health" in PUBLIC_PATHS

    def test_public_paths_contains_setup(self):
        """Test PUBLIC_PATHS contains setup paths."""
        assert "/setup" in PUBLIC_PATHS

    def test_public_paths_contains_static(self):
        """Test PUBLIC_PATHS contains static path."""
        assert "/static/" in PUBLIC_PATHS

    def test_minimal_info_paths_contains_info(self):
        """Test MINIMAL_INFO_PATHS contains /info."""
        assert "/info" in MINIMAL_INFO_PATHS
