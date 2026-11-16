"""Configuration for Yattee Server.

Startup-only settings are configured here via environment variables.
Runtime settings are managed via the admin panel and stored in the database.
"""

import os

# Server settings (startup-only)
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8080"))

# Data directory (for database, temp files, etc.)
DATA_DIR = os.getenv("DATA_DIR", "data")

# Download directory (for proxied video downloads)
DOWNLOAD_DIR = os.getenv("DOWNLOAD_DIR", "")

# Encryption key for sensitive credentials (auto-generated if not set)
# Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
CREDENTIALS_ENCRYPTION_KEY = os.getenv("CREDENTIALS_ENCRYPTION_KEY")

# CORS settings
# Comma-separated list of allowed origins (e.g., "https://app.example.com,https://admin.example.com")
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "")

# Allow all origins (development mode) - credentials will be DISABLED in this mode
CORS_ALLOW_ALL = os.getenv("CORS_ALLOW_ALL", "false").lower() in ("true", "1", "yes")

# Allow credentials (cookies, authorization headers) - only works with specific origins
CORS_ALLOW_CREDENTIALS = os.getenv("CORS_ALLOW_CREDENTIALS", "true").lower() in ("true", "1", "yes")

# Debug mode (enables auto-reload in development)
DEBUG = os.getenv("DEBUG", "false").lower() in ("true", "1", "yes")

# Secure cookies (set to false only for local development without HTTPS)
SECURE_COOKIES = os.getenv("SECURE_COOKIES", "true").lower() in ("true", "1", "yes")

# Skip TLS certificate verification in yt-dlp (not recommended for production)
YTDLP_SKIP_TLS_VERIFY = os.getenv("YTDLP_SKIP_TLS_VERIFY", "false").lower() in ("true", "1", "yes")

# HTTP proxy for YouTube-bound egress (yt-dlp, InnerTube, /proxy/relay of
# googlevideo media). Format: scheme://[user:password@]host:port with scheme in
# http, https, socks4, socks4a, socks5, socks5h. Raw credentials may contain
# @ : / # % or spaces: egress.normalize_proxy_url() percent-encodes them once,
# for every client. A malformed value makes YouTube requests fail with a clear
# (credential-free) error instead of silently going out directly.
YT_EGRESS_PROXY = os.getenv("YT_EGRESS_PROXY") or None

# Force IP family for YouTube-bound egress: "auto", "ipv4" or "ipv6".
# Seeds the yt_ip_family setting on startup (see env_provisioning.py).
YT_IP_FAMILY = os.getenv("YT_IP_FAMILY") or None

# PO token provider (bgutil): "true"/"false" seeds the yt_pot_enabled setting
# on startup; YT_POT_PROVIDER_URL points at an external provider instead of
# the bundled one (see env_provisioning.py).
YT_POT_ENABLED = os.getenv("YT_POT_ENABLED") or None
YT_POT_PROVIDER_URL = os.getenv("YT_POT_PROVIDER_URL") or None

# Additional CIDR ranges to permit through the SSRF guard.
# Comma-separated list of IPv4/IPv6 networks in CIDR notation, e.g.
# "10.20.30.0/24,fd00::/8" — useful when a backing service (Invidious /
# yattee-server companion) lives on the LAN and returns stream URLs that
# point at private IPs. Entries are parsed at startup; malformed values
# are logged and dropped. Loopback is always blocked regardless.
SSRF_EXTRA_ALLOWED_CIDRS = os.getenv("SSRF_EXTRA_ALLOWED_CIDRS", "")

# Auto-provisioning (optional, for automated deployments)
# When ADMIN_USERNAME and ADMIN_PASSWORD are both set, an admin user is auto-created/updated on startup
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")
# When set, configures the Invidious instance URL and enables the proxy on startup
INVIDIOUS_INSTANCE_URL = os.getenv("INVIDIOUS_INSTANCE_URL")
