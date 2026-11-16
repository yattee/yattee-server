"""Egress policy helpers for YouTube-bound traffic.

The yt_egress_proxy and yt_ip_family settings apply only to YouTube-family
hosts at the HTTP-client layer (the relay also fetches from Invidious —
possibly on the LAN — and from generic extraction sites, where forcing a
proxy or IP family would break connectivity).
"""

import functools
import re
import urllib.parse
from typing import Any, Dict, Optional, Tuple

YOUTUBE_HOST_SUFFIXES = (
    "googlevideo.com",
    "youtube.com",
    "ytimg.com",
    "ggpht.com",
    "youtu.be",
)


def is_youtube_url(url: str) -> bool:
    """True if the URL's host belongs to the YouTube/googlevideo family."""
    try:
        host = urllib.parse.urlsplit(url).hostname
    except ValueError:
        return False
    if not host:
        return False
    host = host.lower()
    return any(host == suffix or host.endswith("." + suffix) for suffix in YOUTUBE_HOST_SUFFIXES)


def local_address_for(family: str) -> Optional[str]:
    """Map an IP family setting to an httpx local_address bind.

    Binding to the wildcard address of one family makes connect attempts on
    the other family fail, which is the httpx way to force a family.
    """
    if family == "ipv6":
        return "::"
    if family == "ipv4":
        return "0.0.0.0"
    return None


# ---------------------------------------------------------------------------
# Egress proxy URL handling
#
# This is the ONE place that parses, validates, normalizes and redacts the
# YouTube egress proxy URL. Every consumer (yt-dlp --proxy, the InnerTube httpx
# client, the /proxy/relay httpx transport, the POT provider via yt-dlp, and all
# diagnostics) takes the value from Settings.effective_yt_egress_proxy(), which
# returns the normalized form produced here.
#
# Why normalization exists: a proxy URL carries credentials in its authority
# (scheme://user:pass@host:port). Credentials that contain URL-reserved
# characters (@ : / # % space ...) are mis-split by URL parsers — httpx raises
# InvalidURL, urllib/yt-dlp split the authority at a different place than httpx
# — so the same string can mean different things to different clients, and a
# fragment of a credential can end up where a hostname is expected. Percent-
# encoding the credentials makes every client (httpx, urllib, yt-dlp's SOCKS
# parser) decode exactly the same username and password.
# ---------------------------------------------------------------------------

SUPPORTED_PROXY_SCHEMES = ("http", "https", "socks4", "socks4a", "socks5", "socks5h")

INVALID_PROXY_PLACEHOLDER = "<invalid proxy configuration>"

_SCHEME_RE = re.compile(r"^([A-Za-z][A-Za-z0-9+.\-]*)://(.*)$", re.DOTALL)
_HOSTNAME_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?$")
_IPV6_RE = re.compile(r"^\[[0-9A-Fa-f:.]+\]$")
# A credential component that is ALREADY safe to place in a URL: only unreserved
# characters, sub-delimiters and well-formed %XX escapes. Anything else (raw @ :
# / # ? space, a stray %, non-ASCII, ...) means it is a raw credential.
_ALREADY_ENCODED_RE = re.compile(r"^(?:[A-Za-z0-9\-._~!$&'()*+,;=]|%[0-9A-Fa-f]{2})*$")


class ProxyConfigError(ValueError):
    """The configured egress proxy URL is malformed.

    The message is always safe to log and to return to a client: it never
    contains the username, the password or the URL.
    """


def _escapes_decode_cleanly(value: str) -> bool:
    """True if the %XX escapes in an encoded-looking value form valid UTF-8.

    Distinguishes real encoding ("abc%20def", "%E4%BD%A0") from a raw password
    that merely contains a '%' followed by two hex digits ("abc%def": %de is a
    lone UTF-8 lead byte, so it is a raw password and gets encoded as abc%25def).
    """
    if "%" not in value:
        return True
    try:
        urllib.parse.unquote_to_bytes(value).decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


