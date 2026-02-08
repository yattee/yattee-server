"""Security tests for Yattee Server.

Tests for:
- RCE prevention (command injection via URLs starting with '-')
- SSRF prevention (blocking requests to private/internal networks)
- Path traversal prevention (sanitizing format_id and ext)
"""

import pytest

# =============================================================================
# Test is_valid_url (RCE Prevention)
# =============================================================================


class TestIsValidUrl:
    """Tests for is_valid_url function (RCE prevention)."""

    def test_valid_http_url(self):
        """Valid HTTP URLs should pass."""
        from ytdlp_wrapper import is_valid_url

        assert is_valid_url("http://example.com/video")
        assert is_valid_url("http://youtube.com/watch?v=abc123")

    def test_valid_https_url(self):
        """Valid HTTPS URLs should pass."""
        from ytdlp_wrapper import is_valid_url

        assert is_valid_url("https://example.com/video")
        assert is_valid_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        assert is_valid_url("https://vimeo.com/12345")

    def test_reject_url_starting_with_dash(self):
        """URLs starting with '-' should be rejected (command injection)."""
        from ytdlp_wrapper import is_valid_url

        # These could be interpreted as yt-dlp flags
        assert not is_valid_url("--exec whoami")
        assert not is_valid_url("-o /etc/passwd")
        assert not is_valid_url("--output /tmp/test")
        assert not is_valid_url("-f bestvideo")

    def test_reject_invalid_schemes(self):
        """Non-HTTP/HTTPS schemes should be rejected."""
        from ytdlp_wrapper import is_valid_url

        assert not is_valid_url("file:///etc/passwd")
        assert not is_valid_url("ftp://example.com/file")
        assert not is_valid_url("javascript:alert(1)")
        assert not is_valid_url("data:text/html,<script>alert(1)</script>")

    def test_reject_missing_host(self):
        """URLs without a host should be rejected."""
        from ytdlp_wrapper import is_valid_url

        assert not is_valid_url("http://")
        assert not is_valid_url("https://")
        assert not is_valid_url("http:///path")

    def test_reject_empty_and_invalid(self):
        """Empty strings and invalid URLs should be rejected."""
        from ytdlp_wrapper import is_valid_url

        assert not is_valid_url("")
        assert not is_valid_url("not a url")
        assert not is_valid_url("just some text")


# =============================================================================
# Test is_safe_url (SSRF Prevention)
# =============================================================================


