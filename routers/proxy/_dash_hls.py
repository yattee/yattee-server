"""DASH -> HLS (fMP4) manifest translation for YouTube VOD.

Why: YouTube's own HLS tops out at 1080p H.264 and is muxed per language
(mpv cannot switch audio inside it). The DASH formats go up to 4K and have
separate audio tracks per language, but mpv's DASH demuxer reads the files
as one long Range request, which googlevideo throttles.

What the browser does instead is index-driven: it reads the ``sidx`` box and
fetches each fragment with its own small Range request. HLS can express
exactly that for fMP4 (``EXT-X-MAP`` + ``EXT-X-BYTERANGE``), so we only
translate the *manifest*; the player still downloads every byte of media
through /proxy/relay (default, see _relay_segments) or straight from googlevideo.

  GET /proxy/dash-hls/master?v=<id>&h=1080[&fps=60]&sig&exp[&relay=1]
      master playlist: ONE video variant (the requested quality) plus one
      EXT-X-MEDIA audio rendition per allowed language (original always).
  GET /proxy/dash-hls/media?url=<googlevideo>&sig&exp[&relay=1]
      media playlist: fetches the file head, parses ftyp/moov/sidx and emits
      one byte-range segment per sidx reference.

Only mp4 (avc1 / av01) video and m4a (AAC) audio are used: ffmpeg's HLS
demuxer wants fMP4 or TS segments, not WebM.

Settings (columns added by alembic revision 014):
  hls_dash_enabled          replace YouTube HLS with translated DASH (default on)
  hls_dash_audio_languages  comma list of extra audio languages to expose
                            (original track is always included)
  hls_dash_prefer_av1       prefer AV1 over H.264 when both exist (default off;
                            >1080p is AV1 regardless since H.264 stops there)
"""

import logging
import math
import struct
import time
import urllib.parse
from typing import Optional

import httpx
from cachetools import TTLCache
from fastapi import HTTPException, Request
from fastapi.responses import Response

from egress import is_youtube_url, local_address_for
from routers.proxy._relay import (
    DEFAULT_TTL_SECONDS,
    UPSTREAM_USER_AGENT,
    _sign,
    _verify,
    signed_relay_url,
)
from routers.proxy._streaming import router
from settings import get_settings
from utils import get_base_url
from ytdlp_wrapper import is_safe_url

logger = logging.getLogger(__name__)

HLS_MIME = "application/vnd.apple.mpegurl"
_HEAD_BYTES = 256 * 1024
_sidx_cache: TTLCache = TTLCache(maxsize=256, ttl=3600)


# --- settings ----------------------------------------------------------------


def dash_enabled() -> bool:
    return bool(getattr(get_settings(), "hls_dash_enabled", True))


def _extra_languages() -> list[str]:
    raw = getattr(get_settings(), "hls_dash_audio_languages", None) or ""
    return [x.strip().lower() for x in raw.replace(";", ",").split(",") if x.strip()]


def _prefer_av1() -> bool:
    return bool(getattr(get_settings(), "hls_dash_prefer_av1", False))


def _relay_segments() -> bool:
    """Route segments through /proxy/relay.

    ffmpeg's HLS demuxer keeps a persistent connection per playlist and, with
    ``http_multiple`` (auto-enabled on HTTP/1.1), pre-opens the request for the
    next segment and leaves its body unread. When the player pauses, googlevideo
    resets those idle connections after a few minutes; on resume ffmpeg swallows
    the mid-segment error, hands the truncated fragment to the mp4 demuxer and
    the video stream never resyncs (frozen picture, audio continues). Relaying
    moves the idle connection to our reverse proxy, which tolerates it.
    """
    return bool(getattr(get_settings(), "hls_dash_relay", True))


def _height_bounds() -> tuple[int, int]:
    s = get_settings()
    return (int(getattr(s, "hls_min_height", 0) or 0), int(getattr(s, "hls_max_height", 0) or 0))


# --- signed URLs ---------------------------------------------------------------


