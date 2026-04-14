"""Storyboards endpoint with InnerTube -> yt-dlp -> Invidious fallback chain."""

import logging
from typing import List

from fastapi import APIRouter, HTTPException

import innertube
import invidious_proxy
from converters import convert_storyboards
from models import Storyboard
from ytdlp_wrapper import YtDlpError, get_video_info, sanitize_video_id

router = APIRouter(tags=["storyboards"])
logger = logging.getLogger(__name__)


@router.get("/storyboards/{video_id}", response_model=List[Storyboard])
async def get_storyboards(video_id: str):
    """Get video storyboards (scrubber preview thumbnails).

    Tries InnerTube first (YouTube-direct, no Invidious dependency), then
    falls back to yt-dlp, and finally to an Invidious passthrough if
    configured. Returns an empty list when no storyboards exist for a video.
    """
    try:
        video_id = sanitize_video_id(video_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    tier_errors: List[str] = []

    # 1. InnerTube
    if innertube.is_enabled():
        try:
            it_video = await innertube.get_video_player_next(video_id)
            raw = it_video.get("storyboards") or []
            storyboards = [Storyboard(**sb) for sb in raw]
            if storyboards:
                return storyboards
        except innertube.InnerTubeError as e:
            tier_errors.append(f"innertube: {e}")
            logger.info(f"[Storyboards] InnerTube failed for {video_id}: {e}")

    # 2. yt-dlp
    try:
        info = await get_video_info(video_id)
        storyboards = convert_storyboards(info.get("formats"))
        if storyboards:
            return storyboards
    except YtDlpError as e:
        tier_errors.append(f"yt-dlp: {e}")
        logger.info(f"[Storyboards] yt-dlp failed for {video_id}: {e}")

    # 3. Invidious
    if invidious_proxy.is_enabled():
        try:
            data = await invidious_proxy.fetch_json(f"/api/v1/storyboards/{video_id}")
            if data:
                return [Storyboard(**sb) for sb in data]
        except invidious_proxy.InvidiousProxyError as e:
            tier_errors.append(f"invidious: {e}")
            logger.info(f"[Storyboards] Invidious failed for {video_id}: {e}")

    # No tier raised and no tier produced data — legitimately empty
    if not tier_errors:
        return []

    # Every tier we attempted failed
    logger.warning(f"[Storyboards] All tiers failed for {video_id}: {tier_errors}")
    raise HTTPException(status_code=502, detail=f"Storyboards unavailable: {'; '.join(tier_errors)}")
