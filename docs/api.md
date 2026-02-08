# API Reference

Complete endpoint reference for Yattee Server. All public API endpoints use the `/api/v1` prefix for Invidious compatibility.

## Authentication

Most public API endpoints do not require authentication. When Basic Auth is enabled:

- **Public endpoints** (video, search, channels, playlists, feed) require HTTP Basic Auth headers
- **Proxy and media endpoints** (`/proxy/`, `/api/v1/thumbnails/`, `/api/v1/captions/`) use token-based auth via a `token` query parameter
- **Admin endpoints** (`/api/*` excluding `/api/v1/`) require HTTP Basic Auth with admin privileges
- **Setup endpoints** (`/api/setup/*`) are public until the first admin is created

---

## Video Endpoints

### GET `/api/v1/videos/{video_id}`

Get video metadata including streams, captions, and related videos. Invidious-compatible response format.

**Path Parameters:**
- `video_id` (string) - YouTube video ID

**Query Parameters:**
- `proxy` (boolean, optional) - Include proxy stream URLs
- `invidious` (boolean, optional) - Prefer Invidious data source

**Response:** Invidious-compatible video object with `formatStreams`, `adaptiveFormats`, `captions`, and metadata fields.

---

### GET `/api/v1/extract`

Extract video details from any URL supported by yt-dlp (not just YouTube).

**Query Parameters:**
- `url` (string, required) - URL to extract from

**Response:** Invidious-compatible video object. Requires the site to be enabled in the Sites configuration (or `allow_all_sites_for_extraction` to be enabled).

---

### GET `/api/v1/extract/channel`

Extract videos from a channel/user page on any supported site.

**Query Parameters:**
- `url` (string, required) - Channel or user page URL
- `page` (integer, default: 1) - Page number (min: 1)

**Response:** List of video entries from the channel.

---

## Search Endpoints

### GET `/api/v1/search`

Search for videos, channels, or playlists. Invidious-compatible.

**Query Parameters:**
- `q` (string, required) - Search query
- `page` (integer, default: 1) - Page number (min: 1)
- `sort` (string, optional) - Sort order
- `date` (string, optional) - Date filter
- `duration` (string, optional) - Duration filter
- `type` (string, default: "video") - Result type: `video`, `channel`, or `playlist`

**Response:** Array of search result objects.

---

### GET `/api/v1/search/suggestions`

Get search suggestions. Proxied from Invidious.

**Query Parameters:**
- `q` (string, required) - Search query prefix

**Response:** `{"query": "...", "suggestions": ["..."]}`

---

### GET `/api/v1/trending`

Get trending videos. Proxied from Invidious.

**Query Parameters:**
- `region` (string, default: "US") - Country code

**Response:** Array of trending video objects.

---

### GET `/api/v1/popular`

Get popular videos. Proxied from Invidious.

**Response:** Array of popular video objects.

---

## Channel Endpoints

All channel endpoints support both `@handle` and `UC...` format channel IDs.

### GET `/api/v1/channels/{channel_id}`

Get channel details. Invidious-compatible.

**Path Parameters:**
- `channel_id` (string) - Channel ID or @handle

**Response:** Channel metadata including description, subscriber count, and latest videos.

---

### GET `/api/v1/channels/{channel_id}/videos`

Get channel videos with pagination.

**Path Parameters:**
- `channel_id` (string) - Channel ID or @handle

**Query Parameters:**
- `continuation` (string, optional) - Pagination token

**Response:** `{"videos": [...], "continuation": "..."}`

---

### GET `/api/v1/channels/{channel_id}/playlists`

Get channel playlists.

**Path Parameters:**
- `channel_id` (string) - Channel ID or @handle

**Query Parameters:**
- `continuation` (string, optional) - Pagination token

**Response:** `{"playlists": [...], "continuation": "..."}`

---

### GET `/api/v1/channels/{channel_id}/shorts`

Get channel shorts.

**Path Parameters:**
- `channel_id` (string) - Channel ID or @handle

**Query Parameters:**
- `continuation` (string, optional) - Pagination token

