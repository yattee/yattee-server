"""InnerTube search - general and channel search.

Uses YouTube's InnerTube /search endpoint for general queries,
and resolve_url + browse endpoints to search within channels.
"""

import base64
import logging
import time
import urllib.parse
from typing import Any, Dict, List, Optional, Tuple

from innertube._client import InnerTubeError, innertube_post
from innertube._converters import (
    channel_renderer_to_invidious,
    lockup_view_model_to_invidious,
    playlist_renderer_to_invidious,
    video_renderer_to_invidious,
)
from innertube._playlists import _extract_continuation_token

logger = logging.getLogger("innertube")


SORT_MAP = {"date": 2, "views": 3, "rating": 4}
DATE_MAP = {"hour": 1, "today": 2, "week": 3, "month": 4, "year": 5}
DURATION_MAP = {"short": 1, "long": 2, "medium": 3}
TYPE_MAP = {"video": 1, "channel": 2, "playlist": 3}

_CACHE_TTL_SECONDS = 1800
_MAX_PAGE_WALK = 50

# Key: (query, search_type, sort, date, duration, page) where `page` is the page
# that was just returned; the stored token fetches `page + 1`.
_continuation_cache: Dict[Tuple[Any, ...], Tuple[str, float]] = {}


def _cache_get(key: Tuple[Any, ...]) -> Optional[str]:
    entry = _continuation_cache.get(key)
    if not entry:
        return None
    token, expires_at = entry
    if time.time() >= expires_at:
        _continuation_cache.pop(key, None)
        return None
    return token


def _cache_set(key: Tuple[Any, ...], token: str) -> None:
    _continuation_cache[key] = (token, time.time() + _CACHE_TTL_SECONDS)


def _cache_evict(key: Tuple[Any, ...]) -> None:
    _continuation_cache.pop(key, None)


def _build_search_params(
    search_type: Optional[str] = None,
    sort: Optional[str] = None,
    date: Optional[str] = None,
    duration: Optional[str] = None,
) -> Optional[str]:
    """Build base64-encoded protobuf params for InnerTube search endpoint.

    Encodes sort order, upload date, duration, and result type filters.
    Returns None if no filters are specified.
    """
    has_sort = sort and sort in SORT_MAP
    has_date = date and date in DATE_MAP
    has_duration = duration and duration in DURATION_MAP
    has_type = search_type and search_type in TYPE_MAP

    if not has_sort and not has_date and not has_duration and not has_type:
        return None

    data = bytearray()

    # Field 1 (0x08): sort order
    if has_sort:
        data.extend([0x08, SORT_MAP[sort]])

    # Field 2 (0x12): filters submessage
    if has_date or has_duration or has_type:
        filters = bytearray()
        if has_date:
            filters.extend([0x08, DATE_MAP[date]])
        if has_type:
            filters.extend([0x10, TYPE_MAP[search_type]])
        if has_duration:
            filters.extend([0x18, DURATION_MAP[duration]])

        data.extend([0x12, len(filters)])
        data.extend(filters)

    return base64.b64encode(data).decode() if data else None


