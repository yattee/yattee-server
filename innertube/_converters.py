"""Convert InnerTube response structures to Invidious-compatible dicts.

These converters produce dicts in the same shape as the Invidious API,
so the existing `invidious_to_video_list_item()` etc. converters can be reused.
"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("innertube")


def _extract_text(obj: Any) -> str:
    """Extract plain text from InnerTube text objects."""
    if not obj:
        return ""
    if isinstance(obj, str):
        return obj
    if "simpleText" in obj:
        return obj["simpleText"]
    if "runs" in obj:
        return "".join(run.get("text", "") for run in obj["runs"])
    return ""


def _extract_thumbnails(obj: Any) -> List[Dict[str, Any]]:
    """Extract thumbnails from InnerTube thumbnail container."""
    if not obj:
        return []
    thumbs = obj.get("thumbnails", [])
    return [
        {
            "quality": _thumbnail_quality(t.get("width", 0)),
            "url": t.get("url", ""),
            "width": t.get("width"),
            "height": t.get("height"),
        }
        for t in thumbs
    ]


def _thumbnail_quality(width: int) -> str:
    """Map thumbnail width to quality label."""
    if width >= 1280:
        return "maxres"
    if width >= 640:
        return "sddefault"
    if width >= 480:
        return "high"
    if width >= 320:
        return "medium"
    return "default"


_STANDARD_THUMBNAILS = [
    ("default.jpg", "default", 120, 90),
    ("mqdefault.jpg", "medium", 320, 180),
    ("hqdefault.jpg", "high", 480, 360),
    ("sddefault.jpg", "sddefault", 640, 480),
    ("maxresdefault.jpg", "maxres", 1280, 720),
]


def _standard_video_thumbnails(video_id: str) -> List[Dict[str, Any]]:
    """Generate standard YouTube thumbnail entries for a video ID."""
    if not video_id:
        return []
    return [
        {"quality": quality, "url": f"https://i.ytimg.com/vi/{video_id}/{filename}", "width": width, "height": height}
        for filename, quality, width, height in _STANDARD_THUMBNAILS
    ]


def _parse_count_text(text: str) -> Optional[int]:
    """Parse a count string like '1.2K views', '3M subscribers' to an integer."""
    if not text:
        return None
    text = text.strip().upper().replace(",", "")
    # Remove trailing words like "views", "subscribers"
    parts = text.split()
    if not parts:
        return None
    num_part = parts[0]

    multipliers = {"K": 1_000, "M": 1_000_000, "B": 1_000_000_000}
    for suffix, mult in multipliers.items():
        if num_part.endswith(suffix):
            try:
                return int(float(num_part[:-1]) * mult)
            except ValueError:
                return None
    try:
        return int(num_part)
    except ValueError:
        return None


def _parse_duration_text(text: str) -> int:
    """Parse duration text like '12:34' or '1:23:45' to seconds."""
    if not text:
        return 0
    parts = text.strip().split(":")
    try:
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        if len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
        if len(parts) == 1:
            return int(parts[0])
    except ValueError:
        pass
    return 0


def video_renderer_to_invidious(renderer: Dict[str, Any]) -> Dict[str, Any]:
    """Convert an InnerTube videoRenderer to Invidious video dict format.

    The output dict can be passed to `invidious_to_video_list_item()`.
    """
    video_id = renderer.get("videoId", "")
    title = _extract_text(renderer.get("title"))

    # Author info
    channel = renderer.get("ownerText") or renderer.get("longBylineText") or renderer.get("shortBylineText", {})
    author = _extract_text(channel)
    author_id = ""
    author_url = ""
    if "runs" in channel:
        for run in channel["runs"]:
            nav = run.get("navigationEndpoint", {})
            browse = nav.get("browseEndpoint", {})
            if browse.get("browseId"):
                author_id = browse["browseId"]
                author_url = f"/channel/{author_id}"
                break

    # Thumbnails – use well-known YouTube CDN URLs for full quality range
    thumbnails = _standard_video_thumbnails(video_id)

    # Duration
    length_text = _extract_text(renderer.get("lengthText"))
    length_seconds = _parse_duration_text(length_text)

    # For accessibility-based duration (more reliable)
    if not length_seconds:
        accessibility = renderer.get("lengthText", {}).get("accessibility", {}).get("accessibilityData", {})
        duration_label = accessibility.get("label", "")
        # Parse "12 minutes, 34 seconds" format
        length_seconds = _parse_accessibility_duration(duration_label)

    # View count
    view_count_text = _extract_text(renderer.get("viewCountText"))
    view_count = _parse_count_text(view_count_text)

    # Published time
    published_text = _extract_text(renderer.get("publishedTimeText"))

    # Live status
    badges = renderer.get("badges", [])
    is_live = False
    for badge in badges:
        badge_renderer = badge.get("metadataBadgeRenderer", {})
        if badge_renderer.get("style") in ("BADGE_STYLE_TYPE_LIVE_NOW", "BADGE_STYLE_TYPE_LIVE_NOW_DEFAULT"):
            is_live = True
            break

    # Also check thumbnailOverlays for live status
    for overlay in renderer.get("thumbnailOverlays", []):
        status = overlay.get("thumbnailOverlayTimeStatusRenderer", {})
        if status.get("style") == "LIVE":
            is_live = True
            break

    # Description snippet
    description = _extract_text(renderer.get("descriptionSnippet") or renderer.get("detailedMetadataSnippets", [{}]))

    return {
        "type": "video",
        "videoId": video_id,
        "title": title,
        "description": description,
        "author": author,
        "authorId": author_id,
        "authorUrl": author_url,
        "videoThumbnails": thumbnails,
        "lengthSeconds": length_seconds,
        "viewCount": view_count,
        "viewCountText": view_count_text,
        "published": None,
        "publishedText": published_text,
        "liveNow": is_live,
        "isUpcoming": False,
    }


def _parse_accessibility_duration(label: str) -> int:
    """Parse accessibility duration label like '12 minutes, 34 seconds'."""
    if not label:
        return 0
    total = 0
    parts = label.lower().replace(",", "").split()
    i = 0
    while i < len(parts) - 1:
        try:
            num = int(parts[i])
            unit = parts[i + 1]
            if "hour" in unit:
                total += num * 3600
            elif "minute" in unit:
                total += num * 60
            elif "second" in unit:
                total += num
            i += 2
        except (ValueError, IndexError):
            i += 1
    return total


def playlist_renderer_to_invidious(renderer: Dict[str, Any]) -> Dict[str, Any]:
    """Convert an InnerTube playlistRenderer to Invidious playlist dict format."""
    playlist_id = renderer.get("playlistId", "")
    title = _extract_text(renderer.get("title"))

    # Author
    channel = renderer.get("longBylineText") or renderer.get("shortBylineText", {})
    author = _extract_text(channel)
    author_id = ""
    if "runs" in channel:
        for run in channel["runs"]:
            browse = run.get("navigationEndpoint", {}).get("browseEndpoint", {})
            if browse.get("browseId"):
                author_id = browse["browseId"]
                break

    # Video count
    video_count_text = _extract_text(renderer.get("videoCount") or renderer.get("videoCountText"))
    video_count = 0
    if video_count_text:
        try:
            video_count = int(video_count_text.replace(",", "").split()[0])
        except (ValueError, IndexError):
            pass

    # Thumbnail
    thumbnails = _extract_thumbnails(renderer.get("thumbnail") or renderer.get("thumbnails"))
    playlist_thumbnail = thumbnails[0]["url"] if thumbnails else None

    return {
        "type": "playlist",
        "playlistId": playlist_id,
        "title": title,
        "author": author,
        "authorId": author_id,
        "videoCount": video_count,
        "playlistThumbnail": playlist_thumbnail,
        "videos": [],
    }


def lockup_view_model_to_invidious(renderer: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Convert an InnerTube lockupViewModel to Invidious format.

    YouTube uses lockupViewModel for playlist (and sometimes channel) results
    in search instead of the older playlistRenderer/channelRenderer.
    """
    content_type = renderer.get("contentType", "")
    content_id = renderer.get("contentId", "")

    if not content_id:
        return None

    # Extract title
    title = (
        renderer.get("metadata", {})
        .get("lockupMetadataViewModel", {})
        .get("title", {})
        .get("content", "")
    )

    # Extract metadata rows for author info
    metadata_rows = (
        renderer.get("metadata", {})
        .get("lockupMetadataViewModel", {})
        .get("metadata", {})
        .get("contentMetadataViewModel", {})
        .get("metadataRows", [])
    )

    author = ""
    author_id = ""
    for row in metadata_rows:
        for part in row.get("metadataParts", []):
            text_obj = part.get("text", {})
            for cmd_run in text_obj.get("commandRuns", []):
                browse = (
                    cmd_run.get("onTap", {})
                    .get("innertubeCommand", {})
                    .get("browseEndpoint", {})
                )
                if browse.get("browseId") and not author_id:
                    author = text_obj.get("content", "")
                    author_id = browse["browseId"]
                    break
            if author_id:
                break
        if author_id:
            break

    if content_type == "LOCKUP_CONTENT_TYPE_PLAYLIST":
        # Extract video count from thumbnail badge
        video_count = 0
        badges = (
            renderer.get("contentImage", {})
            .get("collectionThumbnailViewModel", {})
            .get("primaryThumbnail", {})
            .get("thumbnailViewModel", {})
            .get("overlays", [])
        )
        for overlay in badges:
            badge_vm = overlay.get("thumbnailOverlayBadgeViewModel", {})
            for badge in badge_vm.get("thumbnailBadges", []):
                badge_text = badge.get("thumbnailBadgeViewModel", {}).get("text", "")
                if badge_text:
                    try:
                        video_count = int(badge_text.replace(",", "").split()[0])
                    except (ValueError, IndexError):
                        pass

        # Extract thumbnail
        thumb_sources = (
            renderer.get("contentImage", {})
            .get("collectionThumbnailViewModel", {})
            .get("primaryThumbnail", {})
            .get("thumbnailViewModel", {})
            .get("image", {})
            .get("sources", [])
        )
        playlist_thumbnail = thumb_sources[0].get("url", "") if thumb_sources else None

        return {
            "type": "playlist",
            "playlistId": content_id,
            "title": title,
            "author": author,
            "authorId": author_id,
            "videoCount": video_count,
            "playlistThumbnail": playlist_thumbnail,
            "videos": [],
        }

    if content_type == "LOCKUP_CONTENT_TYPE_CHANNEL":
        return {
            "type": "channel",
            "authorId": content_id,
            "author": title,
            "description": "",
            "subCount": None,
            "subCountText": "",
            "videoCount": None,
            "authorThumbnails": [],
            "authorVerified": False,
        }

    return None