def signed_dash_master_url(
    base_url: str,
    video_id: str,
    *,
    height: int,
    fps: Optional[int] = None,
    relay: bool = False,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
) -> str:
    exp = int(time.time()) + ttl_seconds
    params = {"v": video_id, "h": str(height), "sig": _sign(video_id, exp), "exp": str(exp)}
    if fps:
        params["fps"] = str(fps)
    if relay:
        params["relay"] = "1"
    return f"{base_url.rstrip('/')}/proxy/dash-hls/master?{urllib.parse.urlencode(params)}"


def _signed_media_url(base_url: str, fmt_url: str, *, relay: bool, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> str:
    exp = int(time.time()) + ttl_seconds
    params = {"url": fmt_url, "sig": _sign(fmt_url, exp), "exp": str(exp)}
    if relay:
        params["relay"] = "1"
    return f"{base_url.rstrip('/')}/proxy/dash-hls/media?{urllib.parse.urlencode(params)}"


# --- format planning ---------------------------------------------------------


def _is_video_mp4(f: dict) -> bool:
    return (
        f.get("ext") == "mp4"
        and f.get("vcodec") not in (None, "none", "images")
        and f.get("acodec") in (None, "none")
        and bool(f.get("url"))
        and bool(f.get("height"))
        and not f.get("fragments")
        and not str(f.get("protocol", "")).startswith("m3u8")
    )


def _is_audio_m4a(f: dict) -> bool:
    return (
        f.get("ext") == "m4a"
        and str(f.get("acodec", "")).startswith("mp4a")
        and f.get("vcodec") in (None, "none")
        and bool(f.get("url"))
        and not str(f.get("protocol", "")).startswith("m3u8")
    )


def _codec_family(f: dict) -> str:
    v = str(f.get("vcodec", ""))
    return "av01" if v.startswith("av01") else "avc1" if v.startswith("avc1") else v.split(".")[0]


def plan_video(formats: list[dict], *, prefer_av1: bool = False) -> list[dict]:
    """Best mp4 video format per (height, fps), sorted best first."""
    best: dict[tuple[int, int], dict] = {}
    rank = {"av01": 1, "avc1": 0} if prefer_av1 else {"avc1": 1, "av01": 0}
    for f in formats or []:
        if not _is_video_mp4(f):
            continue
        key = (int(f["height"]), round(float(f.get("fps") or 30)))
        cur = best.get(key)
        score = (rank.get(_codec_family(f), -1), float(f.get("tbr") or 0))
        if cur is None or score > (rank.get(_codec_family(cur), -1), float(cur.get("tbr") or 0)):
            best[key] = f
    return sorted(best.values(), key=lambda f: (int(f["height"]), round(float(f.get("fps") or 30))), reverse=True)


def _is_original(f: dict) -> bool:
    note = str(f.get("format_note") or "").lower()
    return "original" in note or (f.get("language_preference") or 0) > 0


def _lang_base(code: Optional[str]) -> str:
    return (code or "").lower().split("-")[0]


def plan_audio(formats: list[dict], *, extra_languages: Optional[list[str]] = None) -> list[dict]:
    """Best m4a audio per language; original first, then the allowed extras."""
    by_lang: dict[str, dict] = {}
    original: Optional[dict] = None
    for f in formats or []:
        if not _is_audio_m4a(f):
            continue
        lang = (f.get("language") or "").lower()
        tbr = float(f.get("tbr") or 0)
        if _is_original(f):
            if original is None or tbr > float(original.get("tbr") or 0):
                original = f
            continue
        cur = by_lang.get(lang)
        if cur is None or tbr > float(cur.get("tbr") or 0):
            by_lang[lang] = f
    if original is None:
        # Single-audio video: no language tagging at all -> best overall.
        if by_lang:
            original = max(by_lang.values(), key=lambda f: float(f.get("tbr") or 0))
            by_lang = {k: v for k, v in by_lang.items() if v is not original}
        else:
            return []
    out = [original]
    wanted = [_lang_base(x) for x in (extra_languages or [])]
    if wanted:
        for lang, f in sorted(by_lang.items()):
            if _lang_base(lang) in wanted and _lang_base(lang) != _lang_base(original.get("language")):
                out.append(f)
    return out


def _display_name(f: dict, *, original: bool) -> str:
    note = str(f.get("format_note") or "")
    name = note.split(",")[0].strip() or (f.get("language") or "Audio")
    name = name.replace("(default)", "").strip()
    if original and "original" not in name.lower():
        name += " (original)"
    return name.replace('"', "")


def pick_video(planned: list[dict], height: int, fps: Optional[int]) -> Optional[dict]:
    if not planned:
        return None
    exact = [
        f for f in planned if int(f["height"]) == height and (fps is None or round(float(f.get("fps") or 30)) == fps)
    ]
    if exact:
        return exact[0]
    same = [f for f in planned if int(f["height"]) == height]
    if same:
        return same[0]
    below = [f for f in planned if int(f["height"]) <= height]
    return below[0] if below else planned[-1]


# --- sidx parsing ------------------------------------------------------------


def _transport_for(url: str):
    if is_youtube_url(url):
        s = get_settings()
        proxy = s.effective_yt_egress_proxy()
        local_addr = local_address_for(s.effective_ip_family())
        if proxy or local_addr:
            return httpx.AsyncHTTPTransport(proxy=proxy, local_address=local_addr)
    return None


async def _fetch_range(url: str, start: int, end: int) -> bytes:
    transport = _transport_for(url)
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(connect=10.0, read=20.0, write=10.0, pool=10.0),
        follow_redirects=True,
        **({"transport": transport} if transport else {}),
    ) as client:
        resp = await client.get(url, headers={"User-Agent": UPSTREAM_USER_AGENT, "Range": f"bytes={start}-{end}"})
    if resp.status_code not in (200, 206):
        raise HTTPException(status_code=resp.status_code, detail="Upstream error")
    return resp.content


