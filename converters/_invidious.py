"""Invidious to model conversions."""

import logging
from datetime import datetime
from typing import Optional

import tokens as token_utils
from converters._formatting import parse_relative_time
from converters._helpers import (
    _convert_invidious_thumbnail_to_proxy,
    _enrich_audio_display_name,
    _extract_region_from_label,
    _filter_sensitive_headers,
    _label_to_lang_code,
    _xtags_from_url,
    resolve_invidious_url,
)
from models import (
    AdaptiveFormat,
    AudioTrack,
    Caption,
    ChannelListItem,
    FormatStream,
    PlaylistListItem,
    PlaylistResponse,
    Storyboard,
    Thumbnail,
    VideoListItem,
    VideoResponse,
)
from settings import get_settings


def invidious_to_video_response(
    info: dict,
    base_url: str = "",
    proxy_streams: bool = False,
    proxy_mode: str = "download",
    invidious_base_url: str = "",
    user_id: Optional[int] = None,
) -> VideoResponse:
    """Convert Invidious video API response to VideoResponse.

    Invidious already returns data in our target format, so this is mostly passthrough.

    Args:
        info: Invidious video info dict
        base_url: Base URL for proxy URLs (yattee-server URL)
        proxy_streams: If True, stream URLs are proxied through this server.
        proxy_mode: ``"relay"`` (default for playback) → /proxy/relay byte-relay.
            ``"download"`` → /proxy/fast/ on-disk cache (downloads). ``"off"``
            is equivalent to ``proxy_streams=False``. Ignored when proxying off.
        invidious_base_url: The Invidious instance URL for resolving relative paths
        user_id: User ID for generating streaming tokens (if basic auth enabled)
    """
    s = get_settings()

    # Get Invidious base URL from settings if not provided
    if not invidious_base_url:
        invidious_base_url = (s.invidious_instance or "").rstrip("/")

    effective_proxy_mode = proxy_mode if proxy_streams else "off"

    def _proxy_url(invidious_url: str, itag: str, content_type: Optional[str] = None) -> str:
        """Pick the URL the client will hit for one Invidious-extracted stream.

        - relay: resolve to absolute URL, then sign it for /proxy/relay
        - download: legacy /proxy/fast/{video_id}?itag=… (re-extracts via yt-dlp)
        - off: passthrough, with /videoplayback resolved against the Invidious base
        """
        if effective_proxy_mode == "relay" and base_url and invidious_url:
            from routers.proxy import signed_relay_url

            absolute = resolve_invidious_url(invidious_url, invidious_base_url)
            return signed_relay_url(base_url, absolute, content_type=content_type)
        if effective_proxy_mode == "download" and base_url and itag:
            url = f"{base_url}/proxy/fast/{video_id}?itag={itag}"
            if stream_token:
                url = f"{url}&token={stream_token}"
            return url
        # Off / passthrough — keep existing behavior (Invidious local URLs go
        # through /companion).
        if invidious_url.startswith("/videoplayback"):
            invidious_url = "/companion" + invidious_url
        return resolve_invidious_url(invidious_url, invidious_base_url)

    video_id = info.get("videoId", "")

    # Generate token if user_id is provided (basic auth enabled)
    # Stream token is used for proxy stream URLs (requires proxy_streams=True)
    stream_token = None
    if user_id is not None and proxy_streams and video_id:
        stream_token = token_utils.generate_stream_token(user_id, video_id)

    # Caption token is used for caption content URLs (always when user_id is set)
    caption_token = None
    if user_id is not None and base_url and video_id:
        caption_token = token_utils.generate_stream_token(user_id, video_id)

    # Thumbnail token is used for proxied thumbnail URLs (always when user_id is set)
    thumbnail_token = None
    if user_id is not None and base_url and video_id:
        thumbnail_token = token_utils.generate_stream_token(user_id, video_id)

    # Convert thumbnails (with optional proxying)
    video_thumbnails = []
    for thumb in info.get("videoThumbnails", []):
        url = thumb.get("url", "")
        if s.invidious_proxy_thumbnails and base_url:
            url = _convert_invidious_thumbnail_to_proxy(url, base_url, token=thumbnail_token or "")
        video_thumbnails.append(
            Thumbnail(
                quality=thumb.get("quality", "default"), url=url, width=thumb.get("width"), height=thumb.get("height")
            )
        )

    author_thumbnails = []
    for thumb in info.get("authorThumbnails", []):
        url = thumb.get("url", "")
        if s.invidious_proxy_thumbnails and base_url:
            url = _convert_invidious_thumbnail_to_proxy(url, base_url, token=thumbnail_token or "")
        author_thumbnails.append(
            Thumbnail(
                quality=thumb.get("quality", "default"), url=url, width=thumb.get("width"), height=thumb.get("height")
            )
        )

    # Convert format streams
    format_streams = []
    for fmt in info.get("formatStreams", []):
        original_url = fmt.get("url", "")
        itag = str(fmt.get("itag", ""))
        url = _proxy_url(original_url, itag, content_type=fmt.get("type"))
        format_streams.append(
            FormatStream(
                url=url,
                itag=str(itag),
                type=fmt.get("type", ""),
                quality=fmt.get("quality", ""),
                container=fmt.get("container", ""),
                resolution=fmt.get("resolution"),
                width=fmt.get("width"),
                height=fmt.get("height"),
                encoding=fmt.get("encoding"),
                size=fmt.get("size"),
                fps=fmt.get("fps"),
                httpHeaders=_filter_sensitive_headers(fmt.get("httpHeaders")),
            )
        )

    # Convert adaptive formats
    adaptive_formats = []
    for fmt in info.get("adaptiveFormats", []):
        original_url = fmt.get("url", "")
        itag = str(fmt.get("itag", ""))
        url = _proxy_url(original_url, itag, content_type=fmt.get("type"))

        # iOS Yattee determines "original audio" from displayName containing
        # "original" (or URL xtags). The relay proxy hides xtags by URL-encoding
        # the upstream URL, so parse xtags from `original_url` *before* it's
        # wrapped and bake the marker into displayName.
        #
        # Invidious frequently omits the `audioTrack` object on adaptive formats
        # for multi-language videos — the language metadata only lives in the
        # upstream URL's xtags. Synthesize an AudioTrack from xtags in that case
        # so the iOS client can tell the tracks apart.
        audio_track = None
        is_audio_only = (fmt.get("type") or "").startswith("audio/")
        track = fmt.get("audioTrack") or {}
        xtags = _xtags_from_url(original_url) if is_audio_only else {}
        if track or (is_audio_only and xtags):
            display_name = _enrich_audio_display_name(track.get("displayName"), xtags)
            is_default = track.get("isDefault", False) or xtags.get("acont") == "original"
            track_id = track.get("id") or xtags.get("lang")
            audio_track = AudioTrack(id=track_id, displayName=display_name, isDefault=is_default)

        adaptive_formats.append(
            AdaptiveFormat(
                url=url,
                itag=str(itag),
                type=fmt.get("type", ""),
                container=fmt.get("container", ""),
                init=fmt.get("init"),
                index=fmt.get("index"),
                resolution=fmt.get("resolution"),
                width=fmt.get("width"),
                height=fmt.get("height"),
                bitrate=fmt.get("bitrate"),
                clen=fmt.get("clen"),
                encoding=fmt.get("encoding"),
                fps=fmt.get("fps"),
                audioTrack=audio_track,
                audioQuality=fmt.get("audioQuality"),
                httpHeaders=_filter_sensitive_headers(fmt.get("httpHeaders")),
            )
        )

    # Convert captions to new /content?lang= format for yt-dlp backend
    # Invidious URLs like ?label=English need to be converted to /content?lang=en
    captions = []
    for cap in info.get("captions", []):
        label = cap.get("label", "")
        lang_code = cap.get("languageCode", "")
        is_auto = "(auto-generated)" in label.lower() or "(auto)" in label.lower()

        # If no language code, try to extract from label
        if not lang_code:
            lang_code = _label_to_lang_code(label)

        # For non-auto captions, check if label has region info to construct full locale
        # Invidious returns "en" for both "English (auto-generated)" and "English (United States)"
        # but yt-dlp needs "en-US" for the manual caption to be found
        if lang_code and not is_auto:
            region = _extract_region_from_label(label)
            if region:
                lang_code = f"{lang_code}-{region}"

        if lang_code:
            # Build new-style URL for yt-dlp caption endpoint
            url = f"{base_url}/api/v1/captions/{video_id}/content?lang={lang_code}"
            if is_auto:
                url += "&auto=true"
            if caption_token:
                url += f"&token={caption_token}"
        else:
            # Fallback to original URL if we can't determine language
            original_url = cap.get("url", "")
            url = f"{base_url}{original_url}" if original_url.startswith("/") else original_url

        captions.append(Caption(label=label, languageCode=lang_code, url=url, auto_generated=is_auto))

    # Convert storyboards (resolve relative URLs to Invidious instance)
    storyboards = []
    for sb in info.get("storyboards", []):
        # Resolve relative storyboard URLs (Invidious may return paths like /api/v1/storyboards/...)
        storyboard_url = resolve_invidious_url(sb.get("url", ""), invidious_base_url)
        template_url = resolve_invidious_url(sb.get("templateUrl", ""), invidious_base_url)

        storyboards.append(
            Storyboard(
                url=storyboard_url,
                templateUrl=template_url,
                width=sb.get("width", 0),
                height=sb.get("height", 0),
                count=sb.get("count", 0),
                interval=sb.get("interval", 0),
                storyboardWidth=sb.get("storyboardWidth", 0),
                storyboardHeight=sb.get("storyboardHeight", 0),
                storyboardCount=sb.get("storyboardCount", 0),
            )
        )

    # Resolve other potentially relative URLs
    author_url = info.get("authorUrl")
    if author_url:
        author_url = resolve_invidious_url(author_url, invidious_base_url)

    hls_url = info.get("hlsUrl")
    if hls_url:
        if effective_proxy_mode == "relay" and base_url:
            from routers.proxy import signed_relay_url

            hls_url = signed_relay_url(
                base_url,
                resolve_invidious_url(hls_url, invidious_base_url),
                content_type="application/vnd.apple.mpegurl",
            )
        else:
            hls_url = resolve_invidious_url(hls_url, invidious_base_url)

    dash_url = info.get("dashUrl")
    if dash_url:
        # DASH manifests aren't body-rewritten yet (see _relay.py); keep
        # passthrough behavior so the iOS client still gets a usable URL.
        # When proxy_mode=relay is on we still wrap so the manifest fetch at
        # least goes via the server (segment IPs may still mismatch).
        if effective_proxy_mode == "relay" and base_url:
            from routers.proxy import signed_relay_url

            dash_url = signed_relay_url(
                base_url,
                resolve_invidious_url(dash_url, invidious_base_url),
                content_type="application/dash+xml",
            )
        else:
            dash_url = resolve_invidious_url(dash_url, invidious_base_url)

    # Convert recommended videos if present
    recommended_videos = None
    if info.get("recommendedVideos"):
        recommended_videos = []
        for rec in info.get("recommendedVideos", []):
            try:
                recommended_videos.append(invidious_to_video_list_item(rec, invidious_base_url))
            except (KeyError, TypeError, ValueError) as e:
                logging.error(f"Failed to convert recommended video: {e}, data: {rec}")
                continue  # Skip any malformed entries

    return VideoResponse(
        videoId=video_id,
        title=info.get("title", ""),
        description=info.get("description"),
        descriptionHtml=info.get("descriptionHtml"),
        author=info.get("author", ""),
        authorId=info.get("authorId", ""),
        authorUrl=author_url,
        authorThumbnails=author_thumbnails if author_thumbnails else None,
        subCountText=info.get("subCountText"),
        lengthSeconds=int(info.get("lengthSeconds") or 0),
        published=info.get("published"),
        publishedText=info.get("publishedText"),
        viewCount=info.get("viewCount"),
        likeCount=info.get("likeCount"),
        videoThumbnails=video_thumbnails,
        liveNow=info.get("liveNow", False),
        isUpcoming=info.get("isUpcoming", False),
        isShort=info.get("isShort"),
        premiereTimestamp=info.get("premiereTimestamp"),
        hlsUrl=hls_url,
        dashUrl=dash_url,
        formatStreams=format_streams,
        adaptiveFormats=adaptive_formats,
        captions=captions,
        storyboards=storyboards,
        recommendedVideos=recommended_videos,
    )


