"""HTTP Basic Authentication middleware for Yattee Server."""

import base64
import binascii
import logging
import time
from collections import defaultdict
from typing import Any, Dict, Optional, Tuple

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

import auth
import database
from settings import get_settings

logger = logging.getLogger(__name__)

# Rate limiting: track failed attempts per IP
# Format: {ip_address: [timestamp1, timestamp2, ...]}
_failed_attempts: Dict[str, list] = defaultdict(list)

# Public endpoints that don't require authentication
PUBLIC_PATHS = [
    "/health",
    "/setup",
    "/setup/status",
    "/api/setup",
    "/static/",
    "/favicon.ico",
    "/proxy/",  # Proxy endpoints validate tokens at the endpoint level
    "/api/v1/thumbnails/",  # Thumbnail proxy - validates tokens at the endpoint level
    "/api/v1/captions/",  # Caption proxy - validates tokens at the endpoint level
]

# Paths that return minimal info without auth (for instance detection)
MINIMAL_INFO_PATHS = [
    "/info",
]


# Track last full cleanup time
_last_full_cleanup: float = 0.0


def _cleanup_old_attempts(ip: str) -> None:
    """Remove failed attempts older than the rate limit window."""
    s = get_settings()
    cutoff = time.time() - s.rate_limit_window
    _failed_attempts[ip] = [t for t in _failed_attempts[ip] if t > cutoff]
    if not _failed_attempts[ip]:
        del _failed_attempts[ip]


def _cleanup_all_old_attempts() -> None:
    """Remove all expired failed attempts from all IPs (memory cleanup)."""
    global _last_full_cleanup
    now = time.time()

    # Only run full cleanup periodically
    if now - _last_full_cleanup < get_settings().rate_limit_cleanup_interval:
        return

    _last_full_cleanup = now
    s = get_settings()
    cutoff = now - s.rate_limit_window

    # Clean up all IPs
    ips_to_remove = []
    for ip, timestamps in _failed_attempts.items():
        valid_timestamps = [t for t in timestamps if t > cutoff]
        if valid_timestamps:
            _failed_attempts[ip] = valid_timestamps
        else:
            ips_to_remove.append(ip)

    for ip in ips_to_remove:
        del _failed_attempts[ip]

    if ips_to_remove:
        logger.debug(f"Rate limit cleanup: removed {len(ips_to_remove)} stale IP entries")


def _is_rate_limited(ip: str) -> bool:
    """Check if IP has exceeded rate limit."""
    _cleanup_old_attempts(ip)
    s = get_settings()
    return len(_failed_attempts.get(ip, [])) >= s.rate_limit_max_failures


def _record_failed_attempt(ip: str) -> None:
    """Record a failed authentication attempt."""
    _failed_attempts[ip].append(time.time())


def _is_public_path(path: str) -> bool:
    """Check if path is public (no auth required)."""
    for public_path in PUBLIC_PATHS:
        if path == public_path or path.startswith(public_path):
            return True
    return False


def _is_minimal_info_path(path: str) -> bool:
    """Check if path should return minimal info without auth."""
    return path in MINIMAL_INFO_PATHS


def parse_basic_auth(authorization: str) -> Optional[Tuple[str, str]]:
    """Parse HTTP Basic Auth header.

    Args:
        authorization: The Authorization header value

    Returns:
        Tuple of (username, password) or None if invalid
    """
    if not authorization:
        return None

    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "basic":
        return None

    try:
        decoded = base64.b64decode(parts[1]).decode("utf-8")
        if ":" not in decoded:
            return None
        username, password = decoded.split(":", 1)
        return (username, password)
    except (ValueError, UnicodeDecodeError, binascii.Error):
        return None


def validate_credentials(username: str, password: str) -> Optional[Dict[str, Any]]:
    """Validate basic auth credentials against database.

    Args:
        username: The username
        password: The password

    Returns:
        User dict if valid, None otherwise
    """
    user = database.get_user_by_username(username)
    if not user:
        return None

    if not auth.verify_password(password, user["password_hash"]):
        return None

    return user


class BasicAuthMiddleware(BaseHTTPMiddleware):
    """Middleware that enforces HTTP Basic Authentication when enabled."""

    async def dispatch(self, request: Request, call_next) -> Response:
        """Process request with basic auth check."""
        # Periodic cleanup of rate limiting memory
        _cleanup_all_old_attempts()

        # Auth is always required after setup (when users exist)
        if not database.has_any_user():
            # No users yet - setup not complete, allow access
            return await call_next(request)

        path = request.url.path
        client_ip = request.client.host if request.client else "unknown"

        # Allow public paths without auth
        if _is_public_path(path):
            return await call_next(request)

        # Check rate limiting before processing auth
        if _is_rate_limited(client_ip):
            logger.warning(f"Rate limited IP {client_ip} attempting access to {path}")
            return JSONResponse(
                status_code=429, content={"detail": "Too many failed authentication attempts. Try again later."}
            )

        # For minimal info paths, return minimal response without auth
        if _is_minimal_info_path(path):
            auth_header = request.headers.get("Authorization")
            if not auth_header:
                # Return minimal info for instance detection (auth is always required)
                return JSONResponse(status_code=200, content={"name": "yattee-server"})
            # If auth header provided, validate it and return full info
            credentials = parse_basic_auth(auth_header)
            if credentials:
                user = validate_credentials(credentials[0], credentials[1])
                if user:
                    request.state.user = user
                    response = await call_next(request)
                    response.headers["X-User-Id"] = str(user["id"])
                    return response
            # Invalid auth, return 401
            _record_failed_attempt(client_ip)
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid credentials"},
                headers={"WWW-Authenticate": 'Basic realm="Yattee Server"'},
            )

        # All other paths require authentication
        auth_header = request.headers.get("Authorization")
        if not auth_header:
            return JSONResponse(
                status_code=401,
                content={"detail": "Authentication required"},
                headers={"WWW-Authenticate": 'Basic realm="Yattee Server"'},
            )

        credentials = parse_basic_auth(auth_header)
        if not credentials:
            _record_failed_attempt(client_ip)
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid authorization header"},
                headers={"WWW-Authenticate": 'Basic realm="Yattee Server"'},
            )

        user = validate_credentials(credentials[0], credentials[1])
        if not user:
            _record_failed_attempt(client_ip)
            logger.warning(f"Failed auth attempt from {client_ip} for user '{credentials[0]}'")
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid credentials"},
                headers={"WWW-Authenticate": 'Basic realm="Yattee Server"'},
            )

        # Store user in request state for downstream handlers
        request.state.user = user

        # Update last login timestamp
        database.update_user_last_login(user["id"])

        # Process request
        response = await call_next(request)

        # Add user ID header to response
        response.headers["X-User-Id"] = str(user["id"])

        return response


def get_current_user_from_request(request: Request) -> Optional[Dict[str, Any]]:
    """Get the authenticated user from request state.

    Use this in route handlers to get the user validated by middleware.

    Args:
        request: The FastAPI request object

    Returns:
        User dict or None if not authenticated
    """
    return getattr(request.state, "user", None)


def is_admin_user(request: Request) -> bool:
    """Check if the authenticated user is an admin.

    Args:
        request: The FastAPI request object

    Returns:
        True if user is admin, False otherwise
    """
    user = get_current_user_from_request(request)
    return user is not None and user.get("is_admin", False)