def _iter_boxes(buf: bytes, offset: int = 0):
    """Yield (type, box_start, box_size, header_size) for top-level boxes."""
    pos = offset
    while pos + 8 <= len(buf):
        (size,) = struct.unpack(">I", buf[pos : pos + 4])
        btype = buf[pos + 4 : pos + 8].decode("latin1")
        hdr = 8
        if size == 1:
            if pos + 16 > len(buf):
                return
            (size,) = struct.unpack(">Q", buf[pos + 8 : pos + 16])
            hdr = 16
        elif size == 0:
            size = len(buf) - pos
        yield btype, pos, size, hdr
        if size <= 0:
            return
        pos += size


def parse_sidx(buf: bytes, start: int, hdr: int) -> tuple[int, list[tuple[int, float]]]:
    """Return (first_offset, [(size, duration_s), ...]) from a sidx box."""
    p = start + hdr
    version = buf[p]
    p += 4  # version + flags
    _ref_id, timescale = struct.unpack(">II", buf[p : p + 8])
    p += 8
    if version == 0:
        _ept, first_offset = struct.unpack(">II", buf[p : p + 8])
        p += 8
    else:
        _ept, first_offset = struct.unpack(">QQ", buf[p : p + 16])
        p += 16
    _reserved, ref_count = struct.unpack(">HH", buf[p : p + 4])
    p += 4
    refs = []
    for _ in range(ref_count):
        a, dur, _sap = struct.unpack(">III", buf[p : p + 12])
        p += 12
        refs.append((a & 0x7FFFFFFF, dur / float(timescale or 1)))
    return first_offset, refs


async def index_file(url: str) -> dict:
    """{'init_end': int, 'segments': [(offset, size, dur), ...]} for an fMP4 DASH file."""
    cached = _sidx_cache.get(url)
    if cached:
        return cached
    buf = await _fetch_range(url, 0, _HEAD_BYTES - 1)
    moov_end = None
    sidx = None
    for btype, pos, size, hdr in _iter_boxes(buf):
        if btype == "moov":
            moov_end = pos + size
        if btype == "sidx":
            if pos + size > len(buf):
                buf += await _fetch_range(url, len(buf), pos + size - 1)
            sidx = (pos, size, hdr)
            break
        if btype in ("moof", "mdat"):
            break
    if sidx is None or moov_end is None:
        raise HTTPException(status_code=502, detail="No sidx/moov found in upstream file")
    pos, size, hdr = sidx
    first_offset, refs = parse_sidx(buf, pos, hdr)
    anchor = pos + size + first_offset
    segments = []
    off = anchor
    for seg_size, dur in refs:
        segments.append((off, seg_size, dur))
        off += seg_size
    out = {"init_end": pos + size, "segments": segments}  # init = ftyp+moov+sidx
    _sidx_cache[url] = out
    return out


