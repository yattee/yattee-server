"""Tests for credentials module."""

import os
import sys
import tempfile
from unittest.mock import patch

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from credentials import (
    _build_credential_args,
    _write_temp_file,
    cleanup_temp_files,
    extract_extractor_hint,
    match_site,
)


class TestExtractExtractorHint:
    """Tests for extract_extractor_hint function."""

    def test_youtube_url(self):
        """Test YouTube URL extraction."""
        assert extract_extractor_hint("https://www.youtube.com/watch?v=abc123") == "youtube"
        assert extract_extractor_hint("https://youtu.be/abc123") == "youtube"

    def test_twitter_url(self):
        """Test Twitter/X URL extraction."""
        assert extract_extractor_hint("https://twitter.com/user/status/123") == "twitter"
        assert extract_extractor_hint("https://x.com/user/status/123") == "twitter"

    def test_tiktok_url(self):
        """Test TikTok URL extraction."""
        assert extract_extractor_hint("https://www.tiktok.com/@user/video/123") == "tiktok"

    def test_instagram_url(self):
        """Test Instagram URL extraction."""
        assert extract_extractor_hint("https://www.instagram.com/p/abc123") == "instagram"

    def test_facebook_url(self):
        """Test Facebook URL extraction."""
        assert extract_extractor_hint("https://www.facebook.com/video/123") == "facebook"
        assert extract_extractor_hint("https://fb.com/video/123") == "facebook"
        assert extract_extractor_hint("https://fb.watch/abc") == "facebook"

    def test_vimeo_url(self):
        """Test Vimeo URL extraction."""
        assert extract_extractor_hint("https://vimeo.com/123456") == "vimeo"

    def test_dailymotion_url(self):
        """Test Dailymotion URL extraction."""
        assert extract_extractor_hint("https://www.dailymotion.com/video/abc") == "dailymotion"

    def test_twitch_url(self):
        """Test Twitch URL extraction."""
        assert extract_extractor_hint("https://www.twitch.tv/streamer") == "twitch"

    def test_unknown_domain_fallback(self):
        """Test fallback for unknown domains."""
        assert extract_extractor_hint("https://www.example.com/video") == "example"
        assert extract_extractor_hint("https://newsite.org/content") == "newsite"

    def test_www_prefix_stripped(self):
        """Test that www. prefix is stripped."""
        hint1 = extract_extractor_hint("https://www.vimeo.com/123")
        hint2 = extract_extractor_hint("https://vimeo.com/123")
        assert hint1 == hint2

    def test_invalid_url_fallback(self):
        """Test that invalid URLs fall back to domain extraction."""
        # urlparse handles these gracefully - they get treated as paths
        # The function returns empty string or extracted domain parts
        hint = extract_extractor_hint("not a url")
        assert hint is not None  # Falls back to some extraction
        assert extract_extractor_hint("") == ""  # Empty string returns empty

    def test_subdomain_handling(self):
        """Test handling of subdomains."""
        assert extract_extractor_hint("https://mobile.twitter.com/user") == "twitter"
        assert extract_extractor_hint("https://m.youtube.com/watch?v=abc") == "youtube"


class TestMatchSite:
    """Tests for match_site function."""

    def test_exact_match(self):
        """Test exact match."""
        assert match_site("youtube", "youtube") is True
        assert match_site("twitter", "twitter") is True

    def test_case_insensitive(self):
        """Test case insensitive matching."""
        assert match_site("YouTube", "youtube") is True
        assert match_site("TWITTER", "Twitter") is True

    def test_partial_match_removed_for_security(self):
        """Test that partial substring matching is no longer allowed for security.

        This is intentionally NOT matching to prevent credential leakage
        where patterns like 'twitter' could match 'twitter.com.evil.com'.
        Use wildcard patterns instead.
        """
        # Substring matching without wildcards should NOT match
        assert match_site("twitter", "twitter.com") is False
        assert match_site("twitter.com", "twitter") is False

    def test_wildcard_prefix_match(self):
        """Test wildcard prefix matching (e.g., 'twitter*')."""
        assert match_site("twitterfeed", "twitter*") is True
        assert match_site("twitter.com", "twitter*") is True
        assert match_site("mytwitter", "twitter*") is False  # Doesn't start with twitter

    def test_wildcard_suffix_match(self):
        """Test wildcard suffix matching (e.g., '*twitter')."""
        assert match_site("mytwitter", "*twitter") is True
        assert match_site("twitter", "*twitter") is True
        assert match_site("twitterfeed", "*twitter") is False  # Doesn't end with twitter

    def test_wildcard_match(self):
        """Test wildcard pattern matching."""
        assert match_site("mytwitter", "*twitter*") is True
        assert match_site("twitterfeed", "*twitter*") is True

    def test_no_match(self):
        """Test non-matching patterns."""
        assert match_site("youtube", "vimeo") is False
        assert match_site("twitter", "facebook") is False


