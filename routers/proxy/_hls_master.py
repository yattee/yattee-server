"""Filtered HLS master playlist endpoint (+ HLS stream description for the API).

Why: YouTube's VOD HLS master lists one *muxed* (video+audio) variant per
(resolution x audio track) and carries no EXT-X-MEDIA. A video with 21
auto-dubs yields ~130 variants. Two consequences for mpv/ffmpeg:

  * ffmpeg's HLS demuxer opens every variant playlist and probes its first
    segment before playback starts -> ~60 s startup.
  * every variant becomes a separate program; the player lists one nameless
    audio track per variant ("Track 1..N") and switching between them means
    switching variants, which ffmpeg does badly (silence until the next seek).

mpv does no HLS ABR anyway (hls-bitrate=max picks one variant at open), so
nothing is lost by serving a master with exactly ONE variant: the chosen
audio language at the requested height. That is what this module does.

  GET /proxy/hls-master?url=<signed upstream master>&sig&exp[&h=1080&fps=24][&relay=1]

At /api/v1/videos time (finalize_hls_streams) the master is fetched once and
the API lists one HLS formatStream per available quality ("HLS 1080p",
"HLS 720p", ...) within [hls_min_height, hls_max_height], each pointing at
/proxy/hls-master with the matching ``h``/``fps``. The bare ``hlsUrl`` and
yt-dlp's bogus "HLS 144p" formatStream are dropped.

Configured in admin Settings (persisted in the ``settings`` table):
  hls_filter_enabled    master switch (default on)
  hls_audio_language    "" = original audio; "pl" = Polish dub when the video
                        has one, else original
  hls_min_height        0 = no lower bound; else hide qualities below it
  hls_max_height        0 = no upper bound; else hide qualities above it
Columns are added by alembic revision 014.
"""

import logging
import re
import time
import urllib.parse
from typing import Optional

import httpx
from fastapi import HTTPException, Request
from fastapi.responses import Response

from egress import is_youtube_url, local_address_for
from routers.proxy._relay import (
    DEFAULT_TTL_SECONDS,
    UPSTREAM_USER_AGENT,
    _rewrite_hls,
    _sign,
    _verify,
)
from routers.proxy._streaming import router
from settings import get_settings
from ytdlp_wrapper import is_safe_url

logger = logging.getLogger(__name__)

_ATTR_RE = re.compile(r'([A-Z0-9-]+)=("[^"]*"|[^,]*)')
# xtags=acont=dubbed-auto:lang=ar / acont=original:lang=en-US
_ACONT_RE = re.compile(r"acont=([a-z-]+)(?::lang=([A-Za-z]{2,3})(?:-[A-Za-z0-9]+)?)?", re.IGNORECASE)
HLS_MIME = "application/vnd.apple.mpegurl"


def filter_enabled() -> bool:
    return bool(getattr(get_settings(), "hls_filter_enabled", True))


def _audio_language() -> str:
    return (getattr(get_settings(), "hls_audio_language", None) or "").strip().lower()


def _height_bounds() -> tuple[int, int]:
    s = get_settings()
    return (int(getattr(s, "hls_min_height", 0) or 0), int(getattr(s, "hls_max_height", 0) or 0))


def signed_hls_master_url(
    base_url: str,
    upstream_url: str,
    *,
    relay: bool = False,
    height: Optional[int] = None,
    fps: Optional[int] = None,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
) -> str:
    """Mint a signed /proxy/hls-master URL for ``upstream_url``."""
    exp = int(time.time()) + ttl_seconds
    params = {"url": upstream_url, "sig": _sign(upstream_url, exp), "exp": str(exp)}
    if height:
        params["h"] = str(height)
    if fps:
        params["fps"] = str(fps)
    if relay:
        params["relay"] = "1"
    return f"{base_url.rstrip('/')}/proxy/hls-master?{urllib.parse.urlencode(params)}"


