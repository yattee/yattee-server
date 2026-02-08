"""Streaming token generation and validation for authenticated playback."""

import base64
import binascii
import hashlib
import hmac
import logging
import os
import secrets
import time
from typing import Optional, Tuple

import config

logger = logging.getLogger(__name__)

# Token expiry in seconds (24 hours)
DEFAULT_EXPIRY_SECONDS = 24 * 60 * 60

_signing_secret = None


def _get_signing_key() -> bytes:
    """Get or generate the signing key for stream tokens."""
    global _signing_secret
    if _signing_secret:
        return _signing_secret.encode("utf-8")

    # Check for secret file in data directory
    os.makedirs(config.DATA_DIR, exist_ok=True)
    secret_file = os.path.join(config.DATA_DIR, ".stream_token_secret")

    if os.path.exists(secret_file):
        with open(secret_file, "r") as f:
            _signing_secret = f.read().strip()
            return _signing_secret.encode("utf-8")

    # Generate new secret
    _signing_secret = secrets.token_urlsafe(32)
    with open(secret_file, "w") as f:
        f.write(_signing_secret)
    # Restrict permissions to owner only
    os.chmod(secret_file, 0o600)

    return _signing_secret.encode("utf-8")


def generate_stream_token(user_id: int, video_id: str, expiry_seconds: int = DEFAULT_EXPIRY_SECONDS) -> str:
    """Generate a time-limited signed token for streaming.

    Args:
        user_id: The authenticated user's ID
        video_id: The video ID being accessed
        expiry_seconds: Token validity period in seconds (default: 24 hours)

    Returns:
        URL-safe base64 encoded token string
    """
    expiry_timestamp = int(time.time()) + expiry_seconds

    # Create payload: user_id:video_id:expiry_timestamp
    payload = f"{user_id}:{video_id}:{expiry_timestamp}"

    # Generate HMAC-SHA256 signature
    signature = hmac.new(_get_signing_key(), payload.encode("utf-8"), hashlib.sha256).digest()

    # Combine payload and signature
    token_data = f"{payload}:{base64.urlsafe_b64encode(signature).decode('utf-8')}"

    # Encode entire token as base64
    return base64.urlsafe_b64encode(token_data.encode("utf-8")).decode("utf-8")


def validate_stream_token(token: str, video_id: str = None) -> Tuple[bool, Optional[int], Optional[str]]:
    """Validate a streaming token.

    Args:
        token: The token to validate
        video_id: Optional video ID to verify against (if provided, must match)

    Returns:
        Tuple of (is_valid, user_id, error_message)
        - is_valid: True if token is valid
        - user_id: The user ID from the token (or None if invalid)
        - error_message: Description of why validation failed (or None if valid)
    """
    if not token:
        return (False, None, "Missing token")

    try:
        # Decode base64 token
        token_data = base64.urlsafe_b64decode(token.encode("utf-8")).decode("utf-8")

        # Split into parts: user_id:video_id:expiry:signature
        parts = token_data.rsplit(":", 1)
        if len(parts) != 2:
            return (False, None, "Invalid token format")

        payload = parts[0]
        provided_signature = base64.urlsafe_b64decode(parts[1].encode("utf-8"))

        # Verify signature
        expected_signature = hmac.new(_get_signing_key(), payload.encode("utf-8"), hashlib.sha256).digest()

        if not hmac.compare_digest(provided_signature, expected_signature):
            return (False, None, "Invalid signature")

        # Parse payload
        payload_parts = payload.split(":")
        if len(payload_parts) != 3:
            return (False, None, "Invalid payload format")

        token_user_id = int(payload_parts[0])
        token_video_id = payload_parts[1]
        expiry_timestamp = int(payload_parts[2])

        # Check expiry
        if time.time() > expiry_timestamp:
            return (False, None, "Token expired")

        # Verify video ID if provided
        if video_id and token_video_id != video_id:
            return (False, None, "Video ID mismatch")

        return (True, token_user_id, None)

    except (ValueError, UnicodeDecodeError, binascii.Error) as e:
        logger.warning(f"Token validation error: {e}")
        return (False, None, "Token validation failed")


def add_token_to_url(url: str, token: str) -> str:
    """Add a token parameter to a URL.

    Args:
        url: The original URL
        token: The token to add

    Returns:
        URL with token parameter added
    """
    if "?" in url:
        return f"{url}&token={token}"
    else:
        return f"{url}?token={token}"
