"""Tests for the YouTube egress proxy: normalization, redaction, client wiring.

Credentials in these tests are obviously fake. Nothing here talks to a real
proxy or to YouTube.
"""

import asyncio
import logging
import os
import socket
import sys
import time
import urllib.parse
import urllib.request
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import egress
import egress_diagnostics
from egress import ProxyConfigError, describe_proxy, normalize_proxy_url, redact_proxy_url, redact_secrets
from settings import Settings
from ytdlp_wrapper import YtDlpError, ytdlp_network_args

# What credentials.get_credentials_for_url() returns when no site credentials apply.
NO_CREDENTIALS = SimpleNamespace(args=[], temp_files=[], cookie_ids=[])

HOST = "proxy.example.net"
PORT = 12323
USER = "demo-user"


class _LazyInnerTube:
    """Import innertube._client on first use (keeps collection-time imports light)."""

    def __getattr__(self, name):
        import innertube._client as module

        return getattr(module, name)

    def __setattr__(self, name, value):
        import innertube._client as module

        setattr(module, name, value)


innertube_client = _LazyInnerTube()


def raw_url(password, scheme="http", user=USER, host=HOST, port=PORT):
    return f"{scheme}://{user}:{password}@{host}:{port}"


# Raw passwords containing the URL-reserved characters that broke parsing.
RAW_PASSWORDS = {
    "plain": "S3cretPlain",
    "at": "pa@ss",
    "colon": "pa:ss",
    "slash": "pa/ss",
    "hash": "pa#ss",
    "percent": "pa%ss",
    "space": "pa ss",
    "everything": "a@b:c/d#e%f g?h",
}


def decode_with_httpx(url):
    proxy = httpx.Proxy(url)
    assert proxy.url.host == HOST
    assert proxy.url.port == PORT
    return proxy.auth


def decode_with_urllib(url):
    """What yt-dlp's urllib handler sees for an http(s) proxy."""
    scheme, user, password, hostport = urllib.request._parse_proxy(url)
    assert hostport == f"{HOST}:{PORT}"
    return urllib.parse.unquote(user), urllib.parse.unquote(password)


def decode_with_ytdlp_socks(url):
    from yt_dlp.networking._helper import make_socks_proxy_opts

    opts = make_socks_proxy_opts(url)
    assert opts["addr"] == HOST
    assert opts["port"] == PORT
    return opts["username"], opts["password"]


# =============================================================================
# A-I: normalization
# =============================================================================


class TestNormalization:
    def test_a_proxy_without_authentication(self):
        assert normalize_proxy_url(f"http://{HOST}:{PORT}") == f"http://{HOST}:{PORT}"
        assert normalize_proxy_url(f"socks5://{HOST}:1080") == f"socks5://{HOST}:1080"

    def test_b_authenticated_http_proxy_is_unchanged_when_already_safe(self):
        url = raw_url("S3cretPlain")
        assert normalize_proxy_url(url) == url

    @pytest.mark.parametrize("label", ["at", "colon", "slash", "hash", "percent", "space", "everything"])
    def test_c_to_h_reserved_characters_are_encoded(self, label):
        password = RAW_PASSWORDS[label]
        normalized = normalize_proxy_url(raw_url(password))

        # The authority still has exactly one '@' (the credential separator),
        # and host/port are preserved exactly.
        assert normalized.count("@") == 1
        assert normalized.endswith(f"@{HOST}:{PORT}")
        parsed = urllib.parse.urlsplit(normalized)
        assert parsed.hostname == HOST
        assert parsed.port == PORT
        assert urllib.parse.unquote(parsed.password) == password
        assert urllib.parse.unquote(parsed.username) == USER

    def test_i_already_encoded_credentials_are_not_double_encoded(self):
        encoded = raw_url("pa%40ss%2Fword")
        assert normalize_proxy_url(encoded) == encoded
        assert "%25" not in normalize_proxy_url(encoded)

    def test_i_normalization_is_idempotent(self):
        for password in RAW_PASSWORDS.values():
            once = normalize_proxy_url(raw_url(password))
            assert normalize_proxy_url(once) == once

    def test_username_with_reserved_characters_is_encoded_too(self):
        # The LAST '@' separates credentials from the host, the FIRST ':' the
        # username from the password; everything else is credential data.
        normalized = normalize_proxy_url(f"http://user@name:pa:ss@{HOST}:{PORT}")
        parsed = urllib.parse.urlsplit(normalized)
        assert parsed.hostname == HOST
        assert urllib.parse.unquote(parsed.username) == "user@name"
        assert urllib.parse.unquote(parsed.password) == "pa:ss"

    def test_scheme_case_and_surrounding_noise_are_cleaned_but_host_preserved(self):
        assert normalize_proxy_url(f'  "HTTP://u:p@{HOST}:{PORT}"\n') == f"http://u:p@{HOST}:{PORT}"

    def test_ipv6_literal_host_is_preserved(self):
        assert normalize_proxy_url("socks5h://u:p@[2001:db8::1]:1080") == "socks5h://u:p@[2001:db8::1]:1080"

    def test_trailing_slash_is_tolerated(self):
        assert normalize_proxy_url(f"http://{HOST}:{PORT}/") == f"http://{HOST}:{PORT}"

    def test_missing_port_is_preserved_not_invented(self):
        assert normalize_proxy_url(f"http://{HOST}") == f"http://{HOST}"


