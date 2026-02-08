"""Shared dependencies for admin endpoints."""

import os

from fastapi import HTTPException, Request

# Static files directory
STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "static")


async def get_current_admin(request: Request) -> dict:
    """Dependency to get current authenticated admin (must have admin privileges).

    Requires HTTP Basic Auth with admin credentials.
    """
    basic_auth_user = getattr(request.state, "user", None)
    if not basic_auth_user:
        raise HTTPException(
            status_code=401,
            detail="Authentication required",
            headers={"WWW-Authenticate": 'Basic realm="Yattee Server Admin"'},
        )

    if not basic_auth_user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin privileges required")

    return basic_auth_user
