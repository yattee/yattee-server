"""Credential management for yt-dlp integration."""

import logging
import os
import tempfile
from typing import List, Optional, Tuple
from urllib.parse import urlparse

from cryptography.fernet import InvalidToken

import config
import database
import encryption
from security import validate_header

logger = logging.getLogger(__name__)


def _matches_domain(host: str, domain: str) -> bool:
    """Check if host matches domain with proper boundary checking.

    This prevents credential leakage where twitter.com.evil.com would
    incorrectly match "twitter.com".

    Args:
        host: The hostname to check (e.g., "www.twitter.com")
        domain: The domain pattern (e.g., "twitter.com")

    Returns:
        True if host is exactly domain or ends with .domain
    """
    return host == domain or host.endswith("." + domain)


# Map domains to extractor names
DOMAIN_TO_EXTRACTOR = {
    "twitter.com": "twitter",
    "x.com": "twitter",
    "tiktok.com": "tiktok",
    "instagram.com": "instagram",
    "facebook.com": "facebook",
    "fb.com": "facebook",
    "fb.watch": "facebook",
    "vimeo.com": "vimeo",
    "dailymotion.com": "dailymotion",
    "twitch.tv": "twitch",
    "youtube.com": "youtube",
    "youtu.be": "youtube",
    "reddit.com": "reddit",
    "soundcloud.com": "soundcloud",
    "bilibili.com": "bilibili",
    "nicovideo.jp": "niconico",
    "crunchyroll.com": "crunchyroll",
    "funimation.com": "funimation",
}


def extract_extractor_hint(url: str) -> Optional[str]:
    """Extract an extractor hint from a URL.

    Args:
        url: The URL to extract from

    Returns:
        Extractor name hint or None
    """
    try:
        parsed = urlparse(url)
        host = parsed.netloc.lower()

        # Remove www. prefix
        if host.startswith("www."):
            host = host[4:]

        # Check domain map with proper boundary matching
        for domain, extractor in DOMAIN_TO_EXTRACTOR.items():
            if _matches_domain(host, domain):
                return extractor

        # Fallback: use domain without TLD
        parts = host.split(".")
        if len(parts) >= 2:
            return parts[-2]  # e.g., "example" from "example.com"

        return host
    except (ValueError, AttributeError):
        return None


def match_site(extractor_hint: str, site_pattern: str) -> bool:
    """Check if an extractor hint matches a site pattern.

    Supports exact matches and wildcard patterns:
    - "twitter" matches "twitter" exactly
    - "*twitter*" matches anything containing "twitter"
    - "twitter*" matches anything starting with "twitter"
    - "*twitter" matches anything ending with "twitter"

    Note: Substring matching without wildcards is NOT supported
    for security reasons (prevents credential leakage).

    Args:
        extractor_hint: The extractor name from URL
        site_pattern: The pattern configured for a site

    Returns:
        True if they match
    """
    hint_lower = extractor_hint.lower()
    pattern_lower = site_pattern.lower()

    # Exact match
    if hint_lower == pattern_lower:
        return True

    # Wildcard patterns only - no implicit substring matching
    if pattern_lower.startswith("*") and pattern_lower.endswith("*"):
        # *foo* - contains match
        inner = pattern_lower[1:-1]
        return inner in hint_lower if inner else True
    if pattern_lower.startswith("*"):
        # *foo - ends with match
        return hint_lower.endswith(pattern_lower[1:])
    if pattern_lower.endswith("*"):
        # foo* - starts with match
        return hint_lower.startswith(pattern_lower[:-1])

    return False


async def get_credentials_for_url(url: str) -> Tuple[List[str], List[str]]:
    """Get yt-dlp arguments for credentials matching a URL.

    Args:
        url: The URL to find credentials for

    Returns:
        Tuple of (yt-dlp args list, temp file paths to clean up)
    """
    extractor_hint = extract_extractor_hint(url)
    if not extractor_hint:
        return [], []

    # Get all enabled sites
    sites = database.get_enabled_sites()

    args = []
    temp_files = []

    for site in sites:
        if not match_site(extractor_hint, site["extractor_pattern"]):
            continue

        logger.debug(f"Matched site '{site['name']}' for URL: {url}")

        for cred in site.get("credentials", []):
            cred_type = cred["credential_type"]
            key = cred.get("key")
            value = cred["value"]

            # Decrypt if needed
            if cred.get("is_encrypted"):
                try:
                    value = encryption.decrypt(value)
                except InvalidToken as e:
                    logger.error(f"Failed to decrypt credential: {e}")
                    continue

            try:
                cred_args, cred_temp = _build_credential_args(cred_type, key, value)
                args.extend(cred_args)
                temp_files.extend(cred_temp)
            except (ValueError, KeyError, TypeError) as e:
                logger.error(f"Failed to build args for {cred_type}: {e}")

    return args, temp_files


def _build_credential_args(cred_type: str, key: Optional[str], value: str) -> Tuple[List[str], List[str]]:
    """Build yt-dlp arguments for a single credential.

    Args:
        cred_type: The credential type
        key: Optional key (for headers, browser names)
        value: The credential value

    Returns:
        Tuple of (args list, temp file paths)
    """
    args = []
    temp_files = []

    if cred_type == "cookies_file":
        # Write cookies to temp file
        temp_path = _write_temp_file(value, suffix=".txt")
        temp_files.append(temp_path)
        args.extend(["--cookies", temp_path])

    elif cred_type == "cookies_browser":
        # key is browser name (e.g., "chrome", "firefox:Profile 1")
        browser_spec = key or value
        args.extend(["--cookies-from-browser", browser_spec])

    elif cred_type == "login":
        # key is username, value is password
        if key:
            args.extend(["--username", key])
        if value:
            args.extend(["--password", value])

    elif cred_type == "username":
        args.extend(["--username", value])

    elif cred_type == "password":
        args.extend(["--password", value])

    elif cred_type == "video_password":
        args.extend(["--video-password", value])

    elif cred_type == "header":
        # key is header name, value is header value
        if key:
            # Validate header to prevent HTTP header injection
            is_valid, error = validate_header(key, value)
            if not is_valid:
                raise ValueError(f"Invalid header credential: {error}")
            args.extend(["--add-header", f"{key}:{value}"])

    elif cred_type == "netrc":
        args.append("--netrc")

    elif cred_type == "netrc_location":
        args.extend(["--netrc-location", value])

    elif cred_type == "ap_mso":
        args.extend(["--ap-mso", value])

    elif cred_type == "ap_username":
        args.extend(["--ap-username", value])

    elif cred_type == "ap_password":
        args.extend(["--ap-password", value])

    return args, temp_files


def _write_temp_file(content: str, suffix: str = "") -> str:
    """Write content to a temporary file with restricted permissions.

    Args:
        content: File content
        suffix: File suffix

    Returns:
        Path to temp file
    """
    # Ensure temp directory exists
    temp_dir = os.path.join(config.DATA_DIR, "temp")
    os.makedirs(temp_dir, exist_ok=True)

    fd, temp_path = tempfile.mkstemp(suffix=suffix, dir=temp_dir)
    try:
        os.write(fd, content.encode("utf-8"))
        os.chmod(temp_path, 0o600)  # Owner read/write only
    finally:
        os.close(fd)

    return temp_path


def cleanup_temp_files(temp_files: List[str]):
    """Clean up temporary credential files.

    Args:
        temp_files: List of file paths to remove
    """
    for path in temp_files:
        try:
            if os.path.exists(path):
                os.unlink(path)
        except OSError as e:
            logger.error(f"Failed to clean up temp file {path}: {e}")