# =============================================================================
# J: malformed configuration
# =============================================================================


class TestMalformed:
    @pytest.mark.parametrize(
        "bad",
        [
            "",
            "   ",
            "proxy.example.net:8080",  # no scheme
            "u:p@proxy.example.net:8080",  # no scheme
            "ftp://proxy.example.net:8080",  # unsupported scheme
            "http://",  # no host
            "http://u:p@",  # no host
            "http://@proxy.example.net:8080",  # empty username
            "http://u:p@proxy.example.net:notaport",
            "http://u:p@proxy.example.net:0",
            "http://u:p@proxy.example.net:70000",
            "http://u:p@proxy.example.net:8080:extra",  # credentials after host?
            "http://u:p@proxy.example.net:8080/path?x=1",  # not a bare proxy
            "http://u:p@proxy .example.net:8080",
            "http://u:p@proxy.example.net:8080\nHost: evil",  # header injection
            "http://u:p@[::1:8080",  # broken IPv6
        ],
    )
    def test_malformed_is_rejected(self, bad):
        with pytest.raises(ProxyConfigError):
            normalize_proxy_url(bad)

    def test_non_string_is_rejected(self):
        with pytest.raises(ProxyConfigError):
            normalize_proxy_url(None)
        with pytest.raises(ProxyConfigError):
            normalize_proxy_url(1234)

    @pytest.mark.parametrize(
        "bad",
        [
            "http://demo-user:Sup3rSecret@proxy.example.net:70000",
            "http://demo-user:Sup3rSecret@proxy.example.net:8080:extra",
            "ftp://demo-user:Sup3rSecret@proxy.example.net:8080",
            "http://demo-user:Sup3rSecret@proxy .example.net:8080",
            "http://:Sup3rSecret@proxy.example.net:8080",
        ],
    )
    def test_error_messages_never_contain_credentials(self, bad):
        with pytest.raises(ProxyConfigError) as exc:
            normalize_proxy_url(bad)
        assert "Sup3rSecret" not in str(exc.value)
        assert "demo-user" not in str(exc.value)

    def test_a_misconfigured_proxy_fails_closed_instead_of_going_direct(self):
        s = Settings(yt_egress_proxy="http://u:p@proxy.example.net:badport", yt_egress_proxy_enabled=True)
        with pytest.raises(ProxyConfigError):
            s.effective_yt_egress_proxy()

    async def test_malformed_proxy_surfaces_as_a_clear_ytdlp_error(self):
        from ytdlp_wrapper import run_ytdlp

        bad = Settings(yt_egress_proxy="http://u:Sup3rSecret@proxy.example.net:badport")
        with patch("ytdlp_wrapper._core.get_settings", return_value=bad):
            with patch("credentials.get_credentials_for_url", AsyncMock(return_value=NO_CREDENTIALS)):
                with pytest.raises(YtDlpError) as exc:
                    await run_ytdlp("--dump-json", "https://www.youtube.com/watch?v=3PFkHDMCLQo")
        assert "egress proxy configuration is invalid" in str(exc.value)
        assert "Sup3rSecret" not in str(exc.value)


# =============================================================================
# K: redaction
# =============================================================================


class TestRedaction:
    SECRET = "Sup3r/Secret#pass@word"

    def test_redacted_url_hides_credentials_but_keeps_host_and_port(self):
        redacted = redact_proxy_url(raw_url(self.SECRET))
        assert redacted == f"http://***@{HOST}:{PORT}"
        assert "Sup3r" not in redacted and USER not in redacted

    def test_redacted_invalid_input_never_leaks(self):
        redacted = redact_proxy_url(f"http://{USER}:{self.SECRET}@{HOST}:badport")
        assert redacted == egress.INVALID_PROXY_PLACEHOLDER

    def test_describe_proxy_contains_no_credentials(self):
        report = describe_proxy(raw_url(self.SECRET))
        assert report == {
            "configured": True,
            "valid": True,
            "scheme": "http",
            "host": HOST,
            "port": PORT,
            "authenticated": True,
        }
        assert self.SECRET not in repr(report) and USER not in repr(report)

    def test_describe_proxy_unconfigured_and_invalid(self):
        assert describe_proxy(None) == {"configured": False}
        invalid = describe_proxy("http://u:Sup3rSecret@host:badport")
        assert invalid["valid"] is False
        assert "Sup3rSecret" not in repr(invalid)

    def test_redact_secrets_removes_every_representation(self):
        raw = raw_url(self.SECRET)
        normalized = normalize_proxy_url(raw)
        encoded_password = urllib.parse.quote(self.SECRET, safe="")
        text = (
            f"error contacting {raw} ... {normalized} ... password={self.SECRET} ... "
            f"enc={encoded_password} ... host {HOST} still readable"
        )
        cleaned = redact_secrets(text, raw)
        assert self.SECRET not in cleaned
        assert encoded_password not in cleaned
        assert normalized not in cleaned
        assert "Sup3r" not in cleaned
        assert HOST in cleaned  # host is diagnostic, not secret

    def test_redact_secrets_without_proxy_is_a_noop(self):
        assert redact_secrets("hello", None) == "hello"

    async def test_ytdlp_failure_never_logs_or_raises_the_proxy_credentials(self, caplog):
        from ytdlp_wrapper import run_ytdlp

        raw = raw_url(self.SECRET)
        s = Settings(yt_egress_proxy=raw, yt_egress_proxy_enabled=True)
        proc = MagicMock()
        proc.returncode = 1
        proc.communicate = AsyncMock(
            return_value=(
                b"",
                f"ERROR: [youtube] 3PFkHDMCLQo: Unable to download API page: [Errno -2] Name or service "
                f"not known (proxy {raw})".encode(),
            )
        )
        with (
            patch("ytdlp_wrapper._core.get_settings", return_value=s),
            patch("credentials.get_credentials_for_url", AsyncMock(return_value=NO_CREDENTIALS)),
            patch("asyncio.create_subprocess_exec", AsyncMock(return_value=proc)),
            caplog.at_level(logging.DEBUG),
        ):
            with pytest.raises(YtDlpError) as exc:
                await run_ytdlp("--dump-json", "https://www.youtube.com/watch?v=3PFkHDMCLQo")

        everything = str(exc.value) + exc.value.stderr + caplog.text
        assert "Sup3r" not in everything
        assert USER not in everything  # the username is never printed either
        # ... and the failure is attributed to the right stage for operators.
        assert "stage=yt-dlp cause=proxy-dns" in caplog.text
        assert f"http://***@{HOST}:{PORT}" in caplog.text