**Response:** `{"videos": [...], "continuation": "..."}`

---

### GET `/api/v1/channels/{channel_id}/streams`

Get channel past live streams.

**Path Parameters:**
- `channel_id` (string) - Channel ID or @handle

**Query Parameters:**
- `continuation` (string, optional) - Pagination token

**Response:** `{"videos": [...], "continuation": "..."}`

---

### GET `/api/v1/channels/{channel_id}/search`

Search for videos within a channel.

**Path Parameters:**
- `channel_id` (string) - Channel ID or @handle

**Query Parameters:**
- `q` (string, required) - Search query
- `page` (integer, default: 1) - Page number (min: 1)

**Response:** Array of video objects matching the query.

---

### GET `/api/v1/channels/{channel_id}/avatar/{size}.jpg`

Proxy channel avatar image.

**Path Parameters:**
- `channel_id` (string) - Channel ID or @handle
- `size` (integer) - Avatar size: 32, 48, 76, 100, 176, or 512

**Query Parameters:**
- `token` (string, optional) - Auth token (required when auth is enabled)

**Response:** JPEG image.

---

### POST `/api/v1/channels/metadata`

Get cached metadata for multiple channels in a single request.

**Request Body:**
```json
{
  "channel_ids": ["UC...", "@handle", ...]
}
```

**Response:** Array of channel metadata objects.

---

## Playlist Endpoints

### GET `/api/v1/playlists/{playlist_id}`

Get playlist details and videos. Invidious-compatible.

**Path Parameters:**
- `playlist_id` (string) - Playlist ID (e.g., `PLxxxxxx`)

**Response:** Playlist metadata with video list.

---

## Comment Endpoints

### GET `/api/v1/comments/{video_id}`

Get comments for a video. Proxied through Invidious.

**Path Parameters:**
- `video_id` (string) - Video ID

**Query Parameters:**
- `continuation` (string, optional) - Pagination token

**Response:** Invidious-compatible comments object.

---

## Feed Endpoints

### POST `/api/v1/feed`

Get a combined feed for a list of channels. The server maintains a background feed fetcher that periodically updates channel feeds.

**Request Body:**
```json
{
  "channels": ["UC...", "@handle", ...],
  "limit": 50,
  "offset": 0
}
```

**Response:** Array of video entries from the requested channels, sorted by date.

---

### POST `/api/v1/feed/status`

Check feed fetch status for a list of channels.

**Request Body:**
```json
{
  "channels": ["UC...", "@handle", ...]
}
```

**Response:** Status information for each channel including last fetch time and errors.

---

## Proxy Endpoints

### GET `/proxy/fast/{video_id}`

Stream video using yt-dlp's parallel downloading. Downloads and streams the video simultaneously for fast playback.

**Path Parameters:**
- `video_id` (string) - Video ID

**Query Parameters:**
- `itag` (string, optional) - Specific format itag
- `format` (string, default: "best") - Format selector
- `url` (string, optional) - Direct stream URL
- `token` (string, optional) - Auth token (required when auth is enabled)

**Response:** Streaming video content with appropriate `Content-Type` header.

---

## Invidious Proxy Endpoints

These endpoints proxy requests through the configured Invidious instance or use yt-dlp as a fallback.

### GET `/api/v1/captions/{video_id}`

Get available captions for a video.

**Path Parameters:**
- `video_id` (string) - Video ID

**Query Parameters:**
- `token` (string, optional) - Auth token (required when auth is enabled)

**Response:** `{"captions": [{"label": "...", "language_code": "...", ...}]}`

---

### GET `/api/v1/captions/{video_id}/content`

Get caption content in the specified format.

**Path Parameters:**
- `video_id` (string) - Video ID

**Query Parameters:**
- `lang` (string, required) - Language code
- `auto` (boolean, default: false) - Use auto-generated captions
- `format` (string, default: "vtt") - Caption format
- `token` (string, optional) - Auth token (required when auth is enabled)

**Response:** Caption content in the requested format.

---

### GET `/api/v1/storyboards/{video_id}`