def upstream_url_from_signed(url: Optional[str]) -> Optional[str]:
    """Inverse of signed_hls_master_url (returns None for other URLs)."""
    if not url:
        return None
    parsed = urllib.parse.urlparse(url)
    if not parsed.path.endswith("/proxy/hls-master"):
        return None
    return (urllib.parse.parse_qs(parsed.query).get("url") or [None])[0]


# --- playlist parsing -------------------------------------------------------


class Variant:
    __slots__ = ("attrs", "tag", "url", "acont", "lang")

    def __init__(self, tag: str, url: str):
        self.tag = tag
        self.url = url
        self.attrs = _parse_attrs(tag)
        m = _ACONT_RE.search(urllib.parse.unquote(url))
        self.acont = (m.group(1) or "").lower() if m else ""
        self.lang = (m.group(2) or "").lower() if m else ""

    @property
    def is_dub(self) -> bool:
        return self.acont.startswith("dubbed")

    @property
    def height(self) -> int:
        res = self.attrs.get("RESOLUTION", "")
        try:
            return int(res.split("x", 1)[1]) if "x" in res else 0
        except ValueError:
            return 0

    @property
    def width(self) -> int:
        res = self.attrs.get("RESOLUTION", "")
        try:
            return int(res.split("x", 1)[0]) if "x" in res else 0
        except ValueError:
            return 0

    @property
    def bandwidth(self) -> int:
        try:
            return int(self.attrs.get("BANDWIDTH", "0") or 0)
        except ValueError:
            return 0

    @property
    def fps(self) -> Optional[int]:
        try:
            return round(float(self.attrs["FRAME-RATE"])) if "FRAME-RATE" in self.attrs else None
        except ValueError:
            return None

    @property
    def codecs(self) -> str:
        return self.attrs.get("CODECS", "")

    def describe(self) -> dict:
        return {
            "height": self.height,
            "width": self.width,
            "fps": self.fps,
            "codecs": self.codecs,
            "bandwidth": self.bandwidth,
            "audio": (self.lang or "original") if not self.is_dub else f"dub:{self.lang or '?'}",
        }


def _parse_attrs(tag_line: str) -> dict:
    _, _, attrs = tag_line.partition(":")
    return {k: v.strip('"') for k, v in _ATTR_RE.findall(attrs)}


def _parse_master(body: str) -> tuple[list[str], list[tuple[int, Variant]]]:
    """Return (header lines incl. placeholders, [(placeholder_index, Variant)])."""
    lines = body.splitlines()
    out: list[str] = []
    variants: list[tuple[int, Variant]] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("#EXT-X-STREAM-INF"):
            j = i + 1
            while j < len(lines) and (not lines[j].strip() or lines[j].startswith("#")):
                if lines[j].startswith("#"):
                    out.append(lines[j])
                j += 1
            if j < len(lines):
                variants.append((len(out), Variant(line, lines[j].strip())))
                out.append("")
                i = j + 1
                continue
        out.append(line)
        i += 1
    return out, variants


def _audio_pool(variants: list[Variant], audio_language: str) -> list[Variant]:
    """Variants carrying the wanted audio track (dub or original); falls back
    to the original (non-dub) track, then to everything."""
    if audio_language:
        want = audio_language.split("-")[0]
        matched = [v for v in variants if v.lang and v.lang.split("-")[0] == want]
        pool = matched or [v for v in variants if not v.is_dub]
    else:
        pool = [v for v in variants if not v.is_dub]
    return pool or variants


def _bounded(pool: list[Variant], min_height: int, max_height: int) -> list[Variant]:
    """Apply [min,max] height bounds; if that empties the pool keep the
    variants closest to the bounds so playback still works."""
    inside = [
        v for v in pool if (not min_height or v.height >= min_height) and (not max_height or v.height <= max_height)
    ]
    if inside:
        return inside
    if max_height and all(v.height > max_height for v in pool):
        h = min(v.height for v in pool)
    else:
        h = max(v.height for v in pool)
    return [v for v in pool if v.height == h]