class TestIsSafeUrl:
    """Tests for is_safe_url function (SSRF prevention)."""

    def test_safe_public_url(self, mock_dns_public):
        """Public URLs should be allowed when they resolve to public IPs."""
        from ytdlp_wrapper import is_safe_url

        assert is_safe_url("https://www.youtube.com/watch?v=abc123")
        assert is_safe_url("https://vimeo.com/12345")
        assert is_safe_url("https://example.com/video")

    def test_block_localhost(self):
        """Localhost should be blocked."""
        from ytdlp_wrapper import is_safe_url

        assert not is_safe_url("http://localhost/admin")
        assert not is_safe_url("http://localhost:8080/api")
        assert not is_safe_url("https://localhost/secret")

    def test_block_loopback_ip(self):
        """Loopback IPs should be blocked."""
        from ytdlp_wrapper import is_safe_url

        assert not is_safe_url("http://127.0.0.1/admin")
        assert not is_safe_url("http://127.0.0.1:8080/api")
        assert not is_safe_url("http://127.0.1.1/secret")

    def test_block_private_ip_10_range(self):
        """10.0.0.0/8 private range should be blocked."""
        from ytdlp_wrapper import is_safe_url

        assert not is_safe_url("http://10.0.0.1/internal")
        assert not is_safe_url("http://10.255.255.255/internal")
        assert not is_safe_url("http://10.1.2.3:8080/api")

    def test_block_private_ip_172_range(self):
        """172.16.0.0/12 private range should be blocked."""
        from ytdlp_wrapper import is_safe_url

        assert not is_safe_url("http://172.16.0.1/internal")
        assert not is_safe_url("http://172.31.255.255/internal")
        assert not is_safe_url("http://172.20.1.1:8080/api")

    def test_block_private_ip_192_range(self):
        """192.168.0.0/16 private range should be blocked."""
        from ytdlp_wrapper import is_safe_url

        assert not is_safe_url("http://192.168.0.1/internal")
        assert not is_safe_url("http://192.168.1.1/admin")
        assert not is_safe_url("http://192.168.255.255:8080/api")

    def test_block_aws_metadata(self):
        """AWS/cloud metadata IP should be blocked."""
        from ytdlp_wrapper import is_safe_url

        assert not is_safe_url("http://169.254.169.254/latest/meta-data/")
        assert not is_safe_url("http://169.254.169.254/latest/api/token")

    def test_block_google_metadata(self):
        """Google Cloud metadata hostname should be blocked."""
        from ytdlp_wrapper import is_safe_url

        assert not is_safe_url("http://metadata.google.internal/computeMetadata/v1/")
        assert not is_safe_url("http://metadata/computeMetadata/v1/")

    def test_allow_domain_names(self, mock_dns_public):
        """Domain names resolving to public IPs should be allowed."""
        from ytdlp_wrapper import is_safe_url

        # Domain names are allowed when they resolve to public IPs
        # (DNS is now resolved to prevent rebinding attacks)
        assert is_safe_url("https://this-domain-does-not-exist-xyz123.com/video")
        assert is_safe_url("https://example.com/video")


# =============================================================================
# Test sanitize_format_id (Path Traversal Prevention)
# =============================================================================


class TestSanitizeFormatId:
    """Tests for sanitize_format_id function (path traversal prevention)."""

    def test_valid_format_ids(self):
        """Valid format IDs should pass through unchanged."""
        from ytdlp_wrapper import sanitize_format_id

        assert sanitize_format_id("137") == "137"
        assert sanitize_format_id("140") == "140"
        assert sanitize_format_id("251-drc") == "251-drc"
        assert sanitize_format_id("mp4_hd") == "mp4_hd"
        assert sanitize_format_id("video.mp4") == "video.mp4"

    def test_reject_path_traversal(self):
        """Path traversal sequences should be rejected."""
        from ytdlp_wrapper import sanitize_format_id

        with pytest.raises(ValueError, match="Invalid format ID"):
            sanitize_format_id("../../../etc/passwd")

        with pytest.raises(ValueError, match="Invalid format ID"):
            sanitize_format_id("..\\..\\etc\\passwd")

        with pytest.raises(ValueError, match="Invalid format ID"):
            sanitize_format_id("../../etc/cron.d/pwned")

    def test_reject_absolute_paths(self):
        """Absolute paths should be rejected."""
        from ytdlp_wrapper import sanitize_format_id

        with pytest.raises(ValueError, match="Invalid format ID"):
            sanitize_format_id("/etc/passwd")

        with pytest.raises(ValueError, match="Invalid format ID"):
            sanitize_format_id("\\windows\\system32")

    def test_reject_special_characters(self):
        """Special characters not allowed in format IDs should be rejected."""
        from ytdlp_wrapper import sanitize_format_id

        with pytest.raises(ValueError, match="Invalid format ID"):
            sanitize_format_id("format;rm -rf /")

        with pytest.raises(ValueError, match="Invalid format ID"):
            sanitize_format_id("format|cat /etc/passwd")

        with pytest.raises(ValueError, match="Invalid format ID"):
            sanitize_format_id("format`whoami`")

    def test_reject_empty(self):
        """Empty format IDs should be rejected."""
        from ytdlp_wrapper import sanitize_format_id

        with pytest.raises(ValueError, match="cannot be empty"):
            sanitize_format_id("")


