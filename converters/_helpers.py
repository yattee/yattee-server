"""URL resolution, header filtering, and language maps."""

import re
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
