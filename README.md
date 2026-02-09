# Yattee Server

[![Build Status](https://github.com/yattee/yattee-server/actions/workflows/docker-publish.yml/badge.svg)](https://github.com/yattee/yattee-server/actions/workflows/docker-publish.yml)
[![Docker Pulls](https://img.shields.io/docker/pulls/yattee/yattee-server)](https://hub.docker.com/r/yattee/yattee-server)
[![Docker Image Size](https://img.shields.io/docker/image-size/yattee/yattee-server/latest)](https://hub.docker.com/r/yattee/yattee-server)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/Python-3.12+-blue.svg)](https://www.python.org)
[![Platforms](https://img.shields.io/badge/Platforms-amd64%20%7C%20arm64-lightgrey.svg)]()

A self-hosted API server powered by [yt-dlp](https://github.com/yt-dlp/yt-dlp) that manages data extraction from YouTube and other video sites. Designed for use with [Yattee](https://github.com/yattee/yattee).

## Features

- **Multi-site extraction** - YouTube plus any site supported by [yt-dlp](https://github.com/yt-dlp/yt-dlp) (Twitch, Vimeo, BiliBili, etc.) with per-site credentials
- **Admin panel** - Web UI with setup wizard, settings management, site configuration, and user management
- **Authentication** - HTTP Basic Auth, HMAC-signed stream URLs, and rate limiting
- **Invidious proxy** - Optional backing Invidious instance for trending, popular, search suggestions, comments, captions, thumbnails, and avatars
- **Feed system** - Background feed fetcher for channel subscriptions with automatic refresh
- **Stream proxy** - Fast parallel downloading via yt-dlp with streaming delivery
- **Search** - YouTube search with filters (sort, date, duration, type)
- **Channels** - Full channel browsing: videos, playlists, shorts, streams, search, avatars
- **Invidious-compatible API** - Drop-in replacement for [Invidious](https://github.com/iv-org/invidious) API endpoints
- **Caching** - Configurable TTL caching for videos, search, channels, avatars, and extractions
- **Docker ready** - Docker Compose setup with auto-provisioning for automated deployments

## Quick Start

### Local Development

```bash
# Clone the repository
git clone https://github.com/yattee/yattee-server.git
cd yattee-server

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run server (default port 8080)
python server.py
```

Open `http://localhost:8080` to access the setup wizard and create your admin account.

### Docker

```bash
# Copy and configure environment
cp .env.example .env

# Start the server (default port 8085)
docker compose up -d
```

Open `http://localhost:8085` to complete setup.

## Configuration

Yattee Server has two layers of configuration: startup environment variables (`.env` file) and runtime settings (admin panel, stored in database). See [docs/configuration.md](docs/configuration.md) for the full reference.

## API Endpoints

API with endpoints for video extractions, search, channels, playlists, comments, feed subscriptions, stream proxy, captions, thumbnails, and more. See [docs/api.md](docs/api.md) for the full reference.

## Admin Panel

The web-based admin panel is accessible at `/admin` and provides:

- **Setup wizard** - First-run configuration to create the initial admin account and optionally connect an Invidious instance
- **Settings** - All runtime settings (cache TTLs, yt-dlp config, Invidious proxy, feed fetcher, rate limiting, etc.)
- **Sites** - Configure extraction sites with credentials (cookies, API keys) for yt-dlp
- **Users** - Manage admin and regular user accounts
- **Watched channels** - View feed fetcher status and trigger manual refreshes
- **Watch page** - Play any video URL directly in the browser

## Authentication

Yattee Server supports multiple authentication mechanisms:

- **HTTP Basic Auth** - Used for all API and admin panel access. Enforced globally once setup is complete.
- **Token-signed URLs** - Stream proxy URLs (`/proxy/fast/`), thumbnails, and captions include an HMAC-signed token parameter so authenticated clients can pass URLs to video players without exposing credentials.
- **Rate limiting** - Failed authentication attempts are rate-limited per IP address.

Authentication is configured during setup and can be managed in the admin panel under Users.

## Requirements

- **Python 3.12+**
- **yt-dlp** - Video extraction
- **deno** - Required by yt-dlp for YouTube JS challenge solving
- **ffmpeg** - Media processing

## Docker

### Docker Compose

```yaml
services:
  yattee-server:
    build: .
    container_name: yattee-server
    ports:
      - "8085:8085"
    volumes:
      - downloads:/downloads
      - data:/app/data
    env_file:
      - .env
    # Optional: auto-provisioning for automated deployments
    # environment:
    #   - ADMIN_USERNAME=admin
    #   - ADMIN_PASSWORD=changeme
    #   - INVIDIOUS_INSTANCE_URL=https://invidious.example.com
    restart: unless-stopped

volumes:
  downloads:
  data:
```

### Volumes

| Volume | Container Path | Purpose |
|--------|---------------|---------|
| `data` | `/app/data` | Database and encryption keys |
| `downloads` | `/downloads` | Temporary proxied video files |

### Auto-Provisioning

For automated deployments, set these environment variables to skip the setup wizard:

- `ADMIN_USERNAME` + `ADMIN_PASSWORD` - Creates or updates an admin account on startup
- `INVIDIOUS_INSTANCE_URL` - Configures the Invidious instance and enables the proxy

## License

MIT
