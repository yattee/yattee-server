# Configuration Reference

Yattee Server has two layers of configuration:

1. **Startup environment variables** - Read once at server start from `.env` file or system environment. Changing these requires a server restart.
2. **Runtime settings** - Managed via the admin panel and stored in the database. Changes take effect immediately.

---

## Startup Environment Variables

Set these in your `.env` file or as system/Docker environment variables.

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `HOST` | string | `0.0.0.0` | Server bind address |
| `PORT` | integer | `8080` | Server port. Docker default is `8085`. |
| `DATA_DIR` | string | `data` | Directory for database, encryption keys, and temp files |
| `DOWNLOAD_DIR` | string | *(empty)* | Directory for proxied video downloads. If empty, uses a default location. |
| `CREDENTIALS_ENCRYPTION_KEY` | string | *(auto-generated)* | Fernet encryption key for site credentials. Auto-generated on first run if not set. Generate with: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |
| `CORS_ORIGINS` | string | *(empty)* | Comma-separated list of allowed origins (e.g., `https://app.example.com,https://admin.example.com`) |
| `CORS_ALLOW_ALL` | boolean | `false` | Allow all origins. Credentials are **disabled** in this mode. For development only. |
| `CORS_ALLOW_CREDENTIALS` | boolean | `true` | Allow credentials (cookies, authorization headers). Only works with specific origins. |
| `DEBUG` | boolean | `false` | Enable auto-reload for development |
| `SECURE_COOKIES` | boolean | `true` | Enforce HTTPS-only cookies. Set to `false` for local development without HTTPS. |
| `YTDLP_SKIP_TLS_VERIFY` | boolean | `false` | Skip TLS certificate verification in yt-dlp. Not recommended for production. |
| `ADMIN_USERNAME` | string | *(none)* | Auto-provisioning: creates or updates an admin user with this username on startup |
| `ADMIN_PASSWORD` | string | *(none)* | Auto-provisioning: password for the auto-provisioned admin. Both `ADMIN_USERNAME` and `ADMIN_PASSWORD` must be set. |
| `INVIDIOUS_INSTANCE_URL` | string | *(none)* | Auto-provisioning: configures the Invidious instance URL and enables the proxy on startup |

Boolean values accept: `true`, `1`, `yes` (case-insensitive) for true; anything else is false.

### Auto-Provisioning

For automated deployments (Docker, CI/CD), you can skip the setup wizard by setting:

- `ADMIN_USERNAME` + `ADMIN_PASSWORD` - Creates the admin account automatically on startup. If the user already exists, the password is updated.
- `INVIDIOUS_INSTANCE_URL` - Sets the Invidious instance URL in runtime settings and enables the Invidious proxy.

---

## Runtime Settings

These settings are configured via the admin panel (`/admin` > Settings) and stored in the database. Changes take effect immediately without restarting the server.

### yt-dlp

| Setting | Type | Default | Range | Description |
|---------|------|---------|-------|-------------|
| `ytdlp_path` | string | `yt-dlp` | - | Path to the yt-dlp binary |
| `ytdlp_timeout` | integer | `120` | 10 - 600 | yt-dlp command timeout in seconds |

### Cache TTLs

All cache TTL values are in seconds.

| Setting | Type | Default | Range | Description |
|---------|------|---------|-------|-------------|
| `cache_video_ttl` | integer | `3600` | 60 - 86400 | Video info cache TTL |
| `cache_search_ttl` | integer | `900` | 60 - 7200 | Search results cache TTL |
| `cache_channel_ttl` | integer | `1800` | 60 - 86400 | Channel info cache TTL |
| `cache_avatar_ttl` | integer | `86400` | 3600 - 604800 | Avatar cache TTL |
| `cache_extract_ttl` | integer | `900` | 60 - 7200 | URL extraction cache TTL |

### Search

