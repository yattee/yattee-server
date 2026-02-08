"""Generic URL extraction (extract_url, extract_channel_url)."""

import asyncio
import json
import logging

import config
from ytdlp_wrapper._cache import get_channel_cache, get_extract_cache
from ytdlp_wrapper._core import run_ytdlp
from ytdlp_wrapper._sanitize import YtDlpError, is_valid_url

logger = logging.getLogger(__name__)


async def extract_url(url: str, use_cache: bool = True, max_retries: int = 3) -> dict:
    """Extract video info from any URL that yt-dlp supports.

    This is the generic extraction function for non-YouTube sites.
    Unlike get_video_info(), this accepts arbitrary URLs and doesn't
    use YouTube-specific options.

    Includes retry logic for transient failures (e.g., anti-bot 403 errors
    from sites like Dailymotion that require initial warm-up).

    Args:
        url: Full URL to extract (e.g., https://vimeo.com/12345)
        use_cache: Whether to use cached results
        max_retries: Maximum number of retry attempts (default: 3)

    Returns:
        yt-dlp video info dict with additional 'extractor' and 'original_url' fields
    """
    if not is_valid_url(url):
        raise ValueError(f"Invalid URL: {url}")

    # Use URL hash as cache key
    cache_key = f"extract:{hash(url)}"
    extract_cache = get_extract_cache()
    if use_cache and cache_key in extract_cache:
        return extract_cache[cache_key]

    last_error = None
    for attempt in range(max_retries):
        try:
            # Build args - only skip TLS verification if explicitly enabled
            ytdlp_args = [
                "-j",
                "--no-download",
                "--no-warnings",
                "--no-playlist",
            ]
            if config.YTDLP_SKIP_TLS_VERIFY:
                ytdlp_args.append("--no-check-certificates")
            ytdlp_args.extend([
                "--remote-components",
                "ejs:github",  # Required for YouTube JS challenge solving
            ])

            stdout = await run_ytdlp(*ytdlp_args, url)

            info = json.loads(stdout)

            # Ensure extractor info is present
            if "extractor" not in info:
                info["extractor"] = info.get("extractor_key", "generic")

            # Store original URL for re-extraction
            info["original_url"] = url

            extract_cache[cache_key] = info
            return info

        except YtDlpError as e:
            last_error = e
            if attempt < max_retries - 1:
                # Exponential backoff: 1s, 2s, 4s
                delay = 2**attempt
                logger.warning(
                    f"Extract attempt {attempt + 1}/{max_retries} failed for {url}, retrying in {delay}s: {e}"
                )
                await asyncio.sleep(delay)
            continue

    # All retries exhausted
    raise last_error


async def extract_channel_url(url: str, page: int = 1, per_page: int = 30, use_cache: bool = True) -> dict:
    """Extract channel/user videos from any URL that yt-dlp supports.

    This is the generic channel extraction function for non-YouTube sites.
    It fetches full video metadata (not flat-playlist mode) so we get
    titles, thumbnails, durations, etc.

    Args:
        url: Full channel/user URL (e.g., https://vimeo.com/username)
        page: Page number (1-based)
        per_page: Results per page
        use_cache: Whether to use cached results

    Returns:
        Dict with channel info and video entries

    Raises:
        ValueError: If URL is invalid
        YtDlpError: If extraction fails (site may not support channel extraction)
    """
    if not is_valid_url(url):
        raise ValueError(f"Invalid URL: {url}")

    # Use URL + page as cache key
    cache_key = f"ext_channel:{hash(url)}:p{page}"
    channel_cache = get_channel_cache()
    if use_cache and cache_key in channel_cache:
        return channel_cache[cache_key]

    # Calculate which items to fetch
    start = (page - 1) * per_page + 1
    end = start + per_page - 1

    # Note: We don't use --flat-playlist here because many extractors
    # (like Dailymotion) don't return titles/thumbnails in flat mode.
    # This is slower but gives us full video metadata.
    ytdlp_args = ["-j", "--no-download", "--no-warnings"]
    if config.YTDLP_SKIP_TLS_VERIFY:
        ytdlp_args.append("--no-check-certificates")
    ytdlp_args.extend(["--playlist-items", f"{start}:{end}"])

    stdout = await run_ytdlp(*ytdlp_args, url)

    entries = []
    channel_info = {}

    for line in stdout.strip().split("\n"):
        if line:
            try:
                data = json.loads(line)
                entries.append(data)
            except json.JSONDecodeError:
                continue

    # Extract channel info from first entry if available
    if entries:
        first = entries[0]
        channel_info = {
            "channel": first.get("uploader") or first.get("channel") or first.get("playlist_uploader") or "",
            "channel_id": (
                first.get("uploader_id") or first.get("channel_id") or first.get("playlist_uploader_id") or ""
            ),
            "channel_url": url,
            "extractor": first.get("extractor_key") or first.get("extractor") or "generic",
        }

    result = {"entries": entries, **channel_info}

    # Cache the result
    channel_cache[cache_key] = result
    return result