# =============================================================================
# Test sanitize_extension (Path Traversal Prevention)
# =============================================================================


class TestSanitizeExtension:
    """Tests for sanitize_extension function (path traversal prevention)."""

    def test_valid_extensions(self):
        """Valid extensions should pass through."""
        from ytdlp_wrapper import sanitize_extension

        assert sanitize_extension("mp4") == "mp4"
        assert sanitize_extension("webm") == "webm"
        assert sanitize_extension("m4a") == "m4a"
        assert sanitize_extension("opus") == "opus"
        assert sanitize_extension("mkv") == "mkv"

    def test_strip_leading_dot(self):
        """Leading dots should be stripped."""
        from ytdlp_wrapper import sanitize_extension

        assert sanitize_extension(".mp4") == "mp4"
        assert sanitize_extension(".webm") == "webm"

    def test_default_for_empty(self):
        """Empty extensions should return default 'mp4'."""
        from ytdlp_wrapper import sanitize_extension

        assert sanitize_extension("") == "mp4"
        assert sanitize_extension(None) == "mp4"

    def test_reject_long_extensions(self):
        """Extensions longer than 10 chars should be rejected."""
        from ytdlp_wrapper import sanitize_extension

        with pytest.raises(ValueError, match="Invalid extension"):
            sanitize_extension("verylongextension")

    def test_reject_special_characters(self):
        """Extensions with special characters should be rejected."""
        from ytdlp_wrapper import sanitize_extension

        with pytest.raises(ValueError, match="Invalid extension"):
            sanitize_extension("../mp4")

        with pytest.raises(ValueError, match="Invalid extension"):
            sanitize_extension("mp4;")

        with pytest.raises(ValueError, match="Invalid extension"):
            sanitize_extension("mp4|cat")


# =============================================================================
# Test _separate_flags_and_urls (RCE Prevention)
# =============================================================================


class TestSeparateFlagsAndUrls:
    """Tests for _separate_flags_and_urls function (RCE prevention)."""

    def test_separates_flags_and_urls(self):
        """Should correctly separate flags from URLs."""
        from ytdlp_wrapper import _separate_flags_and_urls

        args = ("-j", "--no-download", "https://youtube.com/watch?v=abc123")
        flags, urls = _separate_flags_and_urls(args)

        assert flags == ["-j", "--no-download"]
        assert urls == ["https://youtube.com/watch?v=abc123"]

    def test_multiple_urls(self):
        """Should handle multiple URLs."""
        from ytdlp_wrapper import _separate_flags_and_urls

        args = ("-j", "https://url1.com", "https://url2.com")
        flags, urls = _separate_flags_and_urls(args)

        assert flags == ["-j"]
        assert urls == ["https://url1.com", "https://url2.com"]

    def test_no_urls(self):
        """Should handle cases with no URLs."""
        from ytdlp_wrapper import _separate_flags_and_urls

        args = ("-j", "--no-download", "--version")
        flags, urls = _separate_flags_and_urls(args)

        assert flags == ["-j", "--no-download", "--version"]
        assert urls == []


# =============================================================================
# Integration Tests - API Endpoint Security
# =============================================================================


class TestExtractEndpointSecurity:
    """Integration tests for /extract endpoint security."""

    def test_extract_rejects_command_injection(self, test_client):
        """Extract endpoint should reject URLs starting with '-'."""
        response = test_client.get("/api/v1/extract", params={"url": "--exec whoami"})
        assert response.status_code == 400
        assert "Invalid URL" in response.json()["detail"]

    def test_extract_rejects_private_ip(self, test_client):
        """Extract endpoint should reject private IPs (SSRF)."""
        response = test_client.get("/api/v1/extract", params={"url": "http://192.168.1.1/admin"})
        assert response.status_code == 403
        assert "restricted network" in response.json()["detail"]

    def test_extract_rejects_localhost(self, test_client):
        """Extract endpoint should reject localhost (SSRF)."""
        response = test_client.get("/api/v1/extract", params={"url": "http://localhost:8080/api"})
        assert response.status_code == 403
        assert "restricted network" in response.json()["detail"]

    def test_extract_rejects_aws_metadata(self, test_client):
        """Extract endpoint should reject AWS metadata (SSRF)."""
        response = test_client.get("/api/v1/extract", params={"url": "http://169.254.169.254/latest/meta-data/"})
        assert response.status_code == 403
        assert "restricted network" in response.json()["detail"]