# --- playlists -----------------------------------------------------------------


def _q(s: str) -> str:
    return '"' + s.replace('"', "") + '"'


def build_master(video: dict, audios: list[dict], *, base_url: str, relay: bool) -> str:
    lines = ["#EXTM3U", "#EXT-X-VERSION:7", "#EXT-X-INDEPENDENT-SEGMENTS"]
    for i, a in enumerate(audios):
        lang = a.get("language") or ""
        attrs = [
            "TYPE=AUDIO",
            'GROUP-ID="aud"',
            f"NAME={_q(_display_name(a, original=(i == 0)))}",
            f"DEFAULT={'YES' if i == 0 else 'NO'}",
            "AUTOSELECT=YES",
        ]
        if lang:
            attrs.append(f"LANGUAGE={_q(lang)}")
        attrs.append(f"URI={_q(_signed_media_url(base_url, a['url'], relay=relay))}")
        lines.append("#EXT-X-MEDIA:" + ",".join(attrs))
    acodec = (audios[0].get("acodec") if audios else None) or "mp4a.40.2"
    codecs = f"{video.get('vcodec')},{acodec}" if audios else str(video.get("vcodec"))
    bw = int(((float(video.get("tbr") or 0)) + (float(audios[0].get("tbr") or 0) if audios else 0)) * 1000) or 1
    attrs = [f"BANDWIDTH={bw}", f"CODECS={_q(codecs)}", f"RESOLUTION={video.get('width')}x{video.get('height')}"]
    if video.get("fps"):
        attrs.append(f"FRAME-RATE={float(video['fps']):.3f}")
    if audios:
        attrs.append('AUDIO="aud"')
    lines.append("#EXT-X-STREAM-INF:" + ",".join(attrs))
    lines.append(_signed_media_url(base_url, video["url"], relay=relay))
    return "\n".join(lines) + "\n"


def _segment_url(base: str, n: int) -> str:
    """Per-segment URL variant for the same resource.

    ``file=seg.mp4`` must be the LAST query parameter: ffmpeg >= 7.1
    (``extension_picky``) rejects HLS segments whose URL does not end in a
    known media extension, and it only looks at the text after the last dot.
    ``rn=N`` makes every segment URL distinct so ffmpeg >= 9 cannot coalesce
    the contiguous byte ranges into one whole-file request, which googlevideo
    throttles to roughly realtime (measured: 90 s+ vs <1 s for 10 s of 4K).
    Keep-alive still reuses the connection. googlevideo ignores both params.
    """
    sep = "&" if "?" in base else "?"
    return f"{base}{sep}rn={n}&file=seg.mp4"


def build_media(seg_url: str, index: dict) -> str:
    segs = index["segments"]
    target = max(1, math.ceil(max((d for _, _, d in segs), default=1)))
    lines = [
        "#EXTM3U",
        "#EXT-X-VERSION:7",
        f"#EXT-X-TARGETDURATION:{target}",
        "#EXT-X-PLAYLIST-TYPE:VOD",
        "#EXT-X-MEDIA-SEQUENCE:0",
        "#EXT-X-INDEPENDENT-SEGMENTS",
        f'#EXT-X-MAP:URI={_q(_segment_url(seg_url, 0))},BYTERANGE="{index["init_end"]}@0"',
    ]
    for n, (off, size, dur) in enumerate(segs, start=1):
        lines.append(f"#EXTINF:{dur:.6f},")
        lines.append(f"#EXT-X-BYTERANGE:{size}@{off}")
        lines.append(_segment_url(seg_url, n))
    lines.append("#EXT-X-ENDLIST")
    return "\n".join(lines) + "\n"


# --- API integration -----------------------------------------------------------