def _encode_credential(value: str) -> str:
    """Percent-encode one raw credential; leave an already-encoded one alone."""
    if _ALREADY_ENCODED_RE.match(value) and _escapes_decode_cleanly(value):
        return value
    return urllib.parse.quote(value, safe="")


def _split_proxy(raw: Any) -> Tuple[str, Optional[str], Optional[str], str, Optional[int]]:
    """Parse into (scheme, user, password, host, port) with RAW credentials.

    The authority is split at the LAST '@', so '@', ':', '/', '#', '?' and
    spaces inside the credentials cannot leak into the host. Raises
    ProxyConfigError with a credential-free message.
    """
    if not isinstance(raw, str):
        raise ProxyConfigError("proxy URL must be a string")
    value = raw.strip()
    # Hosting dashboards sometimes keep the quotes around a pasted value.
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        value = value[1:-1].strip()
    if not value:
        raise ProxyConfigError("proxy URL is empty")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise ProxyConfigError("proxy URL contains control characters (stray line break?)")

    match = _SCHEME_RE.match(value)
    if not match:
        raise ProxyConfigError("proxy URL must look like scheme://[user:password@]host:port")
    scheme = match.group(1).lower()
    if scheme not in SUPPORTED_PROXY_SCHEMES:
        raise ProxyConfigError(
            f"unsupported proxy scheme '{scheme}' (use one of: {', '.join(SUPPORTED_PROXY_SCHEMES)})"
        )
    rest = match.group(2)

    at = rest.rfind("@")
    if at >= 0:
        userinfo: Optional[str] = rest[:at]
        hostport = rest[at + 1 :]
    else:
        userinfo = None
        hostport = rest

    # Only a single trailing slash is tolerated after host:port.
    if hostport.endswith("/"):
        hostport = hostport[:-1]
    if not hostport:
        raise ProxyConfigError("proxy URL has no host")
    if any(ch in hostport for ch in "/?#@ \t\\"):
        raise ProxyConfigError("proxy host/port contains invalid characters")

    port: Optional[int] = None
    if hostport.startswith("["):
        end = hostport.find("]")
        host = hostport[: end + 1] if end > 0 else hostport
        tail = hostport[end + 1 :] if end > 0 else ""
        if not _IPV6_RE.match(host):
            raise ProxyConfigError("proxy host is not a valid IPv6 literal")
        port_text = tail[1:] if tail.startswith(":") else ("" if not tail else None)
        if port_text is None:
            raise ProxyConfigError("proxy host/port is malformed")
    else:
        host, sep, port_text = hostport.partition(":")
        if sep and ":" in port_text:
            raise ProxyConfigError(
                "proxy host/port is malformed (extra ':' — credentials must go before '@')"
            )
        if not _HOSTNAME_RE.match(host):
            raise ProxyConfigError("proxy host is not a valid hostname or IP address")
    if port_text:
        if not port_text.isascii() or not port_text.isdigit():
            raise ProxyConfigError("proxy port must be a number")
        port = int(port_text)
        if not 1 <= port <= 65535:
            raise ProxyConfigError("proxy port must be between 1 and 65535")

    user: Optional[str] = None
    password: Optional[str] = None
    if userinfo is not None:
        user, sep, password_text = userinfo.partition(":")
        password = password_text if sep else None
        if not user:
            raise ProxyConfigError("proxy credentials are missing a username")
    return scheme, user, password, host, port


def _build_proxy_url(
    scheme: str, user: Optional[str], password: Optional[str], host: str, port: Optional[int]
) -> str:
    auth = ""
    if user is not None:
        auth = _encode_credential(user)
        if password is not None:
            auth += ":" + _encode_credential(password)
        auth += "@"
    return f"{scheme}://{auth}{host}" + (f":{port}" if port is not None else "")


