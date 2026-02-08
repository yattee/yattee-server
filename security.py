"""Centralized security utilities for Yattee Server.

This module provides security functions for:
- SSRF protection with DNS resolution validation
- Command/credential sanitization for logging
- Header injection prevention
"""

import ipaddress
import logging
import re
import socket
import time
import urllib.parse
from collections import OrderedDict
from typing import List, Optional, Tuple

from settings import get_settings

logger = logging.getLogger(__name__)

# DNS cache configuration
DNS_CACHE_MAX_SIZE = 1000  # Maximum entries to prevent unbounded growth (DoS)


class LRUDNSCache:
    """LRU cache for DNS resolutions with size limit to prevent DoS."""

    def __init__(self, max_size: int = DNS_CACHE_MAX_SIZE):
        self._cache: OrderedDict[str, Tuple[List[str], float]] = OrderedDict()
        self._max_size = max_size

    def get(self, hostname: str) -> Optional[Tuple[List[str], float]]:
        """Get cached DNS entry, moving to end (most recently used)."""
        if hostname in self._cache:
            self._cache.move_to_end(hostname)
            return self._cache[hostname]
        return None

    def set(self, hostname: str, ips: List[str], timestamp: float) -> None:
        """Set DNS entry, evicting oldest if at capacity."""
        if hostname in self._cache:
            self._cache.move_to_end(hostname)
        self._cache[hostname] = (ips, timestamp)
        # Evict oldest entries if over capacity
        while len(self._cache) > self._max_size:
            self._cache.popitem(last=False)

    def clear(self) -> None:
        """Clear all cached entries."""
        self._cache.clear()

    def __len__(self) -> int:
        """Return number of cached entries."""
        return len(self._cache)


# Global DNS cache instance
_dns_cache = LRUDNSCache()

# Known dangerous hostnames that should always be blocked
BLOCKED_HOSTNAMES = frozenset({
    "localhost",
    "localhost.localdomain",
    "metadata.google.internal",
    "metadata",
    "kubernetes.default.svc",
    "kubernetes.default",
    "kubernetes",
    "instance-data",
    "169.254.169.254",  # AWS/cloud metadata
})


def _resolve_hostname(hostname: str) -> List[str]:
    """Resolve hostname to list of IP addresses.

    Uses LRU caching to reduce DNS lookup latency while preventing
    unbounded cache growth (DoS protection).

    Args:
        hostname: The hostname to resolve

    Returns:
        List of resolved IP addresses as strings
    """
    now = time.time()

    # Check cache
    cached = _dns_cache.get(hostname)
    if cached:
        ips, timestamp = cached
        if now - timestamp < get_settings().dns_cache_ttl:
            return ips

    # Resolve hostname
    try:
        results = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC)
        ips = list(set(result[4][0] for result in results))
        _dns_cache.set(hostname, ips, now)
        return ips
    except socket.gaierror as e:
        logger.warning(f"DNS resolution failed for {hostname}: {e}")
        return []


# Ranges that Python's is_private flags but are safe for SSRF purposes.
# These are not RFC 1918 private networks and are commonly used by
# VPN, proxy, DNS, and carrier-grade NAT services.
_SSRF_ALLOWED_RANGES = (
    ipaddress.ip_network("198.18.0.0/15"),   # RFC 2544 benchmarking
    ipaddress.ip_network("100.64.0.0/10"),   # RFC 6598 CGNAT / Tailscale
)


def _is_ip_safe(ip_str: str) -> Tuple[bool, Optional[str]]:
    """Check if an IP address is safe (not private/reserved/etc).

    Args:
        ip_str: IP address as string

    Returns:
        Tuple of (is_safe, error_reason)
    """
    try:
        ip = ipaddress.ip_address(ip_str)

        if ip.is_loopback:
            return False, "loopback address"
        if any(ip in net for net in _SSRF_ALLOWED_RANGES):
            return True, None
        if ip.is_private:
            return False, "private address"
        if ip.is_link_local:
            return False, "link-local address"
        if ip.is_reserved:
            return False, "reserved address"
        if ip.is_multicast:
            return False, "multicast address"

        # Additional check for IPv4-mapped IPv6 addresses
        if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
            return _is_ip_safe(str(ip.ipv4_mapped))

        return True, None

    except ValueError:
        return False, "invalid IP address"