class TestExtractChannelEndpointSecurity:
    """Integration tests for /extract/channel endpoint security."""

    def test_extract_channel_rejects_command_injection(self, test_client):
        """Extract channel endpoint should reject URLs starting with '-'."""
        response = test_client.get("/api/v1/extract/channel", params={"url": "-o /tmp/pwned"})
        assert response.status_code == 400
        assert "Invalid URL" in response.json()["detail"]

    def test_extract_channel_rejects_private_ip(self, test_client):
        """Extract channel endpoint should reject private IPs (SSRF)."""
        response = test_client.get("/api/v1/extract/channel", params={"url": "http://10.0.0.1/internal"})
        assert response.status_code == 403
        assert "restricted network" in response.json()["detail"]


class TestFastDownloadEndpointSecurity:
    """Integration tests for /proxy/fast endpoint security."""

    def test_fast_download_rejects_private_ip(self, test_client):
        """Fast download endpoint should reject private IPs when url param provided."""
        response = test_client.get(
            "/proxy/fast/test_video_id",
            params={"url": "http://192.168.1.1/video.mp4", "itag": "137"}
        )
        assert response.status_code == 403
        assert "restricted network" in response.json()["detail"]

    def test_fast_download_rejects_localhost(self, test_client):
        """Fast download endpoint should reject localhost when url param provided."""
        response = test_client.get(
            "/proxy/fast/test_video_id",
            params={"url": "http://localhost/video.mp4", "itag": "137"}
        )
        assert response.status_code == 403
        assert "restricted network" in response.json()["detail"]


class TestUrlValidation:
    """Tests for URL validation functions used in endpoints."""

    def test_valid_urls_accepted(self):
        """Valid channel URLs should pass is_valid_url check."""
        from ytdlp_wrapper import is_valid_url

        # Test that valid channel URLs pass validation
        assert is_valid_url("https://example.com/channel/test")
        assert is_valid_url("https://www.youtube.com/channel/UCtest")
        assert is_valid_url("http://vimeo.com/username")


class TestAdminSiteTestEndpointSecurity:
    """Integration tests for admin site test endpoint security."""

    def test_site_test_rejects_private_ip(self, admin_client):
        """Admin site test endpoint should reject private IPs."""
        # First create a site to test against
        site_response = admin_client.post(
            "/api/sites",
            json={
                "name": "Test Site",
                "extractor_pattern": "test",
                "enabled": True,
                "priority": 0,
                "proxy_streaming": True
            }
        )

        if site_response.status_code == 200:
            site_id = site_response.json()["id"]

            # Now test with private IP
            response = admin_client.post(
                f"/api/sites/{site_id}/test",
                json={"url": "http://192.168.1.1/video"}
            )
            assert response.status_code == 403
            assert "restricted network" in response.json()["detail"]

    def test_site_test_rejects_localhost(self, admin_client):
        """Admin site test endpoint should reject localhost."""
        # First create a site to test against
        site_response = admin_client.post(
            "/api/sites",
            json={
                "name": "Test Site 2",
                "extractor_pattern": "test2",
                "enabled": True,
                "priority": 0,
                "proxy_streaming": True
            }
        )

        if site_response.status_code == 200:
            site_id = site_response.json()["id"]

            # Now test with localhost
            response = admin_client.post(
                f"/api/sites/{site_id}/test",
                json={"url": "http://localhost:8080/api"}
            )
            assert response.status_code == 403
            assert "restricted network" in response.json()["detail"]


