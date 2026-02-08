"""Caption URL resolution and content fetching."""

import logging
from typing import Optional, Tuple

import httpx

from ytdlp_wrapper._youtube import get_video_info

logger = logging.getLogger(__name__)


async def get_caption_url(
    video_id: str, lang: str, auto_generated: bool = False, format: str = "vtt"
) -> Tuple[Optional[str], Optional[dict]]:
    """Get caption URL and metadata from video info.

    Args:
        video_id: YouTube video ID
        lang: Language code (e.g., "en", "es")
        auto_generated: Whether to get auto-generated captions
        format: Desired format ("vtt", "srv1", "json3")

    Returns:
        Tuple of (url, metadata) where metadata includes impersonate flag
    """
    info = await get_video_info(video_id)

    subtitles = info.get("subtitles", {})
    automatic = info.get("automatic_captions", {})

    # Try expected source first, then fallback to the other
    if auto_generated:
        primary, primary_name = automatic, "automatic_captions"
        fallback, fallback_name = subtitles, "subtitles"
    else:
        primary, primary_name = subtitles, "subtitles"
        fallback, fallback_name = automatic, "automatic_captions"

    # Try primary source first, then fallback
    for source, source_name in [(primary, primary_name), (fallback, fallback_name)]:
        if lang not in source:
            continue

        formats = source[lang]
        if not formats:
            continue

        # Find the requested format, or fall back to first available
        caption_data = None
        for fmt in formats:
            if fmt.get("ext") == format:
                caption_data = fmt
                break

        if not caption_data:
            caption_data = formats[0]

        if caption_data:
            if source_name != primary_name:
                logger.info(
                    f"[Captions] Found {video_id} lang={lang} in {source_name} "
                    f"(fallback from {primary_name})"
                )
            return caption_data.get("url"), caption_data

    # Log available languages for debugging
    logger.warning(
        f"[Captions] Not found: {video_id} lang={lang} auto={auto_generated}. "
        f"Available: subtitles={list(subtitles.keys())}, automatic_captions={list(automatic.keys())}"
    )
    return None, None


async def fetch_caption_content(
    video_id: str, lang: str, auto_generated: bool = False, format: str = "vtt"
) -> Tuple[Optional[str], Optional[str]]:
    """Fetch caption content from YouTube.

    Args:
        video_id: YouTube video ID
        lang: Language code (e.g., "en", "es")
        auto_generated: Whether to get auto-generated captions
        format: Desired format ("vtt", "srv1", "json3")

    Returns:
        Tuple of (content, content_type)
    """
    url, metadata = await get_caption_url(video_id, lang, auto_generated, format)
    if not url:
        return None, None

    # Determine content type based on format
    content_types = {
        "vtt": "text/vtt",
        "srv1": "application/xml",
        "json3": "application/json",
    }
    content_type = content_types.get(format, "text/plain")

    # Build headers - some URLs require impersonation
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers=headers, follow_redirects=True)
            response.raise_for_status()
            return response.text, content_type
    except (httpx.HTTPStatusError, httpx.TimeoutException, httpx.RequestError) as e:
        logger.warning(f"Failed to fetch caption: {e}")
        return None, None