# =============================================================================
# L / M / N: every client gets the same, normalized egress
# =============================================================================


class TestClientsShareTheSameEgress:
    @pytest.mark.parametrize("label", sorted(RAW_PASSWORDS))
    def test_m_ytdlp_receives_the_normalized_proxy(self, label):
        raw = raw_url(RAW_PASSWORDS[label])
        s = Settings(yt_egress_proxy=raw, yt_egress_proxy_enabled=True)
        args = ytdlp_network_args(s)
        assert args[:2] == ["--proxy", normalize_proxy_url(raw)]
        # and the raw (broken) form never reaches yt-dlp's argv
        if raw != normalize_proxy_url(raw):
            assert raw not in args

    @pytest.mark.parametrize("label", sorted(RAW_PASSWORDS))
    async def test_l_innertube_receives_the_normalized_proxy(self, label):
        raw = raw_url(RAW_PASSWORDS[label])
        s = Settings(yt_egress_proxy=raw, yt_egress_proxy_enabled=True)
        captured = {}

        def fake_client(**kwargs):
            captured.update(kwargs)
            return SimpleNamespace(is_closed=False)

        innertube_client._client = None
        try:
            with (
                patch("innertube._client.settings_module.get_settings", return_value=s),
                patch("innertube._client.httpx.AsyncClient", side_effect=fake_client),
            ):
                await innertube_client.get_client()
        finally:
            innertube_client._client = None

        assert captured["proxy"] == normalize_proxy_url(raw)
        assert "transport" not in captured  # proxy= must not be shadowed by transport=

    async def test_innertube_builds_a_real_httpx_client_with_special_characters(self):
        """The raw form used to raise InvalidURL here; the normalized one works."""
        raw = raw_url(RAW_PASSWORDS["everything"])
        with pytest.raises(httpx.InvalidURL):
            httpx.AsyncClient(proxy=raw)  # documents the pre-fix failure mode

        s = Settings(yt_egress_proxy=raw, yt_egress_proxy_enabled=True)
        innertube_client._client = None
        try:
            with patch("innertube._client.settings_module.get_settings", return_value=s):
                client = await innertube_client.get_client()
                assert not client.is_closed
                await client.aclose()
        finally:
            innertube_client._client = None

    async def test_innertube_misconfigured_proxy_is_a_clear_non_retryable_error(self):
        s = Settings(yt_egress_proxy="http://u:Sup3rSecret@host:badport", yt_egress_proxy_enabled=True)
        innertube_client._client = None
        with patch("innertube._client.settings_module.get_settings", return_value=s):
            with pytest.raises(innertube_client.InnerTubeError) as exc:
                await innertube_client.get_client()
        assert exc.value.is_retryable is False
        assert "Sup3rSecret" not in str(exc.value)

    @pytest.mark.parametrize("label", sorted(RAW_PASSWORDS))
    def test_n_all_clients_decode_the_identical_credentials(self, label):
        """httpx, yt-dlp's urllib handler and yt-dlp's SOCKS parser must agree."""
        password = RAW_PASSWORDS[label]
        http_url = normalize_proxy_url(raw_url(password))
        socks_url = normalize_proxy_url(raw_url(password, scheme="socks5"))

        assert decode_with_httpx(http_url) == (USER, password)
        assert decode_with_urllib(http_url) == (USER, password)
        assert decode_with_ytdlp_socks(socks_url) == (USER, password)

    def test_n_every_consumer_reads_the_same_effective_value(self):
        raw = raw_url(RAW_PASSWORDS["everything"])
        s = Settings(yt_egress_proxy=raw, yt_egress_proxy_enabled=True)
        effective = s.effective_yt_egress_proxy()
        assert ytdlp_network_args(s)[1] == effective
        assert effective == normalize_proxy_url(raw)

    def test_r_absent_proxy_leaves_behaviour_unchanged(self):
        s = Settings()
        assert s.effective_yt_egress_proxy() is None
        assert "--proxy" not in ytdlp_network_args(s)
        disabled = Settings(yt_egress_proxy="http://proxy:8080", yt_egress_proxy_enabled=False)
        assert disabled.effective_yt_egress_proxy() is None
        # forced family still applies without a proxy
        assert Settings(yt_ip_family="ipv6").effective_ip_family() == "ipv6"

    def test_a_malformed_value_that_is_disabled_is_ignored(self):
        s = Settings(yt_egress_proxy="not a proxy", yt_egress_proxy_enabled=False)
        assert s.effective_yt_egress_proxy() is None