Get video storyboards. Proxied to Invidious.

**Path Parameters:**
- `video_id` (string) - Video ID

**Response:** Storyboard data.

---

### GET `/api/v1/thumbnails/{video_id}/{filename}`

Proxy video thumbnail images.

**Path Parameters:**
- `video_id` (string) - Video ID
- `filename` (string) - Thumbnail filename

**Query Parameters:**
- `token` (string, optional) - Auth token (required when auth is enabled)

**Response:** Image content.

---

## Utility Endpoints

### GET `/health`

Health check endpoint.

**Response:** `{"status": "ok"}`

---

### GET `/info`

Server info with dependency versions and configuration.

**Response:**
```json
{
  "name": "Yattee Server",
  "version": "...",
  "python": "...",
  "platform": "...",
  "dependencies": {"yt-dlp": "...", "ffmpeg": "..."},
  "packages": {"fastapi": "...", "uvicorn": "...", "aiohttp": "...", "yt-dlp": "..."},
  "config": {
    "cache_video_ttl": 3600,
    "cache_search_ttl": 900,
    "cache_channel_ttl": 1800,
    "ytdlp_timeout": 120,
    "invidious_instance": "...",
    "invidious_author_thumbnails": false,
    "allow_all_sites_for_extraction": false
  },
  "sites": [{"name": "...", "extractor_pattern": "..."}]
}
```

---

## Admin API Endpoints

All admin endpoints require HTTP Basic Auth with admin privileges unless noted otherwise.

### Setup & Login

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/api/setup/status` | None | Check if setup is complete |
| POST | `/api/setup` | None | Create first admin account |
| POST | `/api/login` | None | Verify credentials |

**POST `/api/setup`** body:
```json
{
  "username": "admin",
  "password": "password",
  "invidious_url": "https://invidious.example.com"
}
```

**POST `/api/login`** body:
```json
{
  "username": "admin",
  "password": "password"
}
```

---

### Settings

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/settings` | Get current server settings |
| PUT | `/api/settings` | Update server settings (partial updates supported) |
| GET | `/api/watched-channels` | List watched channels with feed status |
| POST | `/api/watched-channels/refresh-all` | Trigger immediate feed refresh |

---

### Sites & Credentials

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/sites` | List all configured sites |
| POST | `/api/sites` | Create a new site |
| GET | `/api/sites/{id}` | Get site with credentials |
| PUT | `/api/sites/{id}` | Update site configuration |
| DELETE | `/api/sites/{id}` | Delete site and credentials |
| POST | `/api/sites/{id}/credentials` | Add credential to site |
| DELETE | `/api/sites/{id}/credentials/{cid}` | Delete credential |
| POST | `/api/sites/{id}/test` | Test site credentials |
| GET | `/api/extractors` | List popular sites for dropdown |

**POST `/api/sites`** body:
```json
{
  "name": "Example Site",
  "extractor_pattern": "example",
  "enabled": true,
  "priority": 0,
  "proxy_streaming": true,
  "credentials": [
    {"credential_type": "cookies_file", "value": "..."}
  ]
}
```

---

### User Management

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/user/me` | Get current user info (any authenticated user) |
| GET | `/api/users` | List all users |
| POST | `/api/users` | Create user |
| GET | `/api/users/{id}` | Get user by ID |
| PUT | `/api/users/{id}` | Update user (grant/revoke admin) |
| DELETE | `/api/users/{id}` | Delete user |
| PUT | `/api/users/{id}/password` | Change user password |
| GET | `/api/admins` | List admin users |
| POST | `/api/admins` | Create admin |
| DELETE | `/api/admins/{id}` | Delete admin |
| PUT | `/api/admins/{id}/password` | Change admin password |

---

## HTML Pages

These endpoints serve the web UI:

| Endpoint | Description |
|----------|-------------|
| `GET /` | Root redirect (to /setup, /watch, or /login) |
| `GET /admin` | Admin dashboard |
| `GET /setup` | First-run setup wizard |
| `GET /login` | Login page |
| `GET /watch` | Video player page |