def invidious_to_video_list_item(info: dict, invidious_base_url: str = "") -> VideoListItem:
    """Convert Invidious API response to VideoListItem.

    Invidious already returns data in our target format, so this is mostly passthrough.
    Resolves relative thumbnail URLs to absolute URLs using the Invidious instance base URL.

    Args:
        info: Invidious video data dict
        invidious_base_url: Base URL of the Invidious instance for resolving relative URLs
    """
    # Convert thumbnails if present, resolving relative URLs
    thumbnails = []
    for thumb in info.get("videoThumbnails", []):
        thumbnails.append(
            Thumbnail(
                quality=thumb.get("quality", "default"),
                url=resolve_invidious_url(thumb.get("url", ""), invidious_base_url),
                width=thumb.get("width"),
                height=thumb.get("height"),
            )
        )

    # Resolve author URL if relative
    author_url = info.get("authorUrl")
    if author_url:
        author_url = resolve_invidious_url(author_url, invidious_base_url)

    # Handle published field - can be int (Unix timestamp) or ISO 8601 string
    # Minimum valid timestamp: Jan 1, 2005 (before YouTube existed)
    MIN_VALID_TIMESTAMP = 1104537600

    published = info.get("published")
    if isinstance(published, str):
        try:
            published = int(datetime.fromisoformat(published.replace("Z", "+00:00")).timestamp())
        except (ValueError, TypeError):
            published = None

    # Validate timestamp - reject epoch/invalid values that cause "56 years ago"
    if published is not None and published <= MIN_VALID_TIMESTAMP:
        published = None

    # InnerTube listings only carry relative text ("2 days ago") - derive an
    # approximate timestamp from it when upstream sent no published value at
    # all. If an explicit value was sent but rejected as garbage, the text is
    # not trusted either.
    if published is None and info.get("published") is None:
        published = parse_relative_time(info.get("publishedText"))
        if published is not None and published <= MIN_VALID_TIMESTAMP:
            published = None

    # Only use publishedText if published is valid (avoid "56 years ago" from bad data)
    published_text = info.get("publishedText") if published else None

    return VideoListItem(
        videoId=info.get("videoId", ""),
        title=info.get("title", ""),
        description=info.get("description"),
        author=info.get("author", ""),
        authorId=info.get("authorId", ""),
        authorUrl=author_url,
        lengthSeconds=int(info.get("lengthSeconds") or 0),
        published=published,
        publishedText=published_text,
        viewCount=info.get("viewCount"),
        viewCountText=info.get("viewCountText"),
        likeCount=info.get("likeCount"),
        videoThumbnails=thumbnails,
        liveNow=info.get("liveNow", False),
        isUpcoming=info.get("isUpcoming", False),
        isShort=info.get("isShort"),
    )