# =============================================================================
# The structural condition behind "[Errno -2] Name or service not known"
# =============================================================================


class TestHostnameFromCredentialFragment:
    def test_raw_credentials_can_turn_a_credential_fragment_into_the_host(self):
        """Deterministic model of the failure class.

        A standards-based URL parser ends the authority at the first '/', '?' or
        '#', so a raw password containing one of them makes a fragment of the
        CREDENTIALS the host. A resolver asked for that "host" answers
        EAI_NONAME — "[Errno -2] Name or service not known".
        """
        for raw_pw in ("pa/ss", "pa#ss", "pa?ss"):
            broken = urllib.parse.urlsplit(f"socks5://{USER}:{raw_pw}@{HOST}:{PORT}")
            assert broken.hostname == USER  # the username, not the proxy
            assert broken.hostname != HOST

            fixed = urllib.parse.urlsplit(normalize_proxy_url(f"socks5://{USER}:{raw_pw}@{HOST}:{PORT}"))
            assert fixed.hostname == HOST
            assert fixed.port == PORT

    def test_httpx_and_ytdlp_reject_or_misread_the_raw_form(self):
        raw = raw_url("pa/ss")
        with pytest.raises(httpx.InvalidURL):
            httpx.Proxy(raw)
        with pytest.raises(ValueError):
            from yt_dlp.networking._helper import make_socks_proxy_opts

            make_socks_proxy_opts(raw_url("pa/ss", scheme="socks5"))

    def test_the_errno_minus_2_message_is_attributed_to_proxy_dns(self):
        message = "Unable to download API page: [Errno -2] Name or service not known"
        assert egress.classify_egress_failure(message, proxy_configured=True) == "proxy-dns"
        assert egress.classify_egress_failure(message, proxy_configured=False) == "dns"

    @pytest.mark.parametrize(
        "message,expected",
        [
            ("Tunnel connection failed: 407 Proxy Authentication Required", "proxy-auth"),
            ("Tunnel connection failed: 502 Bad Gateway", "proxy-connect"),
            ("[Errno 111] Connection refused", "proxy-connect"),
            ("Sign in to confirm you're not a bot", "youtube-bot-check"),
            ("something else entirely", "unknown"),
        ],
    )
    def test_failure_classification(self, message, expected):
        assert egress.classify_egress_failure(message, proxy_configured=True) == expected


# =============================================================================
# Diagnostics: distinguish DNS / TCP / auth / OK without leaking anything
# =============================================================================


class FakeProxyServer:
    """A tiny HTTP proxy that answers CONNECT with a configurable status."""

    def __init__(self, status=200):
        self.status = status
        self.received = []
        self._server = None
        self.port = None

    async def __aenter__(self):
        async def handle(reader, writer):
            data = await reader.readuntil(b"\r\n\r\n")
            self.received.append(data.decode())
            reason = {200: "Connection established", 407: "Proxy Authentication Required"}.get(self.status, "X")
            writer.write(f"HTTP/1.1 {self.status} {reason}\r\n\r\n".encode())
            await writer.drain()
            writer.close()

        self._server = await asyncio.start_server(handle, "127.0.0.1", 0)
        self.port = self._server.sockets[0].getsockname()[1]
        return self

    async def __aexit__(self, *exc):
        self._server.close()
        await self._server.wait_closed()


