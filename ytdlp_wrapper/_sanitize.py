"""YtDlpError, ID/URL/format sanitization."""

import logging
import re
import urllib.parse

logger = logging.getLogger(__name__)


class YtDlpError(Exception):
    """Error from yt-dlp execution."""

    pass


def sanitize_video_id(video_id: str) -> str:
    """Sanitize video ID to prevent command injection."""
    # YouTube video IDs are 11 characters: alphanumeric, dash, underscore
    if re.match(r"^[a-zA-Z0-9_-]{11}$", video_id):
        return video_id
    raise ValueError(f"Invalid video ID format: {video_id}")


def sanitize_channel_id(channel_id: str) -> str:
    """Sanitize channel ID."""
    # Channel IDs start with UC and are 24 chars, or can be @handle
    if re.match(r"^UC[a-zA-Z0-9_-]{22}$", channel_id):
        return channel_id
    if re.match(r"^@[a-zA-Z0-9_.-]+$", channel_id):
        return channel_id
    # Allow channel URLs
    if channel_id.startswith(("http://", "https://")):
        return channel_id
    # Allow base64-like IDs from other platforms (e.g., TikTok's MS4wLjAB... format)
    # These are alphanumeric with possible underscores/dashes, at least 10 chars
    if re.match(r"^[a-zA-Z0-9_-]{10,}$", channel_id):
        return channel_id
    raise ValueError(f"Invalid channel ID format: {channel_id}")


def sanitize_playlist_id(playlist_id: str) -> str:
    """Sanitize playlist ID."""
    # Playlist IDs start with PL, OL, UU, etc.
    if re.match(r"^[a-zA-Z0-9_-]+$", playlist_id):
        return playlist_id
    raise ValueError(f"Invalid playlist ID format: {playlist_id}")


def is_valid_url(url: str) -> bool:
    """Validate URL for extraction (basic security check).

    Rejects:
    - Non http/https schemes
    - URLs without a host
    - URLs starting with '-' (command injection prevention)
    """
    try:
        # Reject URLs starting with '-' (command injection prevention)
        if url.startswith("-"):
            return False
        parsed = urllib.parse.urlparse(url)
        # Must be http or https
        if parsed.scheme not in ("http", "https"):
            return False
        # Must have a host
        if not parsed.netloc:
            return False
        return True
    except (ValueError, AttributeError):
        return False


def is_safe_url(url: str) -> bool:
    """Check if URL is safe from SSRF attacks with DNS resolution.

    This function delegates to is_safe_url_strict() with DNS resolution enabled
    to prevent DNS rebinding attacks where a hostname resolves to a public IP
    during validation but to a private IP when actually fetched.

    Returns:
        True if URL is safe, False if it targets restricted resources
    """
    from security import is_safe_url_strict

    is_safe, reason = is_safe_url_strict(url, resolve_dns=True)
    if not is_safe:
        logger.warning(f"SSRF blocked: {url} - {reason}")
    return is_safe


def sanitize_format_id(format_id: str) -> str:
    """Sanitize format ID to prevent path traversal.

    Allows only alphanumeric characters, dash, underscore, and dot.
    Blocks any path traversal sequences.

    Raises:
        ValueError: If format_id contains invalid characters
    """
    if not format_id:
        raise ValueError("Format ID cannot be empty")

    # Allow alphanumeric, dash, underscore, dot
    if not re.match(r"^[a-zA-Z0-9_.-]+$", format_id):
        raise ValueError(f"Invalid format ID: {format_id}")

    # Block path traversal sequences
    if ".." in format_id or format_id.startswith("/") or format_id.startswith("\\"):
        raise ValueError(f"Invalid format ID (path traversal detected): {format_id}")

    return format_id


def sanitize_extension(ext: str) -> str:
    """Sanitize file extension to prevent path traversal.

    Allows only short alphanumeric extensions (1-10 chars).

    Raises:
        ValueError: If extension is invalid
    """
    if not ext:
        return "mp4"  # Safe default

    # Remove leading dot if present
    if ext.startswith("."):
        ext = ext[1:]

    # Allow only alphanumeric, 1-10 chars
    if not re.match(r"^[a-zA-Z0-9]{1,10}$", ext):
        raise ValueError(f"Invalid extension: {ext}")

    return ext