def list_qualities(
    variants: list[Variant], *, audio_language: str = "", min_height: int = 0, max_height: int = 0
) -> list[Variant]:
    """One variant per (height, fps) — highest BANDWIDTH — sorted best first."""
    best: dict[tuple[int, Optional[int]], Variant] = {}
    for v in _bounded(_audio_pool(variants, audio_language), min_height, max_height):
        key = (v.height, v.fps)
        if key not in best or v.bandwidth > best[key].bandwidth:
            best[key] = v
    return sorted(best.values(), key=lambda v: (v.height, v.fps or 0, v.bandwidth), reverse=True)


def select_variant(
    variants: list[Variant],
    *,
    audio_language: str = "",
    min_height: int = 0,
    max_height: int = 0,
    height: Optional[int] = None,
    fps: Optional[int] = None,
) -> Optional[Variant]:
    """Pick the single variant mpv should play.

    With ``height`` (and optionally ``fps``): the exact quality the API
    advertised; falls back to the best quality <= height, then to the best
    within bounds. Without: the best quality within bounds.
    """
    if not variants:
        return None
    qualities = list_qualities(variants, audio_language=audio_language, min_height=min_height, max_height=max_height)
    if height:
        exact = [v for v in qualities if v.height == height and (fps is None or v.fps == fps)]
        if exact:
            return exact[0]
        same_h = [v for v in qualities if v.height == height]
        if same_h:
            return same_h[0]
        below = [v for v in qualities if v.height <= height]
        if below:
            return below[0]
    return qualities[0] if qualities else None


def filter_master(
    body: str,
    *,
    audio_language: str = "",
    min_height: int = 0,
    max_height: int = 0,
    height: Optional[int] = None,
    fps: Optional[int] = None,
) -> tuple[str, int, int, Optional[Variant]]:
    """Return (filtered_body, variants_before, variants_after, chosen).

    Falls back to the original body if there is nothing to select.
    """
    out, parsed = _parse_master(body)
    before = len(parsed)
    if before == 0:
        return body, 0, 0, None
    chosen = select_variant(
        [v for _, v in parsed],
        audio_language=audio_language,
        min_height=min_height,
        max_height=max_height,
        height=height,
        fps=fps,
    )
    if chosen is None:
        return body, before, before, None

    drop_idx = set()
    for idx, v in parsed:
        if v is chosen:
            out[idx] = f"{v.tag}\n{v.url}"
        else:
            drop_idx.add(idx)
    text = "\n".join(line for n, line in enumerate(out) if n not in drop_idx)
    if body.endswith("\n"):
        text += "\n"
    return text, before, 1, chosen


# --- upstream fetch ----------------------------------------------------------


async def fetch_master(url: str) -> str:
    transport = None
    if is_youtube_url(url):
        s = get_settings()
        proxy = s.effective_yt_egress_proxy()
        local_addr = local_address_for(s.effective_ip_family())
        if proxy or local_addr:
            transport = httpx.AsyncHTTPTransport(proxy=proxy, local_address=local_addr)
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(connect=10.0, read=20.0, write=10.0, pool=10.0),
        follow_redirects=True,
        **({"transport": transport} if transport else {}),
    ) as client:
        resp = await client.get(url, headers={"User-Agent": UPSTREAM_USER_AGENT})
    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail="Upstream error")
    return resp.text


# --- API post-processing -----------------------------------------------------