class TestDiagnostics:
    async def test_dns_failure_is_reported_as_eai_noname(self):
        gai = socket.gaierror(-2, "Name or service not known")
        with patch("socket.getaddrinfo", side_effect=gai):
            report = await egress_diagnostics.diagnose_proxy(raw_url("pw-123456", host="no-such-host.invalid"))
        assert report["dns"]["ok"] is False
        assert report["dns"]["errno"] == -2
        assert "EAI_NONAME" in report["dns"]["name"]
        assert "tcp" not in report
        line = egress_diagnostics.summarize(report)
        assert "dns=FAILED(EAI_NONAME" in line
        assert "pw-123456" not in line and USER not in line

    async def test_working_proxy_reports_200_and_sends_credentials_only_to_the_proxy(self):
        async with FakeProxyServer(200) as proxy:
            raw = raw_url("pa/ss@word", host="127.0.0.1", port=proxy.port)
            report = await egress_diagnostics.diagnose_proxy(raw)
        assert report["dns"]["ok"] and report["tcp"]["ok"]
        assert report["connect"] == {"ok": True, "status": 200, "meaning": "tunnel established"}
        sent = proxy.received[0]
        assert sent.startswith("CONNECT www.youtube.com:443 HTTP/1.1")
        import base64

        token = sent.split("Proxy-Authorization: Basic ")[1].split("\r\n")[0]
        assert base64.b64decode(token).decode() == f"{USER}:pa/ss@word"  # decoded, correct creds
        assert "pa/ss" not in repr(report)

    async def test_wrong_credentials_are_reported_as_407(self):
        async with FakeProxyServer(407) as proxy:
            report = await egress_diagnostics.diagnose_proxy(raw_url("wrong", host="127.0.0.1", port=proxy.port))
        assert report["connect"]["status"] == 407
        assert "credentials" in report["connect"]["meaning"]

    async def test_refused_connection_is_reported_as_tcp_failure(self):
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        sock.close()  # nothing listens here any more
        report = await egress_diagnostics.diagnose_proxy(raw_url("pw", host="127.0.0.1", port=port))
        assert report["dns"]["ok"] is True
        assert report["tcp"]["ok"] is False

    async def test_invalid_config_is_reported_without_network_access(self):
        report = await egress_diagnostics.diagnose_proxy("http://u:Sup3rSecret@host:badport")
        assert report["valid"] is False
        assert "dns" not in report
        assert "Sup3rSecret" not in repr(report)

    async def test_preflight_log_line_is_credential_free(self, caplog):
        gai = socket.gaierror(-2, "Name or service not known")
        with patch("socket.getaddrinfo", side_effect=gai), caplog.at_level(logging.INFO):
            await egress_diagnostics.log_proxy_preflight(raw_url("Sup3rSecret"))
        assert "[Egress] preflight" in caplog.text
        assert "Sup3rSecret" not in caplog.text and USER not in caplog.text
        assert f"{HOST}:{PORT}" in caplog.text

    async def test_preflight_is_silent_without_a_proxy(self, caplog):
        with caplog.at_level(logging.DEBUG):
            await egress_diagnostics.log_proxy_preflight(None)
        assert "[Egress]" not in caplog.text


# =============================================================================
# O / P / Q: relay egress
# =============================================================================


class RecordingTransport:
    instances = []

    def __init__(self, proxy=None, local_address=None, **kwargs):
        self.proxy = proxy
        self.local_address = local_address
        RecordingTransport.instances.append(self)


class FailingClient:
    """Stops the relay right after the transport choice (connect error)."""

    def __init__(self, *args, **kwargs):
        self.kwargs = kwargs

    def build_request(self, *args, **kwargs):
        return object()

    async def send(self, *args, **kwargs):
        raise httpx.ConnectError("connection refused")

    async def aclose(self):
        pass


def fake_request():
    return SimpleNamespace(
        headers={}, url=SimpleNamespace(scheme="https", netloc="yattee.example"), method="GET"
    )