def channel_renderer_to_invidious(renderer: Dict[str, Any]) -> Dict[str, Any]:
    """Convert an InnerTube channelRenderer to Invidious channel dict format."""
    channel_id = renderer.get("channelId", "")
    title = _extract_text(renderer.get("title"))
    description = _extract_text(renderer.get("descriptionSnippet"))

    # Subscriber count
    sub_count_text = _extract_text(renderer.get("subscriberCountText"))
    sub_count = _parse_count_text(sub_count_text)

    # Video count
    video_count_text = _extract_text(renderer.get("videoCountText"))
    video_count = _parse_count_text(video_count_text)

    # Thumbnails
    thumbnails = _extract_thumbnails(renderer.get("thumbnail"))

    # Verified badge
    verified = False
    for badge in renderer.get("ownerBadges", []):
        if badge.get("metadataBadgeRenderer", {}).get("style") == "BADGE_STYLE_TYPE_VERIFIED":
            verified = True
            break

    return {
        "type": "channel",
        "authorId": channel_id,
        "author": title,
        "description": description,
        "subCount": sub_count,
        "subCountText": sub_count_text,
        "videoCount": video_count,
        "authorThumbnails": thumbnails,
        "authorVerified": verified,
    }


def rich_item_to_invidious(item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Convert an InnerTube richItemRenderer to Invidious format.

    richItemRenderer wraps a videoRenderer (used in trending, channel pages).
    """
    content = item.get("content", {})
    if "videoRenderer" in content:
        return video_renderer_to_invidious(content["videoRenderer"])
    if "reelItemRenderer" in content:
        return _reel_item_to_invidious(content["reelItemRenderer"])
    return None


def _reel_item_to_invidious(renderer: Dict[str, Any]) -> Dict[str, Any]:
    """Convert a reelItemRenderer (shorts) to Invidious video format."""
    video_id = renderer.get("videoId", "")
    title = _extract_text(renderer.get("headline"))
    thumbnails = _standard_video_thumbnails(video_id)
    view_count_text = _extract_text(renderer.get("viewCountText"))

    return {
        "type": "video",
        "videoId": video_id,
        "title": title,
        "description": "",
        "author": "",
        "authorId": "",
        "authorUrl": "",
        "videoThumbnails": thumbnails,
        "lengthSeconds": 0,
        "viewCount": _parse_count_text(view_count_text),
        "viewCountText": view_count_text,
        "published": None,
        "publishedText": None,
        "liveNow": False,
        "isUpcoming": False,
    }


def grid_video_to_invidious(renderer: Dict[str, Any]) -> Dict[str, Any]:
    """Convert a gridVideoRenderer to Invidious video format.

    Used in channel video tabs.
    """
    video_id = renderer.get("videoId", "")
    title = _extract_text(renderer.get("title"))
    thumbnails = _standard_video_thumbnails(video_id)
    published_text = _extract_text(renderer.get("publishedTimeText"))
    view_count_text = _extract_text(renderer.get("viewCountText"))

    # Get duration from thumbnail overlay
    length_seconds = 0
    for overlay in renderer.get("thumbnailOverlays", []):
        time_status = overlay.get("thumbnailOverlayTimeStatusRenderer", {})
        length_seconds = _parse_duration_text(_extract_text(time_status.get("text")))
        if length_seconds:
            break

    return {
        "type": "video",
        "videoId": video_id,
        "title": title,
        "description": "",
        "author": "",
        "authorId": "",
        "authorUrl": "",
        "videoThumbnails": thumbnails,
        "lengthSeconds": length_seconds,
        "viewCount": _parse_count_text(view_count_text),
        "viewCountText": view_count_text,
        "published": None,
        "publishedText": published_text,
        "liveNow": False,
        "isUpcoming": False,
    }


def grid_playlist_to_invidious(renderer: Dict[str, Any]) -> Dict[str, Any]:
    """Convert a gridPlaylistRenderer to Invidious playlist format."""
    playlist_id = renderer.get("playlistId", "")
    title = _extract_text(renderer.get("title"))
    thumbnails = _extract_thumbnails(renderer.get("thumbnail"))

    video_count_text = _extract_text(renderer.get("videoCountText") or renderer.get("videoCountShortText"))
    video_count = 0
    if video_count_text:
        try:
            video_count = int(video_count_text.replace(",", "").split()[0])
        except (ValueError, IndexError):
            pass

    return {
        "type": "playlist",
        "playlistId": playlist_id,
        "title": title,
        "author": "",
        "authorId": "",
        "videoCount": video_count,
        "playlistThumbnail": thumbnails[0]["url"] if thumbnails else None,
        "videos": [],
    }