async def dash_hls_streams(video_id: str, *, base_url: str, relay: bool) -> list:
    """FormatStream list (one per quality) for the API response, or []."""
    from models import FormatStream
    from ytdlp_wrapper import get_video_info

    info = await get_video_info(video_id)
    if info.get("is_live"):
        return []
    planned = plan_video(info.get("formats") or [], prefer_av1=_prefer_av1())
    audios = plan_audio(info.get("formats") or [], extra_languages=_extra_languages())
    if not planned or not audios:
        return []
    min_h, max_h = _height_bounds()
    inside = [
        f for f in planned if (not min_h or int(f["height"]) >= min_h) and (not max_h or int(f["height"]) <= max_h)
    ]
    if not inside:
        inside = [planned[-1] if max_h and all(int(f["height"]) > max_h for f in planned) else planned[0]]
    streams = []
    for f in inside:
        h = int(f["height"])
        fps = round(float(f.get("fps") or 30))
        label = f"{h}p" + (str(fps) if fps > 30 else "")
        streams.append(
            FormatStream(
                url=signed_dash_master_url(base_url, video_id, height=h, fps=fps, relay=relay),
                itag=f"hls-{label}",
                type=f'{HLS_MIME}; codecs="{f.get("vcodec")}, {audios[0].get("acodec") or "mp4a.40.2"}"',
                quality=label,
                container="hls",
                resolution=f"{h}p",
                width=int(f.get("width") or 0) or None,
                height=h,
                encoding=None,
                size=None,
                fps=fps,
                httpHeaders=None,
            )
        )
    logger.info(
        f"[DASH-HLS] API {video_id}: {[s.quality for s in streams]} audio={[a.get('language') for a in audios]}"
    )
    return streams


# --- endpoints -----------------------------------------------------------------


def _check(sig_subject: str, sig: str, exp: int) -> None:
    if int(time.time()) > exp:
        raise HTTPException(status_code=403, detail="URL expired")
    if not _verify(sig_subject, exp, sig):
        raise HTTPException(status_code=403, detail="Invalid signature")


@router.get("/dash-hls/master")
async def dash_hls_master(
    request: Request, v: str, h: int, sig: str, exp: int, fps: Optional[int] = None, relay: int = 0
):
    _check(v, sig, exp)
    from ytdlp_wrapper import get_video_info

    t0 = time.monotonic()
    info = await get_video_info(v)
    planned = plan_video(info.get("formats") or [], prefer_av1=_prefer_av1())
    video = pick_video(planned, h, fps)
    audios = plan_audio(info.get("formats") or [], extra_languages=_extra_languages())
    if video is None or not audios:
        raise HTTPException(status_code=404, detail="No suitable DASH formats")
    base_url_self = get_base_url(request)
    relay_segments = bool(relay) or _relay_segments()
    body = build_master(video, audios, base_url=base_url_self, relay=relay_segments)
    logger.info(
        f"[DASH-HLS] master {v} -> {video.get('format_id')} {video.get('height')}p "
        f"audio={[a.get('format_id') for a in audios]} in {int((time.monotonic() - t0) * 1000)}ms"
    )
    return Response(content=body, media_type=HLS_MIME, headers={"cache-control": "no-store"})


@router.get("/dash-hls/media")
async def dash_hls_media(request: Request, url: str, sig: str, exp: int, relay: int = 0):
    _check(url, sig, exp)
    if not is_safe_url(url):
        raise HTTPException(status_code=403, detail="URL targets restricted network resources")
    t0 = time.monotonic()
    try:
        index = await index_file(url)
    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f"Upstream fetch failed: {e}") from e
    seg_url = url
    relay = bool(relay) or _relay_segments()
    if relay:
        base_url_self = get_base_url(request)
        seg_url = signed_relay_url(base_url_self, url, content_type="video/mp4")
    body = build_media(seg_url, index)
    logger.info(
        f"[DASH-HLS] media {len(index['segments'])} segments relay={bool(relay)} "
        f"in {int((time.monotonic() - t0) * 1000)}ms"
    )
    return Response(content=body, media_type=HLS_MIME, headers={"cache-control": "no-store"})
