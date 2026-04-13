"""Comments endpoints - InnerTube primary, Invidious fallback."""

import logging
from typing import Any, List, Optional

from fastapi import APIRouter, HTTPException, Query

import innertube
import invidious_proxy
from converters import resolve_invidious_url

router = APIRouter(tags=["comments"])
logger = logging.getLogger(__name__)


def _resolve_comment_thumbnails(comments: List[Any], invidious_base: str) -> List[Any]:
    """Resolve relative thumbnail URLs in comment author thumbnails."""
    resolved_comments = []
    for comment in comments:
        resolved_comment = dict(comment)

        # Resolve author thumbnails
        if "authorThumbnails" in resolved_comment:
            resolved_thumbs = []
            for thumb in resolved_comment["authorThumbnails"]:
                resolved_thumb = dict(thumb)
                if "url" in resolved_thumb:
                    resolved_thumb["url"] = resolve_invidious_url(resolved_thumb["url"], invidious_base)
                resolved_thumbs.append(resolved_thumb)
            resolved_comment["authorThumbnails"] = resolved_thumbs

        # Recursively resolve replies if present
        if "replies" in resolved_comment and resolved_comment["replies"]:
            if "comments" in resolved_comment["replies"]:
                resolved_comment["replies"]["comments"] = _resolve_comment_thumbnails(
                    resolved_comment["replies"]["comments"], invidious_base
                )

        resolved_comments.append(resolved_comment)

    return resolved_comments


@router.get("/comments/{video_id}")
async def get_comments(
    video_id: str, continuation: Optional[str] = Query(None, description="Continuation token for pagination")
):
    """
    Get comments for a video.

    Tries InnerTube first (direct YouTube API), falls back to Invidious if configured.
    """
    # Try InnerTube first
    try:
        data = await innertube.get_comments(video_id, continuation)
        if data and data.get("comments"):
            logger.info(f"[Comments] InnerTube success for {video_id}: {len(data['comments'])} comments")
            return data
        logger.debug(f"[Comments] InnerTube returned no comments for {video_id}, trying Invidious")
    except innertube.InnerTubeError as e:
        logger.debug(f"[Comments] InnerTube error for {video_id}: {e}")

    # Fall back to Invidious
    if invidious_proxy.is_enabled():
        try:
            data = await invidious_proxy.get_comments(video_id, continuation)
            if data is None:
                return {"comments": [], "continuation": None}

            # Resolve relative URLs in comment author thumbnails
            if "comments" in data:
                invidious_base = invidious_proxy.get_base_url()
                data["comments"] = _resolve_comment_thumbnails(data["comments"], invidious_base)

            return data
        except invidious_proxy.InvidiousProxyError as e:
            raise HTTPException(status_code=502, detail=f"Comments proxy error: {e}")

    # Neither source available — return empty rather than 503
    return {"comments": [], "continuation": None}
