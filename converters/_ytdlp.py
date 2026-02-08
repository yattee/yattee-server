"""yt-dlp to model conversions and author/channel URL helpers."""

import urllib.parse
from typing import Optional

from converters._captions import convert_captions
from converters._formats import convert_formats, convert_thumbnails
from converters._formatting import (
    format_published_text,
    format_subscriber_count,
    format_view_count,
    get_valid_timestamp,
    parse_upload_date,
)
from models import (
    PlaylistListItem,
    Thumbnail,
    VideoListItem,
    VideoResponse,
)


def get_author_thumbnail_url(info: dict) -> Optional[str]:
    """Extract author/channel thumbnail URL from video info."""
    # yt-dlp sometimes includes channel thumbnail in the thumbnails array
    thumbnails = info.get("thumbnails", [])
    for thumb in thumbnails:
        url = thumb.get("url", "")
        # YouTube channel avatars contain yt3.ggpht.com or ytimg.com with /a-/
        if "yt3.ggpht.com" in url or "/a-/" in url:
            return url
    return None


def construct_author_url(
    extractor: Optional[str], author_id: Optional[str], original_url: Optional[str]
) -> Optional[str]:
    """Construct author/channel URL when yt-dlp doesn't provide one.

    Many extractors don't provide channel_url or uploader_url directly,
    so we need to construct them based on the site's URL pattern.
    """
    if not author_id:
        return None

    extractor_lower = (extractor or "").lower()

    # Map extractors to their channel URL patterns
    url_patterns = {
        "dailymotion": f"https://www.dailymotion.com/{author_id}",
        "vimeo": f"https://vimeo.com/{author_id}",
        "soundcloud": f"https://soundcloud.com/{author_id}",
        "tiktok": f"https://www.tiktok.com/@{author_id}",
        "instagram": f"https://www.instagram.com/{author_id}",
        "facebook": f"https://www.facebook.com/{author_id}",
        "twitch": f"https://www.twitch.tv/{author_id}",
        "bilibili": f"https://space.bilibili.com/{author_id}",
        "niconico": f"https://www.nicovideo.jp/user/{author_id}",
        "rutube": f"https://rutube.ru/channel/{author_id}",
        "peertube": None,  # PeerTube needs instance URL, handled separately
    }

    # Check for known extractors
    for extractor_name, pattern in url_patterns.items():
        if extractor_lower.startswith(extractor_name):
            return pattern

    # For unknown extractors, try to construct from original URL's domain
    if original_url:
        try:
            parsed = urllib.parse.urlparse(original_url)
            # Construct base channel URL from domain
            return f"{parsed.scheme}://{parsed.netloc}/{author_id}"
        except ValueError:
            pass

    return None


def ytdlp_to_video_response(
    info: dict, base_url: str = "", proxy_streams: bool = False, original_url: str = "", user_id: Optional[int] = None
) -> VideoResponse:
    """Convert yt-dlp video info to Invidious VideoResponse.

    Args:
        info: yt-dlp video info dict
        base_url: Base URL for caption URLs
        proxy_streams: If True, stream URLs will point to /proxy/fast/{video_id}?itag=X
                      for faster downloads through the server. If False, uses direct YouTube URLs.
        original_url: Override URL for re-extraction (used for external sites)
    """
    video_id = info.get("id", "")

    # Get original URL for external sites (parameter overrides info dict)
    if not original_url:
        original_url = info.get("original_url") or info.get("webpage_url") or ""

    # Build proxy base URL if proxy mode enabled
    proxy_base_url = f"{base_url}/proxy" if proxy_streams and base_url else ""

    format_streams, adaptive_formats = convert_formats(
        info.get("formats"),
        video_id=video_id,
        proxy_base_url=proxy_base_url,
        original_url=original_url if proxy_streams else "",
        user_id=user_id,
    )

    # Get subscriber count and format it
    sub_count = info.get("channel_follower_count")
    sub_count_text = format_subscriber_count(sub_count)

    # Try to get author thumbnail
    author_thumb_url = get_author_thumbnail_url(info)
    author_thumbnails = None
    if author_thumb_url:
        author_thumbnails = [Thumbnail(quality="default", url=author_thumb_url, width=88, height=88)]

    # Get extractor info for external sites
    extractor = info.get("extractor") or info.get("extractor_key")
    original_url = info.get("original_url") or info.get("webpage_url")

    # Get or construct author URL
    author_id = info.get("channel_id") or info.get("uploader_id") or ""
    author_url = info.get("channel_url") or info.get("uploader_url")
    if not author_url and author_id:
        author_url = construct_author_url(extractor, author_id, original_url)

    return VideoResponse(
        videoId=video_id,
        title=info.get("title", ""),
        description=info.get("description"),
        descriptionHtml=info.get("description"),  # yt-dlp doesn't provide HTML
        author=info.get("uploader") or info.get("channel") or "",
        authorId=author_id,
        authorUrl=author_url,
        authorThumbnails=author_thumbnails,
        subCountText=sub_count_text,
        lengthSeconds=int(info.get("duration") or 0),
        published=parse_upload_date(info.get("upload_date")),
        publishedText=format_published_text(info.get("upload_date")),
        viewCount=info.get("view_count"),
        likeCount=info.get("like_count"),
        videoThumbnails=convert_thumbnails(info.get("thumbnails")),
        liveNow=info.get("is_live") or False,
        isUpcoming=info.get("is_upcoming") or False,
        hlsUrl=info.get("manifest_url") if info.get("is_live") else None,
        formatStreams=format_streams,
        adaptiveFormats=adaptive_formats,
        captions=convert_captions(info.get("subtitles"), info.get("automatic_captions"), video_id, base_url, user_id),
        extractor=extractor,
        originalUrl=original_url,
    )


