"""URL resolution, header filtering, and language maps."""

import re
import urllib.parse
from typing import Dict, Optional

# Sensitive HTTP headers that should never be exposed to clients
# These may contain admin-stored credentials (cookies, auth tokens, API keys)
SENSITIVE_HEADERS = frozenset({
    "authorization",
    "cookie",
    "set-cookie",
    "x-api-key",
    "x-auth-token",
    "x-token",
    "proxy-authorization",
    "www-authenticate",
})


def _filter_sensitive_headers(headers: Optional[Dict[str, str]]) -> Optional[Dict[str, str]]:
    """Remove sensitive headers before returning to clients.

    This prevents credential exposure where admin-stored cookies,
    Authorization headers, or API keys could leak to API consumers.

    Args:
        headers: HTTP headers dict from yt-dlp format info

    Returns:
        Filtered headers dict, or None if empty/all filtered
    """
    if not headers:
        return None

    filtered = {
        k: v
        for k, v in headers.items()
        if k.lower() not in SENSITIVE_HEADERS
        and not k.lower().startswith("x-secret")
        and not k.lower().startswith("x-password")
    }
    return filtered if filtered else None


HLS_MANIFEST_CONTENT_TYPE = "application/vnd.apple.mpegurl"

# MIME types that identify an HLS playlist (master or media) rather than media
HLS_MIME_TYPES = (HLS_MANIFEST_CONTENT_TYPE, "application/x-mpegurl")


def is_hls_manifest(content_type: Optional[str], url: str) -> bool:
    """Return True when the stream URL is an HLS playlist, not media."""
    mime = (content_type or "").split(";")[0].strip().lower()
    if mime in HLS_MIME_TYPES:
        return True
    return url.split("?", 1)[0].endswith(".m3u8")


def relay_manifest_url(
    url: Optional[str],
    *,
    base_url: str,
    proxy_mode: str,
    content_type: str = HLS_MANIFEST_CONTENT_TYPE,
) -> Optional[str]:
    """Wrap a manifest URL in a signed /proxy/relay link when proxying is on.

    Manifests always take the relay, in both proxy modes - not only in
    ``"relay"``. A client cannot fetch a manifest straight from the CDN (the
    browser blocks it, because the CDN sends no CORS headers), and
    ``/proxy/fast/`` would serve the playlist unmodified, so the segments inside
    it would still point at the CDN - which answers 403 to every client on a
    different network than the server. ``/proxy/relay`` rewrites the segment
    URLs in the body, so the whole stream stays relayed.
    """
    if not url or proxy_mode == "off" or not base_url:
        return url
    from routers.proxy import signed_relay_url

    return signed_relay_url(base_url, url, content_type=content_type)


# Language name to code mapping for caption conversion
_LANG_NAME_TO_CODE = {
    "english": "en",
    "japanese": "ja",
    "spanish": "es",
    "french": "fr",
    "german": "de",
    "italian": "it",
    "portuguese": "pt",
    "russian": "ru",
    "korean": "ko",
    "chinese": "zh",
    "arabic": "ar",
    "hindi": "hi",
    "turkish": "tr",
    "polish": "pl",
    "dutch": "nl",
    "swedish": "sv",
    "norwegian": "no",
    "danish": "da",
    "finnish": "fi",
    "greek": "el",
    "hebrew": "he",
    "thai": "th",
    "vietnamese": "vi",
    "indonesian": "id",
    "malay": "ms",
    "filipino": "fil",
    "czech": "cs",
    "romanian": "ro",
    "hungarian": "hu",
    "ukrainian": "uk",
    "catalan": "ca",
    "croatian": "hr",
    "serbian": "sr",
    "slovak": "sk",
    "slovenian": "sl",
    "bulgarian": "bg",
    "lithuanian": "lt",
    "latvian": "lv",
    "estonian": "et",
    "persian": "fa",
    "bengali": "bn",
    "tamil": "ta",
    "telugu": "te",
    "kannada": "kn",
    "malayalam": "ml",
    "marathi": "mr",
    "gujarati": "gu",
    "punjabi": "pa",
    "nepali": "ne",
    "sinhala": "si",
    "burmese": "my",
    "khmer": "km",
    "lao": "lo",
    "mongolian": "mn",
    "tibetan": "bo",
    "georgian": "ka",
    "armenian": "hy",
    "azerbaijani": "az",
    "kazakh": "kk",
    "uzbek": "uz",
    "afrikaans": "af",
    "swahili": "sw",
    "zulu": "zu",
    "xhosa": "xh",
    "welsh": "cy",
    "irish": "ga",
    "scots gaelic": "gd",
    "basque": "eu",
    "galician": "gl",
    "icelandic": "is",
    "albanian": "sq",
    "macedonian": "mk",
    "bosnian": "bs",
    "maltese": "mt",
    "luxembourgish": "lb",
    "belarusian": "be",
}

# ISO 3166-1 alpha-2 region codes extracted from caption labels
_REGION_NAME_TO_CODE = {
    "united states": "US",
    "united kingdom": "GB",
    "brazil": "BR",
    "portugal": "PT",
    "mexico": "MX",
    "spain": "ES",
    "canada": "CA",
    "australia": "AU",
    "india": "IN",
    "south africa": "ZA",
    "ireland": "IE",
    "new zealand": "NZ",
    "hong kong": "HK",
    "taiwan": "TW",
    "singapore": "SG",
    "philippines": "PH",
    "latin america": "419",  # UN M.49 code for Latin America
}