def _parse_result_item(item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Convert a single search result item to Invidious format, or None if unsupported."""
    if "videoRenderer" in item:
        return video_renderer_to_invidious(item["videoRenderer"])
    if "channelRenderer" in item:
        return channel_renderer_to_invidious(item["channelRenderer"])
    if "playlistRenderer" in item:
        return playlist_renderer_to_invidious(item["playlistRenderer"])
    if "lockupViewModel" in item:
        return lockup_view_model_to_invidious(item["lockupViewModel"])
    return None


def _parse_search_results(data: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """Parse mixed search results and continuation token from an InnerTube search response.

    Handles both the initial-response shape (sectionListRenderer) and the
    continuation-response shape (appendContinuationItemsAction).
    """
    results: List[Dict[str, Any]] = []
    continuation: Optional[str] = None

    # Initial-response shape.
    sections = (
        data.get("contents", {})
        .get("twoColumnSearchResultsRenderer", {})
        .get("primaryContents", {})
        .get("sectionListRenderer", {})
        .get("contents", [])
    )
    for section in sections:
        if "itemSectionRenderer" in section:
            for item in section["itemSectionRenderer"].get("contents", []):
                converted = _parse_result_item(item)
                if converted:
                    results.append(converted)
        elif "continuationItemRenderer" in section:
            token = _extract_continuation_token(section["continuationItemRenderer"])
            if token:
                continuation = token

    # Continuation-response shape.
    for command in data.get("onResponseReceivedCommands", []):
        append = command.get("appendContinuationItemsAction", {})
        for item in append.get("continuationItems", []):
            if "itemSectionRenderer" in item:
                for content in item["itemSectionRenderer"].get("contents", []):
                    converted = _parse_result_item(content)
                    if converted:
                        results.append(converted)
            elif "continuationItemRenderer" in item:
                token = _extract_continuation_token(item["continuationItemRenderer"])
                if token:
                    continuation = token

    return results, continuation


async def _fetch_initial(
    query: str, search_type: str, sort: Optional[str], date: Optional[str], duration: Optional[str]
) -> Dict[str, Any]:
    body: Dict[str, Any] = {"query": query}
    params = _build_search_params(search_type=search_type, sort=sort, date=date, duration=duration)
    if params:
        body["params"] = params
    return await innertube_post("search", body)


async def _fetch_continuation(token: str) -> Dict[str, Any]:
    return await innertube_post("search", {"continuation": token})


async def _walk_to_page(
    prefix: Tuple[Any, ...],
    query: str,
    search_type: str,
    sort: Optional[str],
    date: Optional[str],
    duration: Optional[str],
    target_page: int,
) -> List[Dict[str, Any]]:
    """Walk page 1 → target_page via sequential continuations, caching each token.

    Returns the results of `target_page`, or [] if we run out of tokens before getting there.
    """
    data = await _fetch_initial(query, search_type, sort, date, duration)
    results, token = _parse_search_results(data)
    if token:
        _cache_set((*prefix, 1), token)

    current_page = 1
    while current_page < target_page:
        if not token:
            return []
        try:
            data = await _fetch_continuation(token)
        except InnerTubeError as e:
            logger.info(f"[InnerTube] Search walk failed at page {current_page + 1}: {e}")
            return []
        results, next_token = _parse_search_results(data)
        current_page += 1
        if next_token:
            _cache_set((*prefix, current_page), next_token)
        if not results:
            return []
        token = next_token

    return results


async def search(
    query: str,
    search_type: str = "all",
    page: int = 1,
    sort: Optional[str] = None,
    date: Optional[str] = None,
    duration: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Search YouTube via InnerTube with continuation-based pagination.

    Args:
        query: Search query string
        search_type: Result type - "video", "channel", "playlist", or "all"
        page: 1-based page number
        sort: Sort by - "relevance", "date", "views", "rating"
        date: Upload date filter - "hour", "today", "week", "month", "year"
        duration: Duration filter - "short", "medium", "long"

    Returns:
        List of result dicts in Invidious-compatible format
    """
    if page < 1 or page > _MAX_PAGE_WALK:
        return []

    prefix: Tuple[Any, ...] = (query, search_type, sort, date, duration)

    if page == 1:
        data = await _fetch_initial(query, search_type, sort, date, duration)
        results, token = _parse_search_results(data)
        if token:
            _cache_set((*prefix, 1), token)
        logger.info(f"[InnerTube] Search q={query} type={search_type} page=1: {len(results)} results")
        return results

    cached = _cache_get((*prefix, page - 1))
    if cached:
        try:
            data = await _fetch_continuation(cached)
            results, next_token = _parse_search_results(data)
            if next_token:
                _cache_set((*prefix, page), next_token)
            logger.info(
                f"[InnerTube] Search q={query} type={search_type} page={page} (cached): {len(results)} results"
            )
            return results
        except InnerTubeError as e:
            if e.status_code and 400 <= e.status_code < 500:
                logger.info(f"[InnerTube] Stale continuation for page {page}, re-walking: {e}")
                _cache_evict((*prefix, page - 1))
            else:
                raise

    results = await _walk_to_page(prefix, query, search_type, sort, date, duration, page)
    logger.info(f"[InnerTube] Search q={query} type={search_type} page={page} (walk): {len(results)} results")
    return results


async def search_channel(
    channel_id: str, query: str, page: int = 1
) -> Dict[str, Any]:
    """Search for videos within a channel.

    Uses YouTube's resolve_url endpoint to get the correct browse params
    for a channel search URL, then fetches results via browse.

    Args:
        channel_id: YouTube channel ID (UC...) or handle (@name)
        query: Search query string
        page: Page number (1-based)

    Returns:
        Dict with "videos" list and optional "continuation" token
    """
    encoded_query = urllib.parse.quote(query)

    # Step 1: Resolve the channel search URL to get browse params
    if channel_id.startswith("@"):
        search_url = f"https://www.youtube.com/{channel_id}/search?query={encoded_query}"
    else:
        search_url = f"https://www.youtube.com/channel/{channel_id}/search?query={encoded_query}"

    resolve_data = await innertube_post("navigation/resolve_url", {"url": search_url})

    browse_endpoint = resolve_data.get("endpoint", {}).get("browseEndpoint", {})
    browse_id = browse_endpoint.get("browseId", channel_id)
    params = browse_endpoint.get("params")

    if not params:
        logger.warning(f"[InnerTube] Channel search resolve failed for {channel_id}")
        return {"videos": [], "continuation": None}

    # Step 2: Browse with the resolved params to load the channel page with search tab
    browse_data = await innertube_post("browse", {"browseId": browse_id, "params": params})

    # Step 3: Find the search tab's continuation token and fetch results
    tabs = browse_data.get("contents", {}).get("twoColumnBrowseResultsRenderer", {}).get("tabs", [])

    for tab in tabs:
        renderer = tab.get("expandableTabRenderer", {}) or tab.get("tabRenderer", {})
        if not renderer.get("selected"):
            continue

        # Check if results are inline in the tab content
        content = renderer.get("content", {})
        sl = content.get("sectionListRenderer", {})
        if sl:
            videos, continuation = _parse_search_sections(sl.get("contents", []))
            if videos:
                logger.info(f"[InnerTube] Channel search {channel_id} q={query}: {len(videos)} results")
                return {"videos": videos, "continuation": continuation}

        # If tab content is empty, check for a continuation in the tab's endpoint
        tab_endpoint = renderer.get("endpoint", {}).get("browseEndpoint", {})
        tab_params = tab_endpoint.get("params")
        if tab_params and tab_params != params:
            # Fetch the search tab content with its own params
            tab_data = await innertube_post("browse", {"browseId": browse_id, "params": tab_params, "query": query})

            # Check onResponseReceivedActions (continuation-loaded results)
            for action in tab_data.get("onResponseReceivedActions", []):
                append = action.get("appendContinuationItemsAction", {})
                items = append.get("continuationItems", [])
                if items:
                    videos, continuation = _parse_continuation_items(items)
                    if videos:
                        logger.info(f"[InnerTube] Channel search {channel_id} q={query}: {len(videos)} results")
                        return {"videos": videos, "continuation": continuation}

            # Also check tab content in the response
            tabs2 = tab_data.get("contents", {}).get("twoColumnBrowseResultsRenderer", {}).get("tabs", [])
            for tab2 in tabs2:
                r2 = tab2.get("expandableTabRenderer", {}) or tab2.get("tabRenderer", {})
                if r2.get("selected"):
                    sl2 = r2.get("content", {}).get("sectionListRenderer", {})
                    if sl2:
                        videos, continuation = _parse_search_sections(sl2.get("contents", []))
                        if videos:
                            logger.info(
                                f"[InnerTube] Channel search {channel_id} q={query}: {len(videos)} results"
                            )
                            return {"videos": videos, "continuation": continuation}

    logger.debug(f"[InnerTube] Channel search {channel_id} q={query}: no results found in response")
    return {"videos": [], "continuation": None}


def _parse_search_sections(sections: list) -> tuple[list, str | None]:
    """Parse video results from sectionListRenderer contents."""
    videos = []
    continuation = None

    for section in sections:
        isr = section.get("itemSectionRenderer", {})
        for item in isr.get("contents", []):
            if "videoRenderer" in item:
                videos.append(video_renderer_to_invidious(item["videoRenderer"]))

        if "continuationItemRenderer" in section:
            token = (
                section["continuationItemRenderer"]
                .get("continuationEndpoint", {})
                .get("continuationCommand", {})
                .get("token")
            )
            if token:
                continuation = token

    return videos, continuation


def _parse_continuation_items(items: list) -> tuple[list, str | None]:
    """Parse video results from continuation items."""
    videos = []
    continuation = None

    for item in items:
        if "itemSectionRenderer" in item:
            isr = item["itemSectionRenderer"]
            for content in isr.get("contents", []):
                if "videoRenderer" in content:
                    videos.append(video_renderer_to_invidious(content["videoRenderer"]))
        elif "videoRenderer" in item:
            videos.append(video_renderer_to_invidious(item["videoRenderer"]))
        elif "continuationItemRenderer" in item:
            token = (
                item["continuationItemRenderer"]
                .get("continuationEndpoint", {})
                .get("continuationCommand", {})
                .get("token")
            )
            if token:
                continuation = token

    return videos, continuation