class TestDomainMatchingSecurity:
    """Security tests for domain matching to prevent credential leakage."""

    def test_malicious_domain_does_not_match(self):
        """Test that twitter.com.evil.com does NOT match twitter.com credentials."""
        # extract_extractor_hint should return None or a different hint for malicious domains
        hint = extract_extractor_hint("https://twitter.com.evil.com/video")
        assert hint != "twitter"

    def test_subdomain_matches(self):
        """Test that legitimate subdomains still match."""
        assert extract_extractor_hint("https://mobile.twitter.com/video") == "twitter"
        assert extract_extractor_hint("https://m.youtube.com/watch") == "youtube"

    def test_exact_domain_matches(self):
        """Test that exact domains match."""
        assert extract_extractor_hint("https://twitter.com/video") == "twitter"
        assert extract_extractor_hint("https://youtube.com/watch") == "youtube"

    def test_www_prefix_matches(self):
        """Test that www prefix still matches."""
        assert extract_extractor_hint("https://www.twitter.com/video") == "twitter"
        assert extract_extractor_hint("https://www.youtube.com/watch") == "youtube"


class TestBuildCredentialArgs:
    """Tests for _build_credential_args function."""

    def test_cookies_file(self):
        """Test cookies_file credential type."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("config.DATA_DIR", tmpdir):
                args, temp_files = _build_credential_args("cookies_file", None, "cookie content")
                assert "--cookies" in args
                assert len(temp_files) == 1
                assert os.path.exists(temp_files[0])
                # Clean up
                cleanup_temp_files(temp_files)

    def test_cookies_browser(self):
        """Test cookies_browser credential type."""
        args, temp_files = _build_credential_args("cookies_browser", "chrome", "")
        assert args == ["--cookies-from-browser", "chrome"]
        assert temp_files == []

    def test_cookies_browser_with_profile(self):
        """Test cookies_browser with profile."""
        args, temp_files = _build_credential_args("cookies_browser", "firefox:Profile 1", "")
        assert args == ["--cookies-from-browser", "firefox:Profile 1"]

    def test_login_credentials(self):
        """Test login credential type."""
        args, temp_files = _build_credential_args("login", "myuser", "mypass")
        assert "--username" in args
        assert "--password" in args
        assert args[args.index("--username") + 1] == "myuser"
        assert args[args.index("--password") + 1] == "mypass"

    def test_username_only(self):
        """Test username credential type."""
        args, temp_files = _build_credential_args("username", None, "myuser")
        assert args == ["--username", "myuser"]

    def test_password_only(self):
        """Test password credential type."""
        args, temp_files = _build_credential_args("password", None, "mypass")
        assert args == ["--password", "mypass"]

    def test_video_password(self):
        """Test video_password credential type."""
        args, temp_files = _build_credential_args("video_password", None, "vidpass")
        assert args == ["--video-password", "vidpass"]

    def test_header(self):
        """Test header credential type."""
        args, temp_files = _build_credential_args("header", "Authorization", "Bearer token123")
        assert args == ["--add-header", "Authorization:Bearer token123"]

    def test_netrc(self):
        """Test netrc credential type."""
        args, temp_files = _build_credential_args("netrc", None, "")
        assert args == ["--netrc"]

    def test_netrc_location(self):
        """Test netrc_location credential type."""
        args, temp_files = _build_credential_args("netrc_location", None, "/path/to/.netrc")
        assert args == ["--netrc-location", "/path/to/.netrc"]

    def test_ap_mso(self):
        """Test ap_mso credential type."""
        args, temp_files = _build_credential_args("ap_mso", None, "Comcast")
        assert args == ["--ap-mso", "Comcast"]

    def test_ap_username(self):
        """Test ap_username credential type."""
        args, temp_files = _build_credential_args("ap_username", None, "user@provider.com")
        assert args == ["--ap-username", "user@provider.com"]

    def test_ap_password(self):
        """Test ap_password credential type."""
        args, temp_files = _build_credential_args("ap_password", None, "secret")
        assert args == ["--ap-password", "secret"]

    def test_unknown_type_returns_empty(self):
        """Test that unknown credential type returns empty."""
        args, temp_files = _build_credential_args("unknown_type", None, "value")
        assert args == []
        assert temp_files == []


class TestWriteTempFile:
    """Tests for _write_temp_file function."""

    def test_creates_file(self):
        """Test that temp file is created."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("config.DATA_DIR", tmpdir):
                path = _write_temp_file("test content")
                assert os.path.exists(path)
                os.unlink(path)

    def test_file_content(self):
        """Test that file contains correct content."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("config.DATA_DIR", tmpdir):
                content = "test content with unicode: 日本語"
                path = _write_temp_file(content)
                with open(path, "r", encoding="utf-8") as f:
                    assert f.read() == content
                os.unlink(path)

    def test_file_suffix(self):
        """Test that file suffix is applied."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("config.DATA_DIR", tmpdir):
                path = _write_temp_file("content", suffix=".txt")
                assert path.endswith(".txt")
                os.unlink(path)


class TestCleanupTempFiles:
    """Tests for cleanup_temp_files function."""

    def test_removes_files(self):
        """Test that files are removed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create temp files
            paths = []
            for i in range(3):
                path = os.path.join(tmpdir, f"temp{i}.txt")
                with open(path, "w") as f:
                    f.write("test")
                paths.append(path)

            # All files exist
            assert all(os.path.exists(p) for p in paths)

            # Clean up
            cleanup_temp_files(paths)

            # All files removed
            assert all(not os.path.exists(p) for p in paths)

    def test_handles_nonexistent_files(self):
        """Test that non-existent files are handled gracefully."""
        # Should not raise
        cleanup_temp_files(["/nonexistent/path/file.txt"])

    def test_handles_empty_list(self):
        """Test that empty list is handled."""
        # Should not raise
        cleanup_temp_files([])