# =============================================================================
# Test security module - is_safe_url_strict (DNS-resolving SSRF Prevention)
# =============================================================================


class TestIsIpSafeAllowedRanges:
    """Tests for _is_ip_safe allowing VPN/proxy/CGNAT ranges."""

    def test_allow_benchmarking_range(self):
        """Test 198.18.0.0/15 (RFC 2544) is allowed — used by VPN/proxy services."""
        from security import _is_ip_safe

        is_safe, _ = _is_ip_safe("198.18.0.186")
        assert is_safe is True

    def test_allow_cgnat_range(self):
        """Test 100.64.0.0/10 (RFC 6598 CGNAT) is allowed — used by Tailscale."""
        from security import _is_ip_safe

        is_safe, _ = _is_ip_safe("100.100.100.100")
        assert is_safe is True

    def test_still_block_rfc1918_private(self):
        """RFC 1918 private ranges should still be blocked."""
        from security import _is_ip_safe

        is_safe, reason = _is_ip_safe("192.168.1.1")
        assert is_safe is False
        assert "private" in reason

    def test_still_block_loopback(self):
        """Loopback should still be blocked."""
        from security import _is_ip_safe

        is_safe, reason = _is_ip_safe("127.0.0.1")
        assert is_safe is False
        assert "loopback" in reason


class TestIsSafeUrlStrict:
    """Tests for is_safe_url_strict function (strict SSRF prevention with DNS resolution)."""

    def test_safe_public_url(self):
        """Public URLs should be allowed."""
        from security import is_safe_url_strict

        is_safe, reason = is_safe_url_strict("https://www.youtube.com/watch?v=abc123", resolve_dns=False)
        assert is_safe
        assert reason is None

    def test_block_localhost_hostname(self):
        """Localhost hostname should be blocked."""
        from security import is_safe_url_strict

        is_safe, reason = is_safe_url_strict("http://localhost/admin", resolve_dns=False)
        assert not is_safe
        assert "blocked hostname" in reason

    def test_block_metadata_hostname(self):
        """Cloud metadata hostnames should be blocked."""
        from security import is_safe_url_strict

        is_safe, reason = is_safe_url_strict("http://metadata.google.internal/v1/", resolve_dns=False)
        assert not is_safe
        assert "blocked hostname" in reason

        is_safe, reason = is_safe_url_strict("http://kubernetes.default.svc/api", resolve_dns=False)
        assert not is_safe
        assert "blocked hostname" in reason

    def test_block_internal_suffix(self):
        """Hostnames ending with .internal should be blocked."""
        from security import is_safe_url_strict

        is_safe, reason = is_safe_url_strict("http://myservice.internal/api", resolve_dns=False)
        assert not is_safe
        assert "blocked hostname suffix" in reason

    def test_block_local_suffix(self):
        """Hostnames ending with .local should be blocked."""
        from security import is_safe_url_strict

        is_safe, reason = is_safe_url_strict("http://myprinter.local/admin", resolve_dns=False)
        assert not is_safe
        assert "blocked hostname suffix" in reason

    def test_block_loopback_ip(self):
        """Loopback IP addresses should be blocked."""
        from security import is_safe_url_strict

        is_safe, reason = is_safe_url_strict("http://127.0.0.1/admin", resolve_dns=False)
        assert not is_safe
        assert "loopback" in reason

    def test_block_private_ip_10(self):
        """10.0.0.0/8 private range should be blocked."""
        from security import is_safe_url_strict

        is_safe, reason = is_safe_url_strict("http://10.0.0.1/internal", resolve_dns=False)
        assert not is_safe
        assert "private" in reason

    def test_block_private_ip_172(self):
        """172.16.0.0/12 private range should be blocked."""
        from security import is_safe_url_strict

        is_safe, reason = is_safe_url_strict("http://172.16.0.1/internal", resolve_dns=False)
        assert not is_safe
        assert "private" in reason

    def test_block_private_ip_192(self):
        """192.168.0.0/16 private range should be blocked."""
        from security import is_safe_url_strict

        is_safe, reason = is_safe_url_strict("http://192.168.1.1/admin", resolve_dns=False)
        assert not is_safe
        assert "private" in reason

    def test_block_link_local_ip(self):
        """Link-local IP addresses (169.254.x.x) should be blocked."""
        from security import is_safe_url_strict

        # 169.254.169.254 is in BLOCKED_HOSTNAMES as AWS metadata endpoint
        is_safe, reason = is_safe_url_strict("http://169.254.169.254/latest/meta-data/", resolve_dns=False)
        assert not is_safe
        assert "blocked hostname" in reason

        # Test an actual link-local IP that's not in the blocklist
        # Note: Python's ipaddress considers link-local IPs as "private"
        is_safe, reason = is_safe_url_strict("http://169.254.1.1/internal/", resolve_dns=False)
        assert not is_safe
        # Accept either "link-local" or "private" since Python may classify it either way
        assert "link-local" in reason or "private" in reason

    def test_missing_hostname(self):
        """URLs without hostname should be blocked."""
        from security import is_safe_url_strict

        is_safe, reason = is_safe_url_strict("http:///path", resolve_dns=False)
        assert not is_safe
        assert "missing hostname" in reason

    def test_dns_resolution_blocking(self, monkeypatch):
        """Hostnames resolving to private IPs should be blocked."""
        import socket

        from security import clear_dns_cache, is_safe_url_strict

        # Clear cache first
        clear_dns_cache()

        # Mock DNS resolution to return a private IP
        def mock_getaddrinfo(hostname, port, family=0, type=0, proto=0, flags=0):
            return [(socket.AF_INET, socket.SOCK_STREAM, 0, '', ('10.0.0.1', 80))]

        monkeypatch.setattr(socket, 'getaddrinfo', mock_getaddrinfo)

        is_safe, reason = is_safe_url_strict("http://evil.example.com/", resolve_dns=True)
        assert not is_safe
        # Reason indicates the hostname resolves to a private address
        assert "private" in reason and "10.0.0.1" in reason