class TestRelayEgress:
    @pytest.fixture(autouse=True)
    def _reset(self):
        RecordingTransport.instances = []

    async def _relay(self, url, settings, *, safe=True):
        from routers.proxy import _relay

        with (
            patch.object(_relay, "_verify", return_value=True),
            patch.object(_relay, "is_safe_url", return_value=safe),
            patch.object(_relay, "get_settings", return_value=settings),
            patch.object(_relay.httpx, "AsyncHTTPTransport", RecordingTransport),
            patch.object(_relay.httpx, "AsyncClient", FailingClient),
        ):
            return await _relay.relay(fake_request(), url=url, sig="x", exp=int(time.time()) + 600)

    async def test_o_googlevideo_media_leaves_through_the_configured_proxy(self):
        raw = raw_url(RAW_PASSWORDS["everything"])
        s = Settings(yt_egress_proxy=raw, yt_egress_proxy_enabled=True)
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            await self._relay("https://rr1---sn-abc.googlevideo.com/videoplayback?id=1", s)

        assert exc.value.status_code == 502
        assert len(RecordingTransport.instances) == 1
        # the SAME normalized value the other clients use
        assert RecordingTransport.instances[0].proxy == normalize_proxy_url(raw)
        # the connect-error response does not leak the credentials
        assert "everything" not in exc.value.detail and USER not in exc.value.detail

    async def test_p_non_youtube_relay_traffic_is_not_forced_through_the_proxy(self):
        s = Settings(yt_egress_proxy=raw_url("pw-123456"), yt_egress_proxy_enabled=True)
        from fastapi import HTTPException

        for url in (
            "https://vimeo.com/stream.mp4",
            "http://invidious.lan/videoplayback?id=1",
            "https://evilgooglevideo.com/videoplayback",
        ):
            with pytest.raises(HTTPException):
                await self._relay(url, s)
        assert RecordingTransport.instances == []

    async def test_relay_without_proxy_is_unchanged(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException):
            await self._relay("https://rr1---sn-abc.googlevideo.com/videoplayback?id=1", Settings())
        assert RecordingTransport.instances == []

    async def test_relay_with_malformed_proxy_fails_closed_with_a_safe_message(self):
        from fastapi import HTTPException

        s = Settings(yt_egress_proxy="http://u:Sup3rSecret@proxy.example.net:badport", yt_egress_proxy_enabled=True)
        with pytest.raises(HTTPException) as exc:
            await self._relay("https://rr1---sn-abc.googlevideo.com/videoplayback?id=1", s)
        assert exc.value.status_code == 502
        assert "Sup3rSecret" not in exc.value.detail
        assert RecordingTransport.instances == []

    async def test_q_ssrf_guard_still_runs_first_even_with_a_proxy_configured(self):
        """The proxy never widens what the relay will fetch."""
        from fastapi import HTTPException

        from routers.proxy import _relay

        s = Settings(yt_egress_proxy=raw_url("pw-123456"), yt_egress_proxy_enabled=True)
        with (
            patch.object(_relay, "_verify", return_value=True),
            patch.object(_relay, "get_settings", return_value=s),
            patch.object(_relay.httpx, "AsyncHTTPTransport", RecordingTransport),
        ):
            for url in (
                "http://169.254.169.254/latest/meta-data",
                "http://127.0.0.1:8080/admin",
                "http://localhost/secret",
                "http://10.0.0.5/internal",
            ):
                with pytest.raises(HTTPException) as exc:
                    await _relay.relay(fake_request(), url=url, sig="x", exp=int(time.time()) + 600)
                assert exc.value.status_code == 403
        assert RecordingTransport.instances == []

    async def test_q_signature_and_expiry_are_still_enforced(self):
        from fastapi import HTTPException

        from routers.proxy import _relay

        with pytest.raises(HTTPException) as exc:
            await _relay.relay(
                fake_request(), url="https://rr1---sn-abc.googlevideo.com/v", sig="bad", exp=int(time.time()) + 600
            )
        assert exc.value.status_code == 403
        with pytest.raises(HTTPException) as exc:
            await _relay.relay(
                fake_request(), url="https://rr1---sn-abc.googlevideo.com/v", sig="bad", exp=int(time.time()) - 5
            )
        assert exc.value.status_code == 403


# =============================================================================
# Provisioning / admin API boundary
# =============================================================================


class TestProvisioning:
    def test_env_value_is_stored_normalized(self):
        import config
        import env_provisioning

        raw = raw_url(RAW_PASSWORDS["everything"])
        stored = Settings()
        with (
            patch.object(config, "YT_EGRESS_PROXY", raw),
            patch("env_provisioning.settings_module.load_settings", return_value=stored),
            patch("env_provisioning.settings_module.save_settings") as save,
        ):
            env_provisioning._provision_egress_proxy()
        assert save.called
        assert stored.yt_egress_proxy == normalize_proxy_url(raw)
        assert stored.yt_egress_proxy_enabled is True

    def test_malformed_env_value_is_kept_raw_so_runtime_fails_closed_and_logs_safely(self, caplog):
        import config
        import env_provisioning

        raw = "http://u:Sup3rSecret@proxy.example.net:badport"
        stored = Settings()
        with (
            patch.object(config, "YT_EGRESS_PROXY", raw),
            patch("env_provisioning.settings_module.load_settings", return_value=stored),
            patch("env_provisioning.settings_module.save_settings"),
            caplog.at_level(logging.INFO),
        ):
            env_provisioning._provision_egress_proxy()
        assert stored.yt_egress_proxy == raw
        assert "malformed" in caplog.text
        assert "Sup3rSecret" not in caplog.text

    def test_no_env_value_leaves_settings_alone(self):
        import config
        import env_provisioning

        with (
            patch.object(config, "YT_EGRESS_PROXY", None),
            patch("env_provisioning.settings_module.load_settings") as load,
        ):
            env_provisioning._provision_egress_proxy()
        load.assert_not_called()


# =============================================================================
# Review round 2: percent-escape detection, admin secret exposure, preflight safety
# =============================================================================


class TestPercentEscapeDetection:
    def test_valid_escape_is_kept(self):
        assert normalize_proxy_url(raw_url("abc%20def")) == raw_url("abc%20def")

    def test_valid_multibyte_escape_is_kept(self):
        assert normalize_proxy_url(raw_url("%E4%BD%A0")) == raw_url("%E4%BD%A0")

    def test_raw_percent_followed_by_hex_looking_chars_is_encoded(self):
        # "%de" is a lone UTF-8 lead byte, not an escape: it is a raw password.
        assert normalize_proxy_url(raw_url("abc%def")) == raw_url("abc%25def")

    @pytest.mark.parametrize("pw", ["abc%", "abc%2", "abc%zz", "100%"])
    def test_malformed_percent_sequences_are_encoded(self, pw):
        out = normalize_proxy_url(raw_url(pw))
        assert urllib.parse.unquote(urllib.parse.urlsplit(out).password) == pw

    @pytest.mark.parametrize("pw", ["abc%20def", "abc%def", "p%40ss", "a%zzb", "x%e4"])
    def test_idempotent_and_decodes_back_consistently(self, pw):
        once = normalize_proxy_url(raw_url(pw))
        assert normalize_proxy_url(once) == once
        assert httpx.URL(once).password  # parseable by httpx


