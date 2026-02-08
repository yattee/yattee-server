"""Tests for tokens.py - streaming token generation and validation."""

import os
import sys

import pytest

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from tokens import add_token_to_url, generate_stream_token, validate_stream_token

# =============================================================================
# Tests for generate_stream_token
# =============================================================================


class TestGenerateStreamToken:
    """Tests for generate_stream_token function."""

    @pytest.fixture(autouse=True)
    def setup_signing_secret(self, monkeypatch, tmp_path):
        """Setup a test signing secret."""
        monkeypatch.setattr("config.DATA_DIR", str(tmp_path))
        import tokens

        tokens._signing_secret = None

    def test_returns_string(self):
        """Test that generate_stream_token returns a string."""
        token = generate_stream_token(user_id=1, video_id="abc123xyz00")
        assert isinstance(token, str)

    def test_returns_base64_url_safe(self):
        """Test that token is URL-safe base64."""
        token = generate_stream_token(user_id=1, video_id="abc123xyz00")
        # URL-safe base64 should not contain + or /
        assert "+" not in token
        assert "/" not in token

    def test_different_users_different_tokens(self):
        """Test that different users get different tokens."""
        token1 = generate_stream_token(user_id=1, video_id="abc123xyz00")
        token2 = generate_stream_token(user_id=2, video_id="abc123xyz00")
        assert token1 != token2

    def test_different_videos_different_tokens(self):
        """Test that different videos get different tokens."""
        token1 = generate_stream_token(user_id=1, video_id="video1xxxxx")
        token2 = generate_stream_token(user_id=1, video_id="video2xxxxx")
        assert token1 != token2

    def test_custom_expiry(self):
        """Test token with custom expiry."""
        token = generate_stream_token(user_id=1, video_id="abc123xyz00", expiry_seconds=60)
        assert isinstance(token, str)


# =============================================================================
# Tests for validate_stream_token
# =============================================================================


class TestValidateStreamToken:
    """Tests for validate_stream_token function."""

    @pytest.fixture(autouse=True)
    def setup_signing_secret(self, monkeypatch, tmp_path):
        """Setup a test signing secret."""
        monkeypatch.setattr("config.DATA_DIR", str(tmp_path))
        import tokens

        tokens._signing_secret = None

    def test_valid_token(self):
        """Test validation of a valid token."""
        token = generate_stream_token(user_id=1, video_id="abc123xyz00")
        is_valid, user_id, error = validate_stream_token(token)
        assert is_valid is True
        assert user_id == 1
        assert error is None

    def test_valid_token_with_video_id_match(self):
        """Test validation with matching video ID."""
        token = generate_stream_token(user_id=1, video_id="abc123xyz00")
        is_valid, user_id, error = validate_stream_token(token, video_id="abc123xyz00")
        assert is_valid is True
        assert user_id == 1

    def test_video_id_mismatch(self):
        """Test validation fails with wrong video ID."""
        token = generate_stream_token(user_id=1, video_id="abc123xyz00")
        is_valid, user_id, error = validate_stream_token(token, video_id="different_id")
        assert is_valid is False
        assert user_id is None
        assert "mismatch" in error.lower()

    def test_empty_token(self):
        """Test validation of empty token."""
        is_valid, user_id, error = validate_stream_token("")
        assert is_valid is False
        assert user_id is None
        assert "missing" in error.lower()

    def test_none_token(self):
        """Test validation of None token."""
        is_valid, user_id, error = validate_stream_token(None)
        assert is_valid is False
        assert user_id is None

    def test_invalid_base64(self):
        """Test validation of invalid base64 token."""
        is_valid, user_id, error = validate_stream_token("not_valid_base64!!!")
        assert is_valid is False
        assert user_id is None

    def test_tampered_token(self):
        """Test validation of tampered token."""
        token = generate_stream_token(user_id=1, video_id="abc123xyz00")
        # Tamper with the token
        tampered = token[:-5] + "XXXXX"
        is_valid, user_id, error = validate_stream_token(tampered)
        assert is_valid is False
        assert user_id is None

    def test_expired_token(self):
        """Test validation of expired token."""
        from datetime import datetime, timedelta

        from freezegun import freeze_time

        # Create token with 1 second expiry
        token = generate_stream_token(user_id=1, video_id="abc123xyz00", expiry_seconds=1)

        # Fast forward time
        with freeze_time(datetime.now() + timedelta(seconds=5)):
            is_valid, user_id, error = validate_stream_token(token)
            assert is_valid is False
            assert user_id is None
            assert "expired" in error.lower()

    def test_wrong_signature(self):
        """Test validation fails with wrong signing key."""
        token = generate_stream_token(user_id=1, video_id="abc123xyz00")

        # Change the secret key
        import tokens

        old_secret = tokens._signing_secret
        tokens._signing_secret = "different_secret_key"

        try:
            is_valid, user_id, error = validate_stream_token(token)
            assert is_valid is False
            assert "signature" in error.lower() or "failed" in error.lower()
        finally:
            tokens._signing_secret = old_secret

    def test_returns_correct_user_id(self):
        """Test that validation returns the correct user ID."""
        token = generate_stream_token(user_id=42, video_id="abc123xyz00")
        is_valid, user_id, error = validate_stream_token(token)
        assert is_valid is True
        assert user_id == 42