# =============================================================================
# Test security module - sanitize_command_for_logging
# =============================================================================


class TestSanitizeCommandForLogging:
    """Tests for sanitize_command_for_logging function."""

    def test_no_sensitive_flags(self):
        """Commands without sensitive flags should be unchanged."""
        from security import sanitize_command_for_logging

        cmd = ["yt-dlp", "-j", "--no-download", "https://example.com"]
        result = sanitize_command_for_logging(cmd)
        assert result == "yt-dlp -j --no-download https://example.com"

    def test_redact_password(self):
        """--password values should be redacted."""
        from security import sanitize_command_for_logging

        cmd = ["yt-dlp", "--password", "secret123", "https://example.com"]
        result = sanitize_command_for_logging(cmd)
        assert result == "yt-dlp --password [REDACTED] https://example.com"
        assert "secret123" not in result

    def test_redact_username(self):
        """--username values should be redacted."""
        from security import sanitize_command_for_logging

        cmd = ["yt-dlp", "--username", "myuser", "--password", "mypass", "https://example.com"]
        result = sanitize_command_for_logging(cmd)
        assert "myuser" not in result
        assert "mypass" not in result
        assert result.count("[REDACTED]") == 2

    def test_redact_cookies(self):
        """--cookies values should be redacted."""
        from security import sanitize_command_for_logging

        cmd = ["yt-dlp", "--cookies", "/tmp/secret_cookies.txt", "https://example.com"]
        result = sanitize_command_for_logging(cmd)
        assert "/tmp/secret_cookies.txt" not in result
        assert "--cookies [REDACTED]" in result

    def test_redact_add_header(self):
        """--add-header values should be redacted."""
        from security import sanitize_command_for_logging

        cmd = ["yt-dlp", "--add-header", "Authorization:Bearer secret-token", "https://example.com"]
        result = sanitize_command_for_logging(cmd)
        assert "secret-token" not in result
        assert "--add-header [REDACTED]" in result

    def test_redact_equals_format(self):
        """--flag=value format should be redacted."""
        from security import sanitize_command_for_logging

        cmd = ["yt-dlp", "--password=secret123", "https://example.com"]
        result = sanitize_command_for_logging(cmd)
        assert "secret123" not in result
        assert "--password=[REDACTED]" in result

    def test_multiple_sensitive_flags(self):
        """Multiple sensitive flags should all be redacted."""
        from security import sanitize_command_for_logging

        cmd = [
            "yt-dlp",
            "--username", "myuser123",
            "--password", "secretpass456",
            "--cookies", "/tmp/cookies.txt",
            "--add-header", "Auth:token789",
            "https://example.com"
        ]
        result = sanitize_command_for_logging(cmd)
        # Check actual credential values are not in output
        assert "myuser123" not in result
        assert "secretpass456" not in result
        assert "/tmp/cookies.txt" not in result
        assert "token789" not in result
        # Verify all 4 sensitive values are redacted
        assert result.count("[REDACTED]") == 4


