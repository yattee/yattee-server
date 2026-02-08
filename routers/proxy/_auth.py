"""Proxy token validation."""

from typing import Optional

from fastapi import HTTPException

import database
import tokens


def validate_proxy_token(token: Optional[str], video_id: str) -> None:
    """Validate streaming token when auth is required.

    Auth is required when users exist (setup is complete), regardless of
    the basic_auth_enabled setting. This ensures consistent auth behavior.

    Args:
        token: The token from query parameter
        video_id: The video ID being accessed

    Raises:
        HTTPException: If auth is required and token is invalid
    """
    # Auth required when users exist (setup is complete)
    if not database.has_any_user():
        return  # No users = setup not complete = no auth required

    # Basic auth is enabled, token is required
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required. Missing streaming token.")

    is_valid, user_id, error = tokens.validate_stream_token(token, video_id)
    if not is_valid:
        raise HTTPException(status_code=401, detail=f"Invalid streaming token: {error}")