async def finalize_hls_streams(response, *, base_url: str = ""):
    """Replace the bare ``hlsUrl`` of a VOD response with one HLS formatStream
    per available quality (within the configured height bounds), each pointing
    at /proxy/hls-master with the matching ``h``/``fps`` so the player gets
    exactly the quality it picked.

    Also drops yt-dlp's per-variant m3u8 formatStreams (they all point at the
    unfiltered master and show up as a misleading "HLS 144p"). Live streams
    and responses without a filtered hlsUrl are returned untouched.
    """
    if not filter_enabled() or getattr(response, "liveNow", False):
        return response
    hls_url = getattr(response, "hlsUrl", None)
    parsed = urllib.parse.urlparse(hls_url or "")
    relay = (urllib.parse.parse_qs(parsed.query).get("relay") or ["0"])[0] == "1"
    if parsed.netloc:
        base_url = base_url or f"{parsed.scheme}://{parsed.netloc}"

    from routers.proxy._dash_hls import dash_enabled, dash_hls_streams

    if dash_enabled() and base_url and getattr(response, "videoId", None):
        try:
            streams = await dash_hls_streams(response.videoId, base_url=base_url, relay=relay)
        except Exception as e:
            logger.warning(f"[DASH-HLS] API planning failed for {response.videoId}: {e}")
            streams = []
        if streams:
            others = [f for f in (response.formatStreams or []) if "mpegurl" not in (f.type or "").lower()]
            response.formatStreams = streams + others
            response.hlsUrl = None
            return response

    upstream = upstream_url_from_signed(hls_url)
    if not upstream:
        return response

    try:
        from models import FormatStream

        t0 = time.monotonic()
        body = await fetch_master(upstream)
        _, variants = _parse_master(body)
        min_h, max_h = _height_bounds()
        qualities = list_qualities(
            [v for _, v in variants], audio_language=_audio_language(), min_height=min_h, max_height=max_h
        )
        qualities = [v for v in qualities if v.height]
        if not qualities:
            return response
        streams = []
        for v in qualities:
            codecs = ", ".join(c.strip() for c in v.codecs.split(",") if c.strip())
            label = f"{v.height}p" + (f"{v.fps}" if v.fps and v.fps > 30 else "")
            streams.append(
                FormatStream(
                    url=signed_hls_master_url(base_url, upstream, relay=relay, height=v.height, fps=v.fps),
                    itag=f"hls-{label}",
                    type=f'{HLS_MIME}; codecs="{codecs}"' if codecs else HLS_MIME,
                    quality=label,
                    container="hls",
                    resolution=f"{v.height}p",
                    width=v.width or None,
                    height=v.height,
                    encoding=None,
                    size=None,
                    fps=v.fps,
                    httpHeaders=None,
                )
            )
        others = [f for f in (response.formatStreams or []) if "mpegurl" not in (f.type or "").lower()]
        response.formatStreams = streams + others
        response.hlsUrl = None
        logger.info(
            f"[HLS-master] API: {len(variants)} variants -> {[s.quality for s in streams]} "
            f"audio={qualities[0].describe()['audio']} in {int((time.monotonic() - t0) * 1000)}ms"
        )
    except Exception as e:  # never break the video response over this
        logger.warning(f"[HLS-master] describe failed, keeping plain hlsUrl: {e}")
    return response


# --- endpoint ----------------------------------------------------------------


@router.get("/hls-master")
async def hls_master(
    request: Request, url: str, sig: str, exp: int, relay: int = 0, h: Optional[int] = None, fps: Optional[int] = None
):
    if int(time.time()) > exp:
        raise HTTPException(status_code=403, detail="URL expired")
    if not _verify(url, exp, sig):
        raise HTTPException(status_code=403, detail="Invalid signature")
    if not is_safe_url(url):
        raise HTTPException(status_code=403, detail="URL targets restricted network resources")

    t0 = time.monotonic()
    try:
        body = await fetch_master(url)
    except httpx.RequestError as e:
        logger.warning(f"[HLS-master] upstream fetch failed: {e}")
        raise HTTPException(status_code=502, detail=f"Upstream fetch failed: {e}") from e

    before = after = None
    chosen = None
    if filter_enabled():
        min_h, max_h = _height_bounds()
        body, before, after, chosen = filter_master(
            body,
            audio_language=_audio_language(),
            min_height=min_h,
            max_height=max_h,
            height=h,
            fps=fps,
        )

    if relay:
        base_url_self = f"{request.url.scheme}://{request.url.netloc}"
        body = _rewrite_hls(body, base_url=base_url_self, manifest_url=url, ttl_seconds=DEFAULT_TTL_SECONDS)

    logger.info(
        f"[HLS-master] variants {before}->{after} chosen={chosen.describe() if chosen else None} "
        f"relay={bool(relay)} in {int((time.monotonic() - t0) * 1000)}ms"
    )
    return Response(content=body, media_type=HLS_MIME, headers={"cache-control": "no-store"})
