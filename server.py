"""Yattee Server - Invidious-compatible API powered by yt-dlp."""

import asyncio
import logging
import os
import platform
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

import avatar_cache
import config
import database
import env_provisioning
import feed_fetcher
import invidious_proxy
from basic_auth import BasicAuthMiddleware
from database.repositories.sites import get_enabled_sites
from routers import admin, channels, comments, playlists, proxy, search, subscriptions, videos
from settings import get_settings

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    # Startup: Initialize database (alembic.ini configures logging)
    database.init_db()
    # Startup: Auto-provision admin user and settings from env vars
    env_provisioning.apply_env_provisioning()
    # Startup: Clean up old download files then start periodic cleanup task
    proxy.cleanup_old_files_sync()
    proxy.start_cleanup_task()
    # Startup: Start feed fetcher for subscriptions
    feed_fetcher.start_feed_fetcher()
    # Startup: Start avatar cache cleanup task
    avatar_cache.start_avatar_cleanup_task()
    yield
    # Shutdown: Stop avatar cache cleanup task
    avatar_cache.stop_avatar_cleanup_task()
    # Shutdown: Stop feed fetcher
    feed_fetcher.stop_feed_fetcher()


app = FastAPI(
    title="Yattee Server",
    description="Invidious-compatible API server for Yattee, powered by yt-dlp",
    version="1.0.0",
    lifespan=lifespan,
)

def configure_cors(app: FastAPI) -> None:
    """Configure CORS middleware based on environment settings.

    Security rules:
    - If specific origins are configured, use them with optional credentials
    - If CORS_ALLOW_ALL is true, allow all origins but DISABLE credentials
    - If neither is set, CORS is effectively disabled (no origins allowed)
    """
    origins: list[str] = []
    allow_credentials = False

    if config.CORS_ORIGINS:
        # Parse comma-separated origins and strip whitespace
        origins = [o.strip() for o in config.CORS_ORIGINS.split(",") if o.strip()]
        # Credentials allowed only with specific origins
        allow_credentials = config.CORS_ALLOW_CREDENTIALS
        logger.info(f"CORS configured with specific origins: {origins}, credentials: {allow_credentials}")
    elif config.CORS_ALLOW_ALL:
        # Development mode: allow all origins but NEVER allow credentials
        # This complies with CORS spec: wildcard + credentials is invalid
        origins = ["*"]
        allow_credentials = False
        logger.warning(
            "CORS configured to allow ALL origins (development mode). "
            "Credentials are DISABLED for security. "
            "Set CORS_ORIGINS for production use."
        )
    else:
        # No CORS configuration - disabled by default (secure)
        logger.info("CORS not configured - cross-origin requests will be blocked")
        return  # Don't add middleware at all

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=allow_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
    )


configure_cors(app)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Middleware to add security headers to all responses."""

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        # Prevent MIME type sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"
        # Prevent clickjacking
        response.headers["X-Frame-Options"] = "DENY"
        # Control referrer information leakage
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response


# Add Security Headers middleware
app.add_middleware(SecurityHeadersMiddleware)

# Add Basic Auth middleware (only enforced when enabled in settings)
app.add_middleware(BasicAuthMiddleware)

# Mount API routers
app.include_router(videos.router, prefix="/api/v1")
app.include_router(search.router, prefix="/api/v1")
app.include_router(channels.router, prefix="/api/v1")
app.include_router(playlists.router, prefix="/api/v1")
app.include_router(proxy.router, prefix="/proxy")
app.include_router(comments.router, prefix="/api/v1")
app.include_router(subscriptions.router, prefix="/api/v1")

# Mount admin router (at root) and static files
app.include_router(admin.router)
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return FileResponse("static/favicon.ico")


@app.middleware("http")
async def add_cache_control(request, call_next):
    """Disable caching for static JS/CSS files during development."""
    response = await call_next(request)
    if request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


# Invidious proxy for captions (proxies to Invidious /companion endpoint)
app.include_router(invidious_proxy.router, prefix="/api/v1")


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok"}


async def get_version(cmd: list[str]) -> str:
    """Get version from a command."""
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
        return stdout.decode().strip().split("\n")[0]
    except (OSError, asyncio.TimeoutError):
        return "not available"


def get_server_version() -> str:
    """Get server version from VERSION file, optionally with git hash suffix."""
    try:
        with open("VERSION") as f:
            base_version = f.read().strip()
    except FileNotFoundError:
        base_version = "unknown"

    git_hash = os.environ.get("GIT_VERSION", "")
    return f"{base_version}-{git_hash}" if git_hash else base_version


@app.get("/info")
async def info():
    """Server info with dependency versions."""
    s = get_settings()

    # Get yt-dlp version
    ytdlp_version = await get_version([s.ytdlp_path, "--version"])

    # Get ffmpeg version
    ffmpeg_raw = await get_version(["ffmpeg", "-version"])
    ffmpeg_version = ffmpeg_raw.split(" ")[2] if "ffmpeg version" in ffmpeg_raw else ffmpeg_raw

    # Get Python packages versions
    import importlib.metadata

    packages = {}
    for pkg in ["fastapi", "uvicorn", "aiohttp", "yt-dlp"]:
        try:
            packages[pkg] = importlib.metadata.version(pkg)
        except importlib.metadata.PackageNotFoundError:
            packages[pkg] = "not installed"

    # Get enabled sites (names only, no credentials)
    enabled_sites = get_enabled_sites()
    sites_list = [
        {"name": site["name"], "extractor_pattern": site.get("extractor_pattern") or ""}
        for site in enabled_sites
    ]

    return {
        "name": "Yattee Server",
        "version": get_server_version(),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "dependencies": {
            "yt-dlp": ytdlp_version,
            "ffmpeg": ffmpeg_version,
        },
        "packages": packages,
        "config": {
            "cache_video_ttl": s.cache_video_ttl,
            "cache_search_ttl": s.cache_search_ttl,
            "cache_channel_ttl": s.cache_channel_ttl,
            "ytdlp_timeout": s.ytdlp_timeout,
            "invidious_instance": s.invidious_instance or "not configured",
            "invidious_author_thumbnails": s.invidious_author_thumbnails,
            "allow_all_sites_for_extraction": s.allow_all_sites_for_extraction,
        },
        "sites": sites_list,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("server:app", host=config.HOST, port=config.PORT, reload=config.DEBUG)
