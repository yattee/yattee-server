"""MIME types, cookies, stream format conversion, and thumbnails."""

import urllib.parse
from typing import Dict, List, Optional

import tokens as token_utils
from converters._helpers import _filter_sensitive_headers
from models import (
    AdaptiveFormat,
    AudioTrack,
    FormatStream,
    Thumbnail,
)


def convert_thumbnails(thumbnails: Optional[List[dict]]) -> List[Thumbnail]:
    """Convert yt-dlp thumbnails to Invidious format."""
    if not thumbnails:
        return []

    result = []
    for thumb in thumbnails:
        url = thumb.get("url", "")
        width = thumb.get("width")
        height = thumb.get("height")

        # Determine quality based on size
        if width and height:
            if width >= 1280:
                quality = "maxres"
            elif width >= 640:
                quality = "sddefault"
            elif width >= 480:
                quality = "high"
            elif width >= 320:
                quality = "medium"
            else:
                quality = "default"
        else:
            quality = "default"

        result.append(Thumbnail(quality=quality, url=url, width=width, height=height))

    return result


def build_mime_type(
    vcodec: Optional[str], acodec: Optional[str], container: str, has_video: Optional[bool] = None
) -> str:
    """Build MIME type string with codecs."""
    # Use provided has_video flag if given, otherwise compute from vcodec
    if has_video is None:
        has_video = vcodec and vcodec != "none"

    # Known audio-only containers
    audio_containers = ("aac", "m4a", "opus", "ogg", "mp3", "flac", "wav", "weba")

    if container in audio_containers:
        # Always use audio MIME type for audio-only containers
        mime = f"audio/{container}"
    elif container in ("mp4", "m4v"):
        mime = "video/mp4" if has_video else "audio/mp4"
    elif container in ("webm",):
        mime = "video/webm" if has_video else "audio/webm"
    elif container == "3gp":
        mime = "video/3gpp"
    else:
        # For unknown containers, check if we have video
        mime = f"video/{container}" if has_video else f"audio/{container}"

    codecs = []
    if vcodec and vcodec != "none":
        codecs.append(vcodec)
    if acodec and acodec != "none":
        codecs.append(acodec)

    if codecs:
        mime += f'; codecs="{", ".join(codecs)}"'

    return mime


def parse_cookies_to_header(cookie_string: str) -> str:
    """Parse yt-dlp cookie string to HTTP Cookie header format.

    yt-dlp returns cookies in Set-Cookie format:
    'name=value; Domain=.tiktok.com; Path=/; Secure; name2=value2; Domain=...'

    This parses it to HTTP Cookie header format:
    'name=value; name2=value2'
    """
    if not cookie_string:
        return ""

    # Split by semicolon and filter out metadata fields
    metadata_keys = {"domain", "path", "secure", "httponly", "expires", "max-age", "samesite"}
    cookie_parts = []

    for part in cookie_string.split(";"):
        part = part.strip()
        if not part:
            continue

        # Check if it's a key=value pair (not metadata)
        if "=" in part:
            key = part.split("=", 1)[0].strip().lower()
            if key not in metadata_keys:
                cookie_parts.append(part)
        # Skip standalone flags like "Secure", "HttpOnly"

    return "; ".join(cookie_parts)