@functools.lru_cache(maxsize=32)
def _normalize_cached(raw: str) -> str:
    return _build_proxy_url(*_split_proxy(raw))


def normalize_proxy_url(raw: Any) -> str:
    """Return the canonical form of an egress proxy URL, or raise ProxyConfigError.

    - scheme, host and port are preserved exactly (scheme lower-cased);
    - raw credentials are percent-encoded, so @ : / # % and spaces are safe;
    - credentials that are already well-formed percent-encoding are NOT
      double-encoded (a credential is treated as already encoded only when it
      consists solely of unreserved characters, sub-delimiters and valid %XX
      escapes; a mixed value such as "p%40ss word" is treated as raw);
    - whitespace/quotes around the whole value are removed.

    Idempotent: normalize(normalize(x)) == normalize(x).
    """
    if not isinstance(raw, str):
        raise ProxyConfigError("proxy URL must be a string")
    return _normalize_cached(raw)


def redact_proxy_url(raw: Any) -> str:
    """A log-safe rendering: scheme://***@host:port. Never raises, never leaks."""
    try:
        scheme, user, _password, host, port = _split_proxy(raw)
    except ProxyConfigError:
        return INVALID_PROXY_PLACEHOLDER
    return f"{scheme}://{'***@' if user is not None else ''}{host}" + (f":{port}" if port is not None else "")


def describe_proxy(raw: Any) -> Dict[str, Any]:
    """Structured, credential-free diagnostics for a configured proxy."""
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return {"configured": False}
    try:
        scheme, user, _password, host, port = _split_proxy(raw)
    except ProxyConfigError as e:
        return {"configured": True, "valid": False, "error": str(e)}
    return {
        "configured": True,
        "valid": True,
        "scheme": scheme,
        "host": host,
        "port": port,
        "authenticated": user is not None,
    }


def redact_secrets(text: str, raw_proxy: Optional[str]) -> str:
    """Remove the proxy URL and its credentials from free text (logs, stderr)."""
    if not text or not raw_proxy:
        return text
    candidates = set()
    try:
        scheme, user, password, host, port = _split_proxy(raw_proxy)
        candidates.add(raw_proxy.strip())
        candidates.add(_build_proxy_url(scheme, user, password, host, port))
        if user is not None:
            full = user if password is None else f"{user}:{password}"
            candidates.add(full)
            candidates.add(_encode_credential(user) + ("" if password is None else ":" + _encode_credential(password)))
        if password:
            candidates.add(password)
            candidates.add(_encode_credential(password))
            candidates.add(urllib.parse.quote(password, safe=""))
    except ProxyConfigError:
        candidates.add(raw_proxy.strip())
    # Longest first so a URL is replaced before its pieces. Very short
    # fragments would mangle ordinary words, so they are not substituted.
    for secret in sorted((c for c in candidates if c and len(c) >= 4), key=len, reverse=True):
        text = text.replace(secret, "[redacted]")
    return text


def classify_egress_failure(message: str, *, proxy_configured: bool) -> str:
    """Name the stage an egress failure most plausibly belongs to.

    Pure string classification of an error message we already hold (yt-dlp
    stderr, an httpx exception text) — safe to log, contains no secrets.
    """
    text = (message or "").lower()
    if "errno -2" in text or "name or service not known" in text or "nodename nor servname" in text:
        return "proxy-dns" if proxy_configured else "dns"
    if "407" in text or "proxy authentication" in text:
        return "proxy-auth"
    if "tunnel connection failed" in text or "proxyerror" in text or "proxy error" in text:
        return "proxy-connect"
    if "connection refused" in text or "errno 111" in text or "timed out" in text or "timeout" in text:
        return "proxy-connect" if proxy_configured else "network"
    if "sign in to confirm" in text or "not a bot" in text:
        return "youtube-bot-check"
    if "unplayable" in text or "http error 403" in text or " 403" in text:
        return "youtube-rejected"
    return "unknown"