def invidious_to_channel_list_item(info: dict, invidious_base_url: str = "") -> ChannelListItem:
    """Convert Invidious API channel search result to ChannelListItem.

    Resolves relative thumbnail URLs to absolute URLs using the Invidious instance base URL.

    Args:
        info: Invidious channel data dict
        invidious_base_url: Base URL of the Invidious instance for resolving relative URLs
    """
    thumbnails = []
    for thumb in info.get("authorThumbnails", []):
        thumbnails.append(
            Thumbnail(
                quality=thumb.get("quality", "default"),
                url=resolve_invidious_url(thumb.get("url", ""), invidious_base_url),
                width=thumb.get("width"),
                height=thumb.get("height"),
            )
        )

    return ChannelListItem(
        authorId=info.get("authorId", ""),
        author=info.get("author", ""),
        channelHandle=info.get("channelHandle"),
        description=info.get("description"),
        subCount=info.get("subCount"),
        subCountText=info.get("subCountText"),
        videoCount=info.get("videoCount"),
        authorThumbnails=thumbnails,
        authorVerified=info.get("authorVerified", False),
    )


def invidious_to_playlist_list_item(info: dict, invidious_base_url: str = "") -> PlaylistListItem:
    """Convert Invidious API playlist search result to PlaylistListItem.

    Resolves relative thumbnail URLs to absolute URLs using the Invidious instance base URL.

    Args:
        info: Invidious playlist data dict
        invidious_base_url: Base URL of the Invidious instance for resolving relative URLs
    """
    videos = []
    for video in info.get("videos", []):
        videos.append(invidious_to_video_list_item(video, invidious_base_url))

    # Resolve playlist thumbnail URL if present
    playlist_thumbnail = info.get("playlistThumbnail")
    if playlist_thumbnail:
        playlist_thumbnail = resolve_invidious_url(playlist_thumbnail, invidious_base_url)

    return PlaylistListItem(
        playlistId=info.get("playlistId", ""),
        title=info.get("title", ""),
        author=info.get("author"),
        authorId=info.get("authorId"),
        videoCount=info.get("videoCount") or 0,
        playlistThumbnail=playlist_thumbnail,
        videos=videos,
    )


def invidious_to_playlist_response(info: dict, invidious_base_url: str = "") -> PlaylistResponse:
    """Convert Invidious API playlist response to PlaylistResponse.

    Invidious /api/v1/playlists/{id} returns:
    {
        "playlistId": "...",
        "title": "...",
        "description": "...",
        "author": "...",
        "authorId": "...",
        "videoCount": 123,
        "videos": [...]
    }

    Args:
        info: Invidious playlist data dict
        invidious_base_url: Base URL of the Invidious instance for resolving relative URLs
    """
    videos = []
    for video in info.get("videos", []):
        videos.append(invidious_to_video_list_item(video, invidious_base_url))

    return PlaylistResponse(
        playlistId=info.get("playlistId", ""),
        title=info.get("title", ""),
        description=info.get("description"),
        author=info.get("author"),
        authorId=info.get("authorId"),
        videoCount=info.get("videoCount", 0),
        videos=videos,
    )