SECRET_PW = "Sup3r/Secret#pw@1"
SECRET_USER = "isp-user-9x"
SECRET_PROXY = f"http://{SECRET_USER}:{urllib.parse.quote(SECRET_PW, safe='')}@{HOST}:{PORT}"


class TestAdminSettingsSecrecy:
    @pytest.fixture(autouse=True)
    def live_settings(self, admin_client):
        """The shared fixture freezes get_settings(); make it follow save_settings()."""
        import settings as settings_module

        with patch("settings.get_settings", side_effect=lambda: settings_module._cached_settings):
            yield

    def _assert_clean(self, text):
        for needle in (SECRET_PW, urllib.parse.quote(SECRET_PW, safe=""), SECRET_USER):
            assert needle not in text

    def test_get_never_returns_credentials(self, admin_client):
        import settings as settings_module

        s = settings_module.get_settings()
        s.yt_egress_proxy = SECRET_PROXY
        settings_module.save_settings(s)
        resp = admin_client.get("/api/settings")
        assert resp.status_code == 200
        self._assert_clean(resp.text)
        body = resp.json()
        assert body["yt_egress_proxy"] == f"http://***@{HOST}:{PORT}"
        assert body["yt_egress_proxy_configured"] is True
        assert body["yt_egress_proxy_scheme"] == "http"
        assert body["yt_egress_proxy_host"] == HOST
        assert body["yt_egress_proxy_port"] == PORT
        assert body["yt_egress_proxy_authentication_configured"] is True

    def test_unconfigured_proxy_metadata(self, admin_client):
        body = admin_client.get("/api/settings").json()
        assert body["yt_egress_proxy"] is None
        assert body["yt_egress_proxy_configured"] is False
        assert body["yt_egress_proxy_authentication_configured"] is False

    def test_put_response_and_following_get_do_not_echo_credentials(self, admin_client):
        import settings as settings_module

        raw = f"http://{SECRET_USER}:{SECRET_PW}@{HOST}:{PORT}"
        put = admin_client.put("/api/settings", json={"yt_egress_proxy": raw})
        assert put.status_code == 200
        self._assert_clean(put.text)
        self._assert_clean(admin_client.get("/api/settings").text)
        # ... yet the stored value is the real, normalized one
        stored = settings_module.get_settings().yt_egress_proxy
        assert stored == normalize_proxy_url(raw)
        assert urllib.parse.unquote(urllib.parse.urlsplit(stored).password) == SECRET_PW

    def test_roundtripping_the_redacted_value_keeps_the_secret(self, admin_client):
        import settings as settings_module

        admin_client.put("/api/settings", json={"yt_egress_proxy": SECRET_PROXY})
        shown = admin_client.get("/api/settings").json()["yt_egress_proxy"]
        resp = admin_client.put("/api/settings", json={"yt_egress_proxy": shown, "ytdlp_timeout": 99})
        assert resp.status_code == 200
        assert settings_module.get_settings().yt_egress_proxy == normalize_proxy_url(SECRET_PROXY)
        assert resp.json()["ytdlp_timeout"] == 99  # other settings still update

    def test_proxy_can_still_be_replaced_and_cleared(self, admin_client):
        import settings as settings_module

        admin_client.put("/api/settings", json={"yt_egress_proxy": SECRET_PROXY})
        new = f"http://other:newpw@{HOST}:{PORT}"
        admin_client.put("/api/settings", json={"yt_egress_proxy": new})
        assert settings_module.get_settings().yt_egress_proxy == new
        resp = admin_client.put("/api/settings", json={"yt_egress_proxy": None})
        assert resp.status_code == 200 and resp.json()["yt_egress_proxy"] is None
        assert settings_module.get_settings().yt_egress_proxy is None

    def test_malformed_proxy_error_is_credential_free(self, admin_client):
        resp = admin_client.put(
            "/api/settings", json={"yt_egress_proxy": f"http://{SECRET_USER}:{SECRET_PW}@{HOST}:notaport"}
        )
        assert resp.status_code == 400
        self._assert_clean(resp.text)

    def test_other_validation_errors_do_not_leak_the_stored_proxy(self, admin_client):
        import settings as settings_module

        s = settings_module.get_settings()
        s.yt_egress_proxy = SECRET_PROXY
        settings_module.save_settings(s)
        resp = admin_client.put("/api/settings", json={"ytdlp_timeout": 1})  # below ge=10
        assert resp.status_code == 400
        self._assert_clean(resp.text)

    def test_non_secret_settings_unchanged(self, admin_client):
        body = admin_client.get("/api/settings").json()
        assert body["ytdlp_timeout"] == 120 or isinstance(body["ytdlp_timeout"], int)
        assert "yt_ip_family" in body and "yt_pot_enabled" in body