def convert_formats(
    formats: Optional[List[dict]],
    video_id: str = "",
    proxy_base_url: str = "",
    original_url: str = "",
    user_id: Optional[int] = None,
) -> tuple[List[FormatStream], List[AdaptiveFormat]]:
    """Split yt-dlp formats into muxed and adaptive streams.

    Args:
        formats: List of yt-dlp format dicts
        video_id: Video ID for generating proxy URLs
        proxy_base_url: Base URL for proxy (e.g., "http://server:8085/proxy").
                       If empty, uses direct YouTube URLs.
        original_url: Original URL for external sites (used for re-extraction in proxy)
        user_id: User ID for generating streaming tokens (if basic auth enabled)
    """
    # Generate token if user_id is provided (basic auth enabled)
    stream_token = None
    if user_id is not None and proxy_base_url and video_id:
        stream_token = token_utils.generate_stream_token(user_id, video_id)
    format_streams = []
    adaptive_formats = []

    if not formats:
        return format_streams, adaptive_formats

    # Track HLS streams by URL to deduplicate true duplicates (same manifest URL)
    hls_streams_by_url: Dict[str, FormatStream] = {}

    for fmt in formats:
        # Skip storyboard/thumbnail formats
        if fmt.get("ext") == "mhtml" or fmt.get("vcodec") == "images":
            continue

        itag = str(fmt.get("format_id", ""))

        # Check if this is an HLS stream (protocol-based detection)
        protocol = fmt.get("protocol", "")
        is_hls = protocol.startswith("m3u8") or "hls" in itag.lower()

        if is_hls:
            # Use manifest_url for HLS playback (not the chunklist url)
            hls_url = fmt.get("manifest_url") or fmt.get("url")
            if not hls_url:
                continue

            # HLS streams are muxed - add them as format streams
            hls_height = fmt.get("height")
            hls_width = fmt.get("width")
            new_stream = FormatStream(
                url=hls_url,  # Direct URL to HLS manifest
                itag=itag,
                type="application/vnd.apple.mpegurl",
                quality=f"{hls_height}p" if hls_height else fmt.get("format_note") or "unknown",
                container="hls",
                resolution=f"{hls_height}p" if hls_height else None,
                width=int(hls_width) if hls_width else None,
                height=int(hls_height) if hls_height else None,
                encoding=None,
                size=str(fmt.get("filesize")) if fmt.get("filesize") else None,
                fps=int(fmt.get("fps")) if fmt.get("fps") else None,
                httpHeaders=_filter_sensitive_headers(fmt.get("http_headers")),
            )

            # Deduplicate by URL only - keep stream with better metadata
            if hls_url in hls_streams_by_url:
                existing = hls_streams_by_url[hls_url]
                # Prefer stream with actual resolution info
                if (new_stream.height and not existing.height) or \
                   (new_stream.quality != "unknown" and existing.quality == "unknown"):
                    hls_streams_by_url[hls_url] = new_stream
            else:
                hls_streams_by_url[hls_url] = new_stream
            continue

        direct_url = fmt.get("url")
        if not direct_url:
            continue

        # Handle codec strings - convert empty strings to None
        vcodec = fmt.get("vcodec") or None
        acodec = fmt.get("acodec") or None
        container = fmt.get("ext", "mp4")

        # Check video_ext as fallback when vcodec is unknown (e.g., BitChute)
        video_ext = fmt.get("video_ext")
        audio_ext = fmt.get("audio_ext")
        has_video = (vcodec and vcodec != "none") or (video_ext and video_ext != "none")
        has_audio = acodec and acodec != "none"

        # If we have video but no codec info, and audio_ext is "none" (no separate audio file),
        # assume it's a muxed stream (e.g., BitChute returns video_ext="mp4", audio_ext="none")
        # This is different from explicit acodec="none" which means truly no audio
        if has_video and not has_audio and audio_ext == "none" and acodec is None:
            muxed_containers = ["mp4", "mkv", "webm", "mov", "avi", "flv"]
            if container.lower() in muxed_containers:
                has_audio = True

        width = fmt.get("width")
        height = fmt.get("height")
        fps = fmt.get("fps")

        # For audio-only streams, ignore misleading height values
        # (e.g., yt-dlp returns height=192 for 192kbps audio on Rumble)
        if not has_video:
            width = None
            height = None

        resolution = f"{height}p" if height else None

        mime_type = build_mime_type(vcodec, acodec, container, has_video=has_video)
        bitrate = fmt.get("tbr") or fmt.get("vbr") or fmt.get("abr")
        filesize = fmt.get("filesize") or fmt.get("filesize_approx")
        http_headers = fmt.get("http_headers") or {}

        # NOTE: Cookie injection removed for security - cookies from yt-dlp
        # may contain admin-stored credentials that should not be exposed.
        # Proxy endpoints handle authentication separately.

        # Use proxy URL if base URL provided, otherwise direct URL
        # Use /fast/ endpoint for yt-dlp parallel downloads (much faster)
        if proxy_base_url and video_id:
            if original_url:
                # External site - include original URL for re-extraction
                encoded_url = urllib.parse.quote(original_url, safe="")
                url = f"{proxy_base_url}/fast/{video_id}?itag={itag}&url={encoded_url}"
            else:
                # YouTube - just use video_id
                url = f"{proxy_base_url}/fast/{video_id}?itag={itag}"
            # Add streaming token if basic auth is enabled
            if stream_token:
                url = f"{url}&token={stream_token}"
        else:
            url = direct_url

        if has_video and has_audio:
            # Muxed stream
            format_streams.append(
                FormatStream(
                    url=url,
                    itag=itag,
                    type=mime_type,
                    quality=resolution or fmt.get("format_note") or "unknown",
                    container=container,
                    resolution=resolution,
                    width=int(width) if width else None,
                    height=int(height) if height else None,
                    encoding=vcodec,
                    size=str(filesize) if filesize else None,
                    fps=int(fps) if fps else None,
                    httpHeaders=_filter_sensitive_headers(http_headers),
                )
            )
        else:
            # Adaptive stream (video-only or audio-only)
            audio_track = None
            if has_audio and not has_video:
                lang = fmt.get("language")
                format_note = fmt.get("format_note") or ""
                # Check if this is the original/default audio track
                # yt-dlp marks original tracks with "original" and/or "(default)" in format_note
                is_original = "original" in format_note.lower() or "(default)" in format_note.lower()
                audio_track = AudioTrack(id=lang, displayName=format_note or lang, isDefault=is_original)

            adaptive_formats.append(
                AdaptiveFormat(
                    url=url,
                    itag=itag,
                    type=mime_type,
                    container=container,
                    resolution=resolution,
                    width=int(width) if width and has_video else None,
                    height=int(height) if height and has_video else None,
                    bitrate=str(int(bitrate * 1000)) if bitrate else None,
                    clen=str(filesize) if filesize else None,
                    encoding=vcodec if has_video else acodec,
                    fps=int(fps) if fps and has_video else None,
                    audioTrack=audio_track,
                    audioQuality=fmt.get("format_note") if has_audio and not has_video else None,
                    httpHeaders=_filter_sensitive_headers(http_headers),
                )
            )

    # Add deduplicated HLS streams to format_streams
    format_streams.extend(hls_streams_by_url.values())

    return format_streams, adaptive_formats
