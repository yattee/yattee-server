"""Core yt-dlp execution: run_ytdlp() and argument processing."""

import asyncio
import logging
from typing import List, Optional, Tuple

from settings import get_settings
from ytdlp_wrapper._sanitize import YtDlpError, is_valid_url

logger = logging.getLogger(__name__)


def _separate_flags_and_urls(args: tuple) -> Tuple[List[str], List[str]]:
    """Separate yt-dlp arguments into flags and URLs.

    Returns:
        Tuple of (flags_list, urls_list)
    """
    flags = []
    urls = []
    for arg in args:
        if isinstance(arg, str) and (arg.startswith("http://") or arg.startswith("https://")):
            urls.append(arg)
        else:
            flags.append(arg)
    return flags, urls


async def run_ytdlp(*args: str, timeout: Optional[int] = None, url: Optional[str] = None) -> str:
    """Run yt-dlp with given arguments and return stdout.

    Security: URLs are automatically separated from flags and placed after '--'
    to prevent command injection via URLs starting with '-'.

    Args:
        *args: yt-dlp arguments
        timeout: Optional timeout in seconds
        url: Optional URL hint for credential lookup (auto-detected from args if not provided)

    Returns:
        stdout from yt-dlp
    """
    s = get_settings()
    timeout = timeout or s.ytdlp_timeout

    # Separate flags and URLs to prevent command injection
    flags, urls = _separate_flags_and_urls(args)

    # Try to extract URL from args if not provided
    if url is None and urls:
        url = urls[0]

    # Validate all URLs before execution
    for u in urls:
        if not is_valid_url(u):
            raise ValueError(f"Invalid URL format: {u}")

    # Get credentials for this URL
    cred_args = []
    temp_files = []

    if url:
        try:
            # Import here to avoid circular imports
            import credentials

            cred_args, temp_files = await credentials.get_credentials_for_url(url)
            if cred_args:
                logger.debug(f"Injecting {len(cred_args)} credential args for URL: {url}")
        except (ValueError, KeyError, OSError) as e:
            logger.warning(f"Failed to load credentials for {url}: {e}")

    # Build final args: credentials + flags + '--' + urls
    # The '--' separator prevents URLs from being interpreted as flags
    all_args = list(cred_args) + flags
    if urls:
        all_args.append("--")
        all_args.extend(urls)

    proc = await asyncio.create_subprocess_exec(
        s.ytdlp_path, *all_args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )

    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        # Clean up temp files
        if temp_files:
            import credentials

            credentials.cleanup_temp_files(temp_files)
        raise YtDlpError(f"yt-dlp timed out after {timeout} seconds")

    # Clean up temp files
    if temp_files:
        import credentials

        credentials.cleanup_temp_files(temp_files)

    if proc.returncode != 0:
        error_msg = stderr.decode().strip() if stderr else "Unknown error"
        logger.error(f"yt-dlp failed (exit code {proc.returncode}) for URL: {url}")
        logger.error(f"yt-dlp stderr: {error_msg}")
        raise YtDlpError(f"yt-dlp failed: {error_msg}")

    logger.debug(f"yt-dlp succeeded for URL: {url}")

    return stdout.decode()
