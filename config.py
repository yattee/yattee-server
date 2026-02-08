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

# Auto-provisioning (optional, for automated deployments)
# When ADMIN_USERNAME and ADMIN_PASSWORD are both set, an admin user is auto-created/updated on startup
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")
# When set, configures the Invidious instance URL and enables the proxy on startup
INVIDIOUS_INSTANCE_URL = os.getenv("INVIDIOUS_INSTANCE_URL")