| Setting | Type | Default | Range | Description |
|---------|------|---------|-------|-------------|
| `default_search_results` | integer | `20` | 5 - 50 | Default number of search results per page |
| `max_search_results` | integer | `50` | 10 - 100 | Maximum search results allowed per request |

### Invidious Proxy

| Setting | Type | Default | Range | Description |
|---------|------|---------|-------|-------------|
| `invidious_enabled` | boolean | `true` | - | Enable Invidious proxy |
| `invidious_instance` | string | *(none)* | - | Invidious instance URL (e.g., `https://invidious.example.com`) |
| `invidious_timeout` | integer | `10` | 5 - 60 | Request timeout in seconds |
| `invidious_max_retries` | integer | `3` | 1 - 10 | Maximum retry attempts on failure |
| `invidious_retry_delay` | float | `1.0` | 0.5 - 30.0 | Delay between retries in seconds |
| `invidious_author_thumbnails` | boolean | `false` | - | Fetch author thumbnails from Invidious for video responses (adds latency) |
| `invidious_proxy_channels` | boolean | `true` | - | Proxy channel requests through Invidious (faster, includes upload dates) |
| `invidious_proxy_channel_tabs` | boolean | `true` | - | Proxy channel tabs (playlists, shorts, streams) through Invidious |
| `invidious_proxy_videos` | boolean | `true` | - | Proxy video requests through Invidious |
| `invidious_proxy_playlists` | boolean | `true` | - | Proxy playlist requests through Invidious |
| `invidious_proxy_captions` | boolean | `true` | - | Proxy caption requests through Invidious |
| `invidious_proxy_thumbnails` | boolean | `true` | - | Proxy thumbnail requests through Invidious |

### Feed

| Setting | Type | Default | Range | Description |
|---------|------|---------|-------|-------------|
| `feed_fetch_interval` | integer | `1800` | 300 - 86400 | Background feed fetch interval in seconds |
| `feed_channel_delay` | integer | `2` | 1 - 30 | Delay between fetching individual channels in seconds |
| `feed_max_videos` | integer | `30` | 10 - 100 | Maximum videos to store per channel |
| `feed_video_max_age` | integer | `30` | 1 - 365 | Maximum video age in days |
| `feed_ytdlp_use_flat_playlist` | boolean | `true` | - | Use fast yt-dlp flat-playlist mode (recommended). Disabling may cause timeouts but provides publish dates when Invidious is unavailable. |
| `feed_fallback_ytdlp_on_414` | boolean | `false` | - | Automatically use yt-dlp when Invidious hits 414 pagination errors |
| `feed_fallback_ytdlp_on_error` | boolean | `true` | - | Automatically use yt-dlp when Invidious fails after retries (500, 502, etc.) |

### Extraction

| Setting | Type | Default | Range | Description |
|---------|------|---------|-------|-------------|
| `allow_all_sites_for_extraction` | boolean | `false` | - | Allow extraction from any yt-dlp-supported site. When disabled, only sites enabled in the Sites table are allowed. |

### Security

| Setting | Type | Default | Range | Description |
|---------|------|---------|-------|-------------|
| `dns_cache_ttl` | integer | `30` | 5 - 3600 | DNS cache TTL in seconds |

### Rate Limiting (Basic Auth)

| Setting | Type | Default | Range | Description |
|---------|------|---------|-------|-------------|
| `rate_limit_window` | integer | `60` | 10 - 600 | Time window for tracking failed attempts in seconds |
| `rate_limit_max_failures` | integer | `5` | 1 - 100 | Maximum failed attempts before blocking |
| `rate_limit_cleanup_interval` | integer | `300` | 60 - 3600 | Interval for cleaning up expired rate limit entries in seconds |

### Proxy & Downloads

| Setting | Type | Default | Range | Description |
|---------|------|---------|-------|-------------|
| `proxy_download_max_age` | integer | `86400` | 60 - 604800 | Maximum age for cached download files in seconds |
| `proxy_max_concurrent_downloads` | integer | `3` | 1 - 20 | Maximum concurrent proxy downloads |
