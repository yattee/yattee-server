"""Playlist endpoints."""

import logging

from fastapi import APIRouter, HTTPException

import invidious_proxy
from converters import invidious_to_playlist_response, ytdlp_to_video_list_item
from models import PlaylistResponse
from settings import get_settings
from ytdlp_wrapper import YtDlpError, get_playlist_info

router = APIRouter(tags=["playlists"])
logger = logging.getLogger(__name__)


@router.get("/playlists/{playlist_id}", response_model=PlaylistResponse)
async def get_playlist(playlist_id: str):
    """Get playlist details and videos (Invidious-compatible)."""
    s = get_settings()

    # Try Invidious proxy first if enabled
    if s.invidious_proxy_playlists and invidious_proxy.is_enabled():
        try:
            data = await invidious_proxy.get_playlist(playlist_id)
            if data:
                invidious_base = invidious_proxy.get_base_url()
                return invidious_to_playlist_response(data, invidious_base)
        except invidious_proxy.InvidiousProxyError:
            pass  # Fall through to yt-dlp

    # Use yt-dlp
    try:
        info = await get_playlist_info(playlist_id)

        videos = []
        for entry in info.get("entries", []):
            try:
                videos.append(ytdlp_to_video_list_item(entry))
            except (KeyError, TypeError, ValueError):
                continue

        return PlaylistResponse(
            playlistId=info.get("id") or playlist_id,
            title=info.get("title") or "Playlist",
            description=info.get("description"),
            author=info.get("uploader") or info.get("channel"),
            authorId=info.get("uploader_id") or info.get("channel_id"),
            videoCount=len(videos),
            videos=videos,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except YtDlpError as e:
        raise HTTPException(status_code=404, detail=f"Playlist not found: {e}")
    except (KeyError, TypeError) as e:
        logger.error(f"[Playlists] Unexpected error for {playlist_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