class TestPreflightIsNonFatal:
    """The preflight is diagnostic only: bounded, never raising, never blocking startup."""

    async def _run(self, raw, caplog):
        with caplog.at_level(logging.DEBUG):
            await egress_diagnostics.log_proxy_preflight(raw)
        for needle in ("Sup3rSecret", USER):
            assert needle not in caplog.text
        return caplog.text

    async def test_dns_failure(self, caplog):
        gai = socket.gaierror(-2, "Name or service not known")
        with patch("socket.getaddrinfo", side_effect=gai):
            text = await self._run(raw_url("Sup3rSecret"), caplog)
        assert "dns=FAILED" in text

    async def test_connect_refused(self, caplog):
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        sock.close()
        text = await self._run(raw_url("Sup3rSecret", host="127.0.0.1", port=port), caplog)
        assert "tcp=FAILED" in text

    async def test_407(self, caplog):
        async with FakeProxyServer(407) as proxy:
            text = await self._run(raw_url("Sup3rSecret", host="127.0.0.1", port=proxy.port), caplog)
        assert "connect=407" in text

    async def test_connect_timeout_is_bounded(self, caplog):
        async def hang(*a, **k):
            await asyncio.sleep(60)

        started = time.monotonic()
        with patch("asyncio.open_connection", hang), patch.object(egress_diagnostics, "STEP_TIMEOUT", 0.2):
            report = await egress_diagnostics.diagnose_proxy(
                raw_url("Sup3rSecret", host="127.0.0.1", port=9), timeout=0.2
            )
        assert report["tcp"] == {"ok": False, "error": "timeout"}
        assert time.monotonic() - started < 5

    async def test_silent_proxy_read_is_bounded(self):
        async def silent(reader, writer):
            await asyncio.sleep(30)

        server = await asyncio.start_server(silent, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        started = time.monotonic()
        try:
            report = await egress_diagnostics.diagnose_proxy(
                raw_url("Sup3rSecret", host="127.0.0.1", port=port), timeout=0.3
            )
        finally:
            server.close()
        assert report["connect"] == {"ok": False, "error": "timeout"}
        assert time.monotonic() - started < 5

    async def test_oversized_response_line_is_bounded(self):
        async def flood(reader, writer):
            await reader.read(1024)
            writer.write(b"X" * 200_000)
            await writer.drain()
            await asyncio.sleep(5)

        server = await asyncio.start_server(flood, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        try:
            report = await egress_diagnostics.diagnose_proxy(
                raw_url("Sup3rSecret", host="127.0.0.1", port=port), timeout=2
            )
        finally:
            server.close()
        assert report["connect"]["ok"] is False

    async def test_total_ceiling(self, caplog):
        async def never(*a, **k):
            await asyncio.sleep(60)

        with patch.object(egress_diagnostics, "diagnose_proxy", never), patch.object(
            egress_diagnostics, "TOTAL_TIMEOUT", 0.2
        ):
            started = time.monotonic()
            text = await self._run(raw_url("Sup3rSecret"), caplog)
        assert time.monotonic() - started < 5
        assert "timed out" in text

    async def test_unexpected_exception_is_swallowed_and_sanitized(self, caplog):
        boom = RuntimeError("failed for http://demo-user:Sup3rSecret@proxy.example.net:12323")
        with patch.object(egress_diagnostics, "diagnose_proxy", AsyncMock(side_effect=boom)):
            text = await self._run(raw_url("Sup3rSecret"), caplog)
        assert "RuntimeError" in text  # only the exception type is logged

    @pytest.mark.parametrize(
        "failure",
        [
            RuntimeError("boom Sup3rSecret"),
            asyncio.TimeoutError(),
            socket.gaierror(-2, "Name or service not known"),
        ],
    )
    async def test_server_lifespan_still_starts(self, failure, caplog):
        import server

        app = SimpleNamespace(state=SimpleNamespace())
        s = Settings(yt_egress_proxy=raw_url("Sup3rSecret"), yt_egress_proxy_enabled=True)
        manager = MagicMock(apply_settings=AsyncMock(), stop=AsyncMock())
        with patch.object(server.database, "init_db"), patch.object(
            server.env_provisioning, "apply_env_provisioning"
        ), patch.object(server, "get_settings", return_value=s), patch.object(
            server.egress_diagnostics, "diagnose_proxy", AsyncMock(side_effect=failure)
        ), patch.object(server.pot_provider, "manager", manager), patch.object(
            server.cookie_health, "start_task"
        ), patch.object(server.cookie_health, "stop_task"), patch.object(
            server.proxy, "cleanup_old_files_sync"
        ), patch.object(server.proxy, "start_cleanup_task"), patch.object(
            server.feed_fetcher, "start_feed_fetcher"
        ), patch.object(server.feed_fetcher, "stop_feed_fetcher"), patch.object(
            server.avatar_cache, "start_avatar_cleanup_task"
        ), patch.object(server.avatar_cache, "stop_avatar_cleanup_task"), caplog.at_level(logging.DEBUG):
            started = time.monotonic()
            async with server.lifespan(app):
                assert time.monotonic() - started < 2  # startup was not blocked by the probe
                await app.state.egress_preflight_task  # the task itself must not raise
        assert "Sup3rSecret" not in caplog.text and USER not in caplog.text
