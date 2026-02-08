"""Page routes and setup/login API."""

import os
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from pydantic import BaseModel, Field

import auth
import database
import settings as settings_module

from .deps import STATIC_DIR

router = APIRouter()


# =============================================================================
# Pydantic Models
# =============================================================================


class SetupRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=6)
    invidious_url: Optional[str] = None


class LoginRequest(BaseModel):
    username: str
    password: str


# =============================================================================
# Page Routes (serve HTML files)
# =============================================================================


@router.get("/", response_class=HTMLResponse)
async def root(request: Request):
    """Root - redirects to /watch (default page)."""
    if not database.has_any_admin():
        return RedirectResponse(url="/setup", status_code=302)

    basic_auth_user = getattr(request.state, "user", None)
    if basic_auth_user:
        return RedirectResponse(url="/watch", status_code=302)

    return RedirectResponse(url="/login", status_code=302)


@router.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request):
    """Admin dashboard with Sites, Users, Channels, Settings tabs."""
    if not database.has_any_admin():
        return RedirectResponse(url="/setup", status_code=302)

    basic_auth_user = getattr(request.state, "user", None)
    if not basic_auth_user:
        return RedirectResponse(url="/login", status_code=302)
    if not basic_auth_user.get("is_admin"):
        return RedirectResponse(url="/", status_code=302)

    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


@router.get("/setup", response_class=HTMLResponse)
async def setup_page(request: Request):
    """First-run setup page."""
    if database.has_any_admin():
        return RedirectResponse(url="/login", status_code=302)
    return FileResponse(os.path.join(STATIC_DIR, "setup.html"))


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Login page."""
    if not database.has_any_admin():
        return RedirectResponse(url="/setup", status_code=302)

    # Any authenticated user (admin or not) should not see login page
    basic_auth_user = getattr(request.state, "user", None)
    if basic_auth_user:
        return RedirectResponse(url="/", status_code=302)

    return FileResponse(os.path.join(STATIC_DIR, "login.html"))


@router.get("/watch", response_class=HTMLResponse)
async def watch_page(request: Request):
    """Watch page - play any video URL."""
    if not database.has_any_admin():
        return RedirectResponse(url="/setup", status_code=302)

    # Require authentication
    basic_auth_user = getattr(request.state, "user", None)
    if not basic_auth_user:
        return RedirectResponse(url="/login", status_code=302)

    return FileResponse(os.path.join(STATIC_DIR, "watch.html"))


# =============================================================================
# Setup & Auth API
# =============================================================================


@router.get("/api/setup/status")
async def setup_status():
    """Check if setup is complete (any admin exists)."""
    return {"setup_complete": database.has_any_admin()}


@router.post("/api/setup")
async def do_setup(data: SetupRequest):
    """Create the first admin account during initial setup."""
    if database.has_any_admin():
        raise HTTPException(status_code=400, detail="Setup already complete")

    password_hash = auth.hash_password(data.password)
    database.create_admin(data.username, password_hash)

    # Configure Invidious proxy if URL provided
    s = settings_module.load_settings()
    if data.invidious_url and data.invidious_url.strip():
        s.invidious_instance = data.invidious_url.strip().rstrip("/")
        s.invidious_enabled = True
    else:
        s.invidious_enabled = False
    settings_module.save_settings(s)

    return {"success": True, "message": "Admin account created"}


@router.post("/api/login")
async def do_login(data: LoginRequest):
    """Verify credentials (for setup page compatibility)."""
    admin = database.get_admin_by_username(data.username)
    if not admin or not auth.verify_password(data.password, admin["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid username or password")

    # Update last login
    database.update_admin_last_login(admin["id"])

    return {"success": True, "username": admin["username"]}
