"""InnerTube playlist endpoint – fetch playlist metadata and videos.

Uses YouTube's InnerTube /browse endpoint with browseId="VL<playlist_id>" to
retrieve a playlist. Auto-paginates through continuation tokens until the
playlist is exhausted.
"""

import logging
from typing import Any, Dict, List, Optional

from innertube._client import InnerTubeError, innertube_post
from innertube._converters import (
    _extract_text,
    _parse_count_text,
    lockup_view_model_to_invidious,
    playlist_video_renderer_to_invidious,
)

logger = logging.getLogger("innertube")

# Safety caps so a broken continuation loop can't hang the process.
_MAX_PAGES = 50
_MAX_VIDEOS = 5000


async def get_playlist(playlist_id: str) -> Optional[Dict[str, Any]]:
    """Fetch playlist metadata and all videos via InnerTube.

    Returns an Invidious-compatible dict so converters.invidious_to_playlist_response
    can be reused. Returns None when the playlist is empty/not found. Raises
    InnerTubeError for HTTP/API failures so the caller can fall through to Invidious
    or yt-dlp.
    """
    browse_id = playlist_id if playlist_id.startswith("VL") else f"VL{playlist_id}"
    body: Dict[str, Any] = {"browseId": browse_id}

    try:
        data = await innertube_post("browse", body, use_cookies=True)
    except InnerTubeError:
        raise

    try:
        metadata = _extract_metadata(data)
        videos, continuation = _extract_playlist_videos(data)
    except (KeyError, TypeError, IndexError) as e:
        logger.warning(f"[InnerTube] Failed to parse playlist {playlist_id}: {e}")
        return None

    # Follow continuation tokens until the playlist is exhausted or we hit a cap.
    pages = 1
    while continuation and pages < _MAX_PAGES and len(videos) < _MAX_VIDEOS:
        try:
            cont_data = await innertube_post("browse", {"continuation": continuation}, use_cookies=True)
        except InnerTubeError as e:
            logger.info(f"[InnerTube] Playlist {playlist_id} continuation failed after {pages} pages: {e}")
            break

        try:
            more_videos, continuation = _extract_continuation_videos(cont_data)
        except (KeyError, TypeError, IndexError) as e:
            logger.warning(f"[InnerTube] Playlist {playlist_id} continuation parse failed: {e}")
            break

        if not more_videos:
            break
        videos.extend(more_videos)
        pages += 1

    if pages >= _MAX_PAGES or len(videos) >= _MAX_VIDEOS:
        logger.warning(
            f"[InnerTube] Playlist {playlist_id} hit pagination cap ({pages} pages, {len(videos)} videos)"
        )

    # If we have neither metadata nor videos, treat as "not found" and fall through.
    if not metadata.get("title") and not videos:
        return None

    video_count = metadata.get("videoCount") or len(videos)

    return {
        "playlistId": playlist_id,
        "title": metadata.get("title", ""),
        "description": metadata.get("description"),
        "author": metadata.get("author"),
        "authorId": metadata.get("authorId"),
        "videoCount": video_count,
        "videos": videos,
    }


def _extract_metadata(data: Dict[str, Any]) -> Dict[str, Any]:
    """Extract title/description/author/videoCount from a playlist browse response.

    Walks several renderer shapes in order; later passes only fill fields that
    earlier passes missed.
    """
    result: Dict[str, Any] = {}

    header = data.get("header", {})

    # 1) Legacy playlistHeaderRenderer
    phr = header.get("playlistHeaderRenderer")
    if phr:
        _merge(result, "title", _extract_text(phr.get("title")))
        _merge(result, "description", _extract_text(phr.get("descriptionText")) or None)
        owner = phr.get("ownerText", {})
        _merge(result, "author", _extract_text(owner))
        _merge(result, "authorId", _browse_id_from_runs(owner))
        num_text = _extract_text(phr.get("numVideosText")) or _first_stat_text(phr.get("stats"))
        count = _parse_count_text(num_text) if num_text else None
        if count is not None:
            _merge(result, "videoCount", count)

    # 2) Sidebar renderer (older non-header layouts)
    sidebar_items = data.get("sidebar", {}).get("playlistSidebarRenderer", {}).get("items", [])
    for item in sidebar_items:
        primary = item.get("playlistSidebarPrimaryInfoRenderer")
        if primary:
            _merge(result, "title", _extract_text(primary.get("title")))
            _merge(result, "description", _extract_text(primary.get("description")) or None)
            stats = primary.get("stats", [])
            if stats:
                count = _parse_count_text(_extract_text(stats[0]))
                if count is not None:
                    _merge(result, "videoCount", count)
        secondary = item.get("playlistSidebarSecondaryInfoRenderer")
        if secondary:
            owner = secondary.get("videoOwner", {}).get("videoOwnerRenderer", {})
            _merge(result, "author", _extract_text(owner.get("title")))
            _merge(result, "authorId", _browse_id_from_runs(owner.get("title")))

    # 3) Newer unified pageHeaderRenderer
    page_header = header.get("pageHeaderRenderer", {}).get("content", {}).get("pageHeaderViewModel", {})
    if page_header:
        title_vm = page_header.get("title", {}).get("dynamicTextViewModel", {}).get("text", {})
        _merge(result, "title", title_vm.get("content", ""))
        desc_vm = page_header.get("description", {}).get("descriptionPreviewViewModel", {}).get("description", {})
        _merge(result, "description", desc_vm.get("content") or None)
        rows = (
            page_header.get("metadata", {})
            .get("contentMetadataViewModel", {})
            .get("metadataRows", [])
        )
        author, author_id = _author_from_metadata_rows(rows)
        _merge(result, "author", author)
        _merge(result, "authorId", author_id)

    # 4) Last-resort metadata renderer
    pmr = data.get("metadata", {}).get("playlistMetadataRenderer", {})
    if pmr:
        _merge(result, "title", pmr.get("title", ""))
        _merge(result, "description", pmr.get("description") or None)

    return result