def is_safe_url_strict(url: str, resolve_dns: bool = True) -> Tuple[bool, Optional[str]]:
    """Check if URL is safe from SSRF attacks with DNS resolution.

    This function performs strict SSRF validation by:
    1. Blocking known dangerous hostnames
    2. Checking if hostname is a direct IP and validating it
    3. Optionally resolving DNS and checking ALL resolved IPs

    Args:
        url: The URL to validate
        resolve_dns: If True, resolve hostname and check all IPs

    Returns:
        Tuple of (is_safe, error_reason)
        - (True, None) if URL is safe
        - (False, "reason") if URL is blocked
    """
    try:
        parsed = urllib.parse.urlparse(url)
        hostname = parsed.hostname

        if not hostname:
            return False, "missing hostname"

        hostname_lower = hostname.lower()

        # Check blocked hostnames
        if hostname_lower in BLOCKED_HOSTNAMES:
            return False, f"blocked hostname: {hostname}"

        # Check if hostname looks like a blocked pattern
        if "metadata" in hostname_lower:
            return False, f"metadata-like hostname: {hostname}"

        # Check if hostname ends with blocked patterns
        blocked_suffixes = [".internal", ".local", ".localhost"]
        for suffix in blocked_suffixes:
            if hostname_lower.endswith(suffix):
                return False, f"blocked hostname suffix: {suffix}"

        # Check if hostname is already an IP address
        try:
            # First check if it's a valid IP address
            ipaddress.ip_address(hostname)
            # If we get here, it's a valid IP - check if it's safe
            is_safe, reason = _is_ip_safe(hostname)
            if not is_safe:
                return False, f"IP address {reason}"
            # If it's a safe IP, we're done
            return True, None
        except ValueError:
            # Not an IP address, continue with hostname validation
            pass

        # Resolve DNS and check all IPs
        if resolve_dns:
            resolved_ips = _resolve_hostname(hostname)
            if not resolved_ips:
                return False, f"DNS resolution failed for {hostname}"

            for ip_str in resolved_ips:
                is_safe, reason = _is_ip_safe(ip_str)
                if not is_safe:
                    return False, f"hostname {hostname} resolves to {reason} ({ip_str})"

        return True, None

    except (ValueError, AttributeError) as e:
        return False, f"URL parsing error: {e}"


# Sensitive yt-dlp flags that should be redacted in logs
SENSITIVE_FLAGS = frozenset({
    "--password",
    "--video-password",
    "--ap-password",
    "--username",
    "--ap-username",
    "--cookies",
    "--cookies-from-browser",
    "--add-header",
    "--netrc-location",
})


def sanitize_command_for_logging(cmd: List[str]) -> str:
    """Sanitize a command for logging, redacting sensitive values.

    Redacts values after sensitive flags like --password, --cookies,
    --add-header, etc.

    Args:
        cmd: Command as list of strings

    Returns:
        Sanitized command string safe for logging
    """
    sanitized = []
    skip_next = False

    for i, arg in enumerate(cmd):
        if skip_next:
            skip_next = False
            sanitized.append("[REDACTED]")
            continue

        # Check if this is a sensitive flag
        if arg in SENSITIVE_FLAGS:
            sanitized.append(arg)
            skip_next = True
            continue

        # Check for --flag=value format
        for flag in SENSITIVE_FLAGS:
            if arg.startswith(f"{flag}="):
                sanitized.append(f"{flag}=[REDACTED]")
                break
        else:
            sanitized.append(arg)

    return " ".join(sanitized)


# Valid characters for HTTP header names (RFC 7230 token)
# token = 1*tchar
# tchar = "!" / "#" / "$" / "%" / "&" / "'" / "*" / "+" / "-" / "." /
#         "^" / "_" / "`" / "|" / "~" / DIGIT / ALPHA
HEADER_NAME_PATTERN = re.compile(r"^[!#$%&'*+\-.^_`|~0-9A-Za-z]+$")

# Header value must not contain CR or LF (HTTP response splitting prevention)
HEADER_VALUE_FORBIDDEN = re.compile(r"[\r\n]")

# Maximum reasonable lengths
MAX_HEADER_NAME_LENGTH = 256
MAX_HEADER_VALUE_LENGTH = 8192


def validate_header(name: str, value: str) -> Tuple[bool, Optional[str]]:
    """Validate HTTP header name and value for injection prevention.

    Checks:
    - Header name follows RFC 7230 token rules
    - Header value contains no CR/LF characters
    - Reasonable length limits

    Args:
        name: HTTP header name
        value: HTTP header value

    Returns:
        Tuple of (is_valid, error_reason)
    """
    if not name:
        return False, "empty header name"

    if len(name) > MAX_HEADER_NAME_LENGTH:
        return False, f"header name too long ({len(name)} > {MAX_HEADER_NAME_LENGTH})"

    if not HEADER_NAME_PATTERN.match(name):
        return False, f"invalid header name characters: {name}"

    if len(value) > MAX_HEADER_VALUE_LENGTH:
        return False, f"header value too long ({len(value)} > {MAX_HEADER_VALUE_LENGTH})"

    if HEADER_VALUE_FORBIDDEN.search(value):
        return False, "header value contains forbidden characters (CR/LF)"

    return True, None


def clear_dns_cache():
    """Clear the DNS resolution cache. Useful for testing."""
    _dns_cache.clear()
