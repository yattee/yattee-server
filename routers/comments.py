"""Comments endpoints - proxied through Invidious."""

import logging
from typing import Any, List, Optional

from fastapi import APIRouter, HTTPException, Query

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

    Comments are proxied through Invidious since yt-dlp doesn't extract them well.
    Requires INVIDIOUS_INSTANCE to be configured.
    """
    if not invidious_proxy.is_enabled():
        raise HTTPException(
            status_code=503, detail="Comments require Invidious proxy. Set INVIDIOUS_INSTANCE environment variable."
        )

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
        raise HTTPException(status_code=502, detail=f"Invidious proxy error: {e}")
    except (KeyError, TypeError) as e:
        logger.error(f"[Comments] Unexpected error for {video_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