def _merge(target: Dict[str, Any], key: str, value: Any) -> None:
    """Set target[key] only if not already present or currently falsy."""
    if value and not target.get(key):
        target[key] = value


def _browse_id_from_runs(text_obj: Any) -> str:
    """Extract the first browseEndpoint.browseId from a runs-style text object."""
    if not isinstance(text_obj, dict):
        return ""
    for run in text_obj.get("runs", []):
        browse = run.get("navigationEndpoint", {}).get("browseEndpoint", {})
        if browse.get("browseId"):
            return browse["browseId"]
    return ""


def _first_stat_text(stats: Optional[List[Any]]) -> str:
    """Return the plain text of the first stats run (used for 'N videos' line)."""
    if not stats:
        return ""
    return _extract_text(stats[0])


def _author_from_metadata_rows(rows: List[Dict[str, Any]]) -> tuple[str, str]:
    """Find the first (author, authorId) in pageHeaderRenderer metadata rows."""
    for row in rows:
        for part in row.get("metadataParts", []):
            text_obj = part.get("text", {})
            for cmd_run in text_obj.get("commandRuns", []):
                browse = (
                    cmd_run.get("onTap", {})
                    .get("innertubeCommand", {})
                    .get("browseEndpoint", {})
                )
                if browse.get("browseId"):
                    return text_obj.get("content", ""), browse["browseId"]
    return "", ""


def _extract_playlist_videos(data: Dict[str, Any]) -> tuple[List[Dict[str, Any]], Optional[str]]:
    """Extract videos and next continuation token from the initial browse response."""
    tabs = data.get("contents", {}).get("twoColumnBrowseResultsRenderer", {}).get("tabs", [])
    if not tabs:
        return [], None

    tab_content = tabs[0].get("tabRenderer", {}).get("content", {})
    section_list = tab_content.get("sectionListRenderer", {})
    if not section_list:
        return [], None

    for section in section_list.get("contents", []):
        item_section = section.get("itemSectionRenderer", {})
        for content in item_section.get("contents", []):
            pvlr = content.get("playlistVideoListRenderer")
            if pvlr:
                return _parse_playlist_entries(pvlr.get("contents", []))
    return [], None


def _extract_continuation_videos(data: Dict[str, Any]) -> tuple[List[Dict[str, Any]], Optional[str]]:
    """Extract videos and next continuation from a continuation browse response."""
    actions = data.get("onResponseReceivedActions") or data.get("onResponseReceivedEndpoints") or []
    for action in actions:
        append = action.get("appendContinuationItemsAction", {})
        items = append.get("continuationItems")
        if items:
            return _parse_playlist_entries(items)
    return [], None


def _parse_playlist_entries(entries: List[Dict[str, Any]]) -> tuple[List[Dict[str, Any]], Optional[str]]:
    """Parse a list of playlistVideoListRenderer contents into video dicts + continuation."""
    videos: List[Dict[str, Any]] = []
    continuation: Optional[str] = None

    for entry in entries:
        try:
            if "playlistVideoRenderer" in entry:
                video = playlist_video_renderer_to_invidious(entry["playlistVideoRenderer"])
                if video.get("videoId"):
                    videos.append(video)
            elif "lockupViewModel" in entry:
                converted = lockup_view_model_to_invidious(entry["lockupViewModel"])
                if converted and converted.get("type") == "video":
                    converted.setdefault("lengthSeconds", 0)
                    videos.append(converted)
            elif "continuationItemRenderer" in entry:
                token = (
                    entry["continuationItemRenderer"]
                    .get("continuationEndpoint", {})
                    .get("continuationCommand", {})
                    .get("token")
                )
                if token:
                    continuation = token
        except (KeyError, TypeError, IndexError) as e:
            logger.debug(f"[InnerTube] Skipping malformed playlist entry: {e}")
            continue

    return videos, continuation