def ytdlp_to_video_list_item(info: dict) -> VideoListItem:
    """Convert yt-dlp video info to VideoListItem for lists.

    Note: When using --flat-playlist, channel info is under playlist_* fields.
    """
    # Channel info: prefer direct fields, fall back to playlist_* fields (used in flat-playlist mode)
    author = (
        info.get("uploader")
        or info.get("channel")
        or info.get("playlist_uploader")
        or info.get("playlist_channel")
        or ""
    )
    author_id = (
        info.get("channel_id")
        or info.get("uploader_id")
        or info.get("playlist_channel_id")
        or info.get("playlist_uploader_id")
        or ""
    )
    author_url = (
        info.get("channel_url")
        or info.get("uploader_url")
        or info.get("playlist_channel_url")
        or info.get("playlist_uploader_url")
    )

    # Handle timestamp: prefer upload_date, fall back to timestamp/release_timestamp
    upload_date = info.get("upload_date")
    published = (
        parse_upload_date(upload_date) if upload_date else get_valid_timestamp(info)
    )
    published_text = format_published_text(upload_date) if upload_date else None

    # Get extractor name for external sites (use nice name from extractor_key)
    extractor = info.get("extractor_key") or info.get("extractor")

    # Construct author URL if not provided
    original_url = info.get("original_url") or info.get("webpage_url") or info.get("url")
    if not author_url and author_id:
        author_url = construct_author_url(extractor, author_id, original_url)

    # Get the original video URL for external videos
    video_url = info.get("webpage_url") or info.get("original_url") or info.get("url")

    return VideoListItem(
        videoId=info.get("id", ""),
        title=info.get("title", ""),
        description=info.get("description"),
        author=author,
        authorId=author_id,
        authorUrl=author_url,
        lengthSeconds=int(info.get("duration") or 0),
        published=published,
        publishedText=published_text,
        viewCount=info.get("view_count"),
        viewCountText=format_view_count(info.get("view_count")),
        likeCount=info.get("like_count"),
        videoThumbnails=convert_thumbnails(info.get("thumbnails")),
        liveNow=info.get("is_live", False) or info.get("live_status") == "is_live",
        isUpcoming=info.get("is_upcoming", False) or info.get("live_status") == "is_upcoming",
        extractor=extractor,
        videoUrl=video_url,
    )


def ytdlp_to_playlist_list_item(info: dict) -> PlaylistListItem:
    """Convert yt-dlp playlist info (from channel playlists tab) to PlaylistListItem.

    yt-dlp returns playlist entries with format like:
    {
        "id": "PL8mG-RkN2uTxRRAvbc1C3yyP1ny4zE9K8",
        "title": "Big Displays",
        "thumbnails": [...],
        "playlist_count": 178,
        "playlist_uploader": "Linus Tech Tips",
        "playlist_uploader_id": "@LinusTechTips",
        "playlist_channel_id": "UCXuqSBlHAE6Xw-yeJA0Tunw",
        ...
    }
    """
    # Get thumbnail URL from first thumbnail if available
    thumbnails = info.get("thumbnails", [])
    thumbnail_url = thumbnails[0].get("url") if thumbnails else None

    return PlaylistListItem(
        playlistId=info.get("id", ""),
        title=info.get("title", ""),
        author=info.get("playlist_uploader") or info.get("playlist_channel"),
        authorId=info.get("playlist_channel_id") or info.get("playlist_uploader_id"),
        videoCount=info.get("playlist_count", 0),
        playlistThumbnail=thumbnail_url,
        videos=[],  # yt-dlp flat-playlist doesn't include video details
    )