# =============================================================================
# Test security module - validate_header
# =============================================================================


class TestValidateHeader:
    """Tests for validate_header function."""

    def test_valid_headers(self):
        """Valid headers should pass."""
        from security import validate_header

        is_valid, reason = validate_header("Authorization", "Bearer token123")
        assert is_valid
        assert reason is None

        is_valid, reason = validate_header("X-Custom-Header", "some value")
        assert is_valid
        assert reason is None

        is_valid, reason = validate_header("Content-Type", "application/json")
        assert is_valid
        assert reason is None

    def test_empty_header_name(self):
        """Empty header names should be rejected."""
        from security import validate_header

        is_valid, reason = validate_header("", "value")
        assert not is_valid
        assert "empty header name" in reason

    def test_invalid_header_name_characters(self):
        """Header names with invalid characters should be rejected."""
        from security import validate_header

        is_valid, reason = validate_header("Header Name", "value")  # Space not allowed
        assert not is_valid
        assert "invalid header name" in reason

        is_valid, reason = validate_header("Header:Name", "value")  # Colon not allowed
        assert not is_valid
        assert "invalid header name" in reason

    def test_header_value_crlf_injection(self):
        """Header values with CR/LF should be rejected (HTTP response splitting)."""
        from security import validate_header

        is_valid, reason = validate_header("X-Header", "value\r\nX-Injected: evil")
        assert not is_valid
        assert "forbidden characters" in reason

        is_valid, reason = validate_header("X-Header", "value\nX-Injected: evil")
        assert not is_valid
        assert "forbidden characters" in reason

        is_valid, reason = validate_header("X-Header", "value\rX-Injected: evil")
        assert not is_valid
        assert "forbidden characters" in reason

    def test_header_name_too_long(self):
        """Very long header names should be rejected."""
        from security import validate_header

        long_name = "X" * 300
        is_valid, reason = validate_header(long_name, "value")
        assert not is_valid
        assert "too long" in reason

    def test_header_value_too_long(self):
        """Very long header values should be rejected."""
        from security import validate_header

        long_value = "x" * 10000
        is_valid, reason = validate_header("X-Header", long_value)
        assert not is_valid
        assert "too long" in reason

    def test_rfc7230_token_characters(self):
        """Header names should allow all RFC 7230 token characters."""
        from security import validate_header

        # All allowed token characters: !#$%&'*+-.^_`|~0-9A-Za-z
        is_valid, reason = validate_header("X-My_Header.v2", "value")
        assert is_valid

        is_valid, reason = validate_header("Accept", "text/html")
        assert is_valid
