"""Tests for token authentication on thumbnails and captions endpoints."""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi import HTTPException

from invidious_proxy import _validate_resource_token


class TestValidateResourceToken:
    """Tests for _validate_resource_token function."""

    @pytest.fixture(autouse=True)
    def setup_signing_secret(self, monkeypatch, tmp_path):
        """Setup a test signing secret."""
        monkeypatch.setattr("config.DATA_DIR", str(tmp_path))
        import tokens

        tokens._signing_secret = None

    def test_no_auth_required_when_no_users(self):
        """Token validation passes when no users exist (setup incomplete)."""
        with patch("database.has_any_user", return_value=False):
            result = _validate_resource_token(None, "abc123")
            assert result is None

    def test_no_auth_required_when_no_users_with_token(self):
        """Token validation passes when no users exist even with token provided."""
        with patch("database.has_any_user", return_value=False):
            result = _validate_resource_token("some_token", "abc123")
            assert result is None

    def test_401_when_users_exist_and_no_token(self):
        """Returns 401 when users exist but no token provided."""
        with patch("database.has_any_user", return_value=True):
            with pytest.raises(HTTPException) as exc_info:
                _validate_resource_token(None, "abc123")
            assert exc_info.value.status_code == 401
            assert "Missing token" in exc_info.value.detail

    def test_401_when_users_exist_and_invalid_token(self):
        """Returns 401 when users exist and token is invalid."""
        with patch("database.has_any_user", return_value=True):
            with pytest.raises(HTTPException) as exc_info:
                _validate_resource_token("invalid_token", "abc123")
            assert exc_info.value.status_code == 401

    def test_succeeds_with_valid_token(self):
        """Returns user_id when token is valid."""
        import tokens

        token = tokens.generate_stream_token(user_id=42, video_id="abc123xyz00")
        with patch("database.has_any_user", return_value=True):
            result = _validate_resource_token(token, "abc123xyz00")
            assert result == 42

    def test_401_with_wrong_video_id(self):
        """Returns 401 when token video_id doesn't match."""
        import tokens

        token = tokens.generate_stream_token(user_id=1, video_id="video1xxxxx")
        with patch("database.has_any_user", return_value=True):
            with pytest.raises(HTTPException) as exc_info:
                _validate_resource_token(token, "wrong_video")
            assert exc_info.value.status_code == 401


class TestThumbnailEndpointAuth:
    """Tests for token auth on the thumbnail proxy endpoint."""

    @pytest.fixture(autouse=True)
    def setup_signing_secret(self, monkeypatch, tmp_path):
        """Setup a test signing secret."""
        monkeypatch.setattr("config.DATA_DIR", str(tmp_path))
        import tokens

        tokens._signing_secret = None

    @pytest.fixture
    def mock_settings(self):
        """Create mock settings for Invidious proxy."""
        settings = MagicMock()
        settings.invidious_instance = "https://invidious.example.com"
        settings.invidious_enabled = True
        settings.invidious_timeout = 30
        return settings

    def test_thumbnail_401_without_token_when_users_exist(self):
        """Thumbnail endpoint returns 401 without token when users exist."""
        with patch("database.has_any_user", return_value=True):
            with pytest.raises(HTTPException) as exc_info:
                _validate_resource_token(None, "test_video")
            assert exc_info.value.status_code == 401

    def test_thumbnail_succeeds_with_valid_token(self):
        """Thumbnail endpoint succeeds with valid token."""
        import tokens

        token = tokens.generate_stream_token(user_id=1, video_id="test_video1")
        with patch("database.has_any_user", return_value=True):
            user_id = _validate_resource_token(token, "test_video1")
            assert user_id == 1

    def test_thumbnail_no_auth_when_no_users(self):
        """Thumbnail endpoint works without token when no users exist."""
        with patch("database.has_any_user", return_value=False):
            result = _validate_resource_token(None, "test_video")
            assert result is None


class TestCaptionsEndpointAuth:
    """Tests for token auth on the captions list endpoint."""

    @pytest.fixture(autouse=True)
    def setup_signing_secret(self, monkeypatch, tmp_path):
        """Setup a test signing secret."""
        monkeypatch.setattr("config.DATA_DIR", str(tmp_path))
        import tokens

        tokens._signing_secret = None

    def test_captions_401_without_token_when_users_exist(self):
        """Captions list endpoint returns 401 without token when users exist."""
        with patch("database.has_any_user", return_value=True):
            with pytest.raises(HTTPException) as exc_info:
                _validate_resource_token(None, "test_video")
            assert exc_info.value.status_code == 401

    def test_captions_succeeds_with_valid_token(self):
        """Captions list endpoint succeeds with valid token."""
        import tokens

        token = tokens.generate_stream_token(user_id=5, video_id="caption_vid1")
        with patch("database.has_any_user", return_value=True):
            user_id = _validate_resource_token(token, "caption_vid1")
            assert user_id == 5

    def test_captions_no_auth_when_no_users(self):
        """Captions list endpoint works without token when no users exist."""
        with patch("database.has_any_user", return_value=False):
            result = _validate_resource_token(None, "test_video")
            assert result is None