def _label_to_lang_code(label: str) -> str:
    """Extract language code from caption label like 'English (auto-generated)'."""
    # Remove common suffixes
    clean = label.lower()
    clean = re.sub(r"\s*\(auto[^)]*\)", "", clean)  # Remove (auto-generated), (auto), etc.
    clean = re.sub(r"\s*\([^)]*\)", "", clean)  # Remove any other parentheses
    clean = clean.strip()

    # Direct lookup
    if clean in _LANG_NAME_TO_CODE:
        return _LANG_NAME_TO_CODE[clean]

    # Try first word only (e.g., "Chinese (Simplified)" -> "chinese")
    first_word = clean.split()[0] if clean else ""
    if first_word in _LANG_NAME_TO_CODE:
        return _LANG_NAME_TO_CODE[first_word]

    return ""


def _extract_region_from_label(label: str) -> str:
    """Extract region code from caption label like 'English (United States)'."""
    match = re.search(r"\(([^)]+)\)", label)
    if not match:
        return ""

    region_text = match.group(1).lower()

    # Skip auto-generated markers
    if "auto" in region_text:
        return ""

    return _REGION_NAME_TO_CODE.get(region_text, "")


def resolve_invidious_url(url: str, invidious_base_url: str) -> str:
    """Resolve relative/protocol-relative URLs from Invidious to absolute URLs.

    Invidious may return URLs in several formats:
    - Protocol-relative: //yt3.ggpht.com/... or //i.ytimg.com/...
    - Relative paths: /vi/VIDEO_ID/maxres.jpg or /ggpht/...
    - Absolute URLs: https://... (returned unchanged)

    Args:
        url: The URL from Invidious API response
        invidious_base_url: The Invidious instance base URL (e.g., https://invidious.example.com)

    Returns:
        Absolute URL, or original value if empty/invalid
    """
    if not url:
        return url

    # Protocol-relative URLs (e.g., //yt3.ggpht.com/...)
    if url.startswith("//"):
        return "https:" + url

    # Relative paths (e.g., /vi/VIDEO_ID/maxres.jpg)
    if url.startswith("/"):
        base = invidious_base_url.rstrip("/") if invidious_base_url else ""
        return base + url

    # Already absolute or other format - return as-is
    return url


def _xtags_from_url(url: Optional[str]) -> Dict[str, str]:
    """Parse YouTube googlevideo `xtags=` query param into key/value pairs.

    YouTube encodes per-track audio metadata in the `xtags` query param of
    googlevideo URLs, e.g. `xtags=acont%3Doriginal%3Alang%3Den-US`. After
    URL-decoding, the value is `:`-separated `key=value` pairs:
    `acont=original:lang=en-US:drc=1`.

    Returns an empty dict if the URL has no xtags or it cannot be parsed.
    """
    if not url:
        return {}
    parsed = urllib.parse.urlparse(url)
    qs = urllib.parse.parse_qs(parsed.query)
    raw = qs.get("xtags", [None])[0]
    if not raw:
        return {}
    out: Dict[str, str] = {}
    for pair in raw.split(":"):
        if "=" in pair:
            k, v = pair.split("=", 1)
            out[k] = v
    return out


def _enrich_audio_display_name(display_name: Optional[str], xtags: Dict[str, str]) -> Optional[str]:
    """Annotate an audio track displayName so the iOS client can detect track type.

    iOS Yattee identifies the original audio by checking whether displayName
    contains the substring "original" (case-insensitive); auto-dubbed tracks
    are detected via "Auto-dubbed". When the upstream URL's xtags mark the
    track as `acont=original` or `acont=dubbed-auto` but the displayName
    lacks the keyword (common with Invidious responses), append it.

    Pass-through when there is no useful xtags marker.
    """
    if not xtags:
        return display_name
    acont = xtags.get("acont")
    lang = xtags.get("lang")
    base = (display_name or lang or "").strip()

    if acont == "original":
        if not base:
            return "original"
        if "original" in base.lower():
            return base
        return f"{base} original"

    if acont == "dubbed-auto":
        if not base:
            return "Auto-dubbed"
        if "auto-dubbed" in base.lower():
            return base
        return f"{base} (Auto-dubbed)"

    return display_name


def _convert_invidious_thumbnail_to_proxy(url: str, base_url: str, token: str = "") -> str:
    """Convert Invidious thumbnail URL to local proxy URL.

    Invidious format: https://invidious.example.com/vi/{video_id}/{filename}
    Proxy format: {base_url}/api/v1/thumbnails/{video_id}/{filename}
    """
    # Match pattern: /vi/{video_id}/{filename}
    match = re.search(r"/vi/([^/]+)/([^/?]+)", url)
    if match:
        video_id = match.group(1)
        filename = match.group(2)
        proxy_url = f"{base_url}/api/v1/thumbnails/{video_id}/{filename}"
        if token:
            proxy_url = f"{proxy_url}?token={token}"
        return proxy_url
    return url  # Return original if pattern doesn't match