# =============================================================================
# Tests for add_token_to_url
# =============================================================================


class TestAddTokenToUrl:
    """Tests for add_token_to_url function."""

    def test_url_without_query_params(self):
        """Test adding token to URL without existing query parameters."""
        url = "https://example.com/video"
        result = add_token_to_url(url, "mytoken123")
        assert result == "https://example.com/video?token=mytoken123"

    def test_url_with_query_params(self):
        """Test adding token to URL with existing query parameters."""
        url = "https://example.com/video?id=123"
        result = add_token_to_url(url, "mytoken123")
        assert result == "https://example.com/video?id=123&token=mytoken123"

    def test_url_with_multiple_query_params(self):
        """Test adding token to URL with multiple query parameters."""
        url = "https://example.com/video?id=123&quality=hd"
        result = add_token_to_url(url, "mytoken123")
        assert result == "https://example.com/video?id=123&quality=hd&token=mytoken123"

    def test_preserves_original_url(self):
        """Test that original URL is preserved."""
        url = "https://example.com/path/to/video.mp4"
        result = add_token_to_url(url, "tok")
        assert result.startswith("https://example.com/path/to/video.mp4")

    def test_empty_token(self):
        """Test adding empty token."""
        url = "https://example.com/video"
        result = add_token_to_url(url, "")
        assert result == "https://example.com/video?token="

    def test_token_with_special_chars(self):
        """Test adding token with URL-safe base64 characters."""
        url = "https://example.com/video"
        token = "abc123-_xyz"
        result = add_token_to_url(url, token)
        assert result == f"https://example.com/video?token={token}"


# =============================================================================
# Integration tests - generate and validate round trip
# =============================================================================


class TestTokenRoundTrip:
    """Integration tests for token generation and validation."""

    @pytest.fixture(autouse=True)
    def setup_signing_secret(self, monkeypatch, tmp_path):
        """Setup a test signing secret."""
        monkeypatch.setattr("config.DATA_DIR", str(tmp_path))
        import tokens

        tokens._signing_secret = None

    def test_round_trip_basic(self):
        """Test generating and validating a token."""
        user_id = 123
        video_id = "dQw4w9WgXcQ"

        token = generate_stream_token(user_id=user_id, video_id=video_id)
        is_valid, returned_user_id, error = validate_stream_token(token, video_id=video_id)

        assert is_valid is True
        assert returned_user_id == user_id
        assert error is None

    def test_round_trip_multiple_videos(self):
        """Test tokens for multiple videos."""
        user_id = 1

        videos = ["video1abcde", "video2fghij", "video3klmno"]
        tokens = {vid: generate_stream_token(user_id=user_id, video_id=vid) for vid in videos}

        # Each token should only be valid for its video
        for vid, token in tokens.items():
            is_valid, _, _ = validate_stream_token(token, video_id=vid)
            assert is_valid is True

            # Should fail for other videos
            for other_vid in videos:
                if other_vid != vid:
                    is_valid, _, _ = validate_stream_token(token, video_id=other_vid)
                    assert is_valid is False
