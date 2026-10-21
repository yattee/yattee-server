"""Core yt-dlp execution: run_ytdlp() and argument processing."""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import egress
from settings import get_settings
from ytdlp_wrapper._sanitize import YtDlpError, is_valid_url

logger = logging.getLogger(__name__)


def ytdlp_pot_args(s) -> List[str]:
    """PO token provider args from settings.

    The bgutil plugin is always installed (requirements.txt), so when POT is
    disabled we pass fetch_pot=never to stop the plugin from pinging its
    default 127.0.0.1:4416 on every call. When enabled, the base_url is only
    emitted while a provider is actually reachable (external URL configured,
    or the bundled process reports healthy) — otherwise every yt-dlp call
    would pay for a failing ping.
    """
    if not s.yt_pot_enabled:
        return ["--extractor-args", "youtube:fetch_pot=never"]
    url = s.effective_pot_provider_url()
    if url:
        return ["--extractor-args", f"youtubepot-bgutilhttp:base_url={url}"]
    import pot_provider  # late import: settings <-> pot_provider cycle

    if pot_provider.manager.is_healthy():
        return ["--extractor-args", f"youtubepot-bgutilhttp:base_url={pot_provider.DEFAULT_BASE_URL}"]
    return []


def ytdlp_network_args(s) -> List[str]:
    """Network-related yt-dlp args from settings: egress proxy + forced IP family.

    effective_ip_family() returns "auto" while the proxy is active, so the
    force flag never applies to the hop to the proxy.
    """
    args = []
    proxy = s.effective_yt_egress_proxy()
    if proxy:
        args.extend(["--proxy", proxy])
    family = s.effective_ip_family()
    if family == "ipv6":
        args.append("--force-ipv6")
    elif family == "ipv4":
        args.append("--force-ipv4")
    args.extend(ytdlp_pot_args(s))
    return args


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


@dataclass
class YtDlpRun:
    """Result of a yt-dlp run, with the cookie credential ids that were injected."""

    stdout: str
    stderr: str = ""
    cookie_ids: List[int] = field(default_factory=list)


async def run_ytdlp(*args: str, timeout: Optional[int] = None, url: Optional[str] = None) -> str:
    """Run yt-dlp with given arguments and return stdout. See run_ytdlp_ex."""
    run = await run_ytdlp_ex(*args, timeout=timeout, url=url)
    return run.stdout


async def run_ytdlp_ex(
    *args: str, timeout: Optional[int] = None, url: Optional[str] = None, use_credentials: bool = True
) -> YtDlpRun:
    """Run yt-dlp with given arguments and return stdout/stderr plus cookie attribution.

    Security: URLs are automatically separated from flags and placed after '--'
    to prevent command injection via URLs starting with '-'.

    When account cookies are injected, --no-warnings is dropped so yt-dlp's
    "cookies are no longer valid" warning reaches stderr, where
    cookie_health can act on it (stdout JSON is unaffected).

    Args:
        *args: yt-dlp arguments
        timeout: Optional timeout in seconds
        url: Optional URL hint for credential lookup (auto-detected from args if not provided)
        use_credentials: Set False to run anonymously (retry path for stale cookies)
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
    cookie_ids: List[int] = []

    if url and use_credentials:
        try:
            # Import here to avoid circular imports
            import credentials

            resolved = await credentials.get_credentials_for_url(url)
            cred_args, temp_files, cookie_ids = resolved.args, resolved.temp_files, resolved.cookie_ids
            if cred_args:
                logger.debug(f"Injecting {len(cred_args)} credential args for URL: {url}")
        except (ValueError, KeyError, OSError) as e:
            logger.warning(f"Failed to load credentials for {url}: {e}")

    if cookie_ids and "--no-warnings" in flags:
        flags = [f for f in flags if f != "--no-warnings"]

    # Build final args: network (proxy/IP family) + credentials + flags + '--' + urls
    # The '--' separator prevents URLs from being interpreted as flags
    try:
        network_args = ytdlp_network_args(s)
    except egress.ProxyConfigError as e:
        raise YtDlpError(f"YouTube egress proxy configuration is invalid: {e}", cookie_ids=cookie_ids) from e
    all_args = network_args + list(cred_args) + flags
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
        raise YtDlpError(f"yt-dlp timed out after {timeout} seconds", cookie_ids=cookie_ids)

    stderr_text = stderr.decode(errors="replace").strip() if stderr else ""

    # Keep the normal extractor path first because many videos already work.
    # If YouTube selectively returns its anonymous-player bot check, retry only
    # that failure through the mweb player. With POT enabled, bgutil supplies
    # the matching GVS token through the configured provider.
    bot_check = "sign in to confirm you" in stderr_text.lower() and "not a bot" in stderr_text.lower()
    youtube_url = bool(url and ("youtube.com/" in url or "youtu.be/" in url))
    has_player_client = any(
        isinstance(arg, str) and arg.startswith("youtube:") and "player_client=" in arg.replace("-", "_")
        for arg in flags
    )
    if proc.returncode != 0 and bot_check and youtube_url and s.yt_pot_enabled and not has_player_client:
        logger.info("[Egress] stage=yt-dlp fallback=mweb+pot reason=youtube-bot-check")
        retry_args = network_args + list(cred_args) + flags + [
            "--extractor-args",
            "youtube:player_client=mweb",
        ]
        if urls:
            retry_args.append("--")
            retry_args.extend(urls)
        retry_proc = await asyncio.create_subprocess_exec(
            s.ytdlp_path, *retry_args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        try:
            stdout, stderr = await asyncio.wait_for(retry_proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            retry_proc.kill()
            await retry_proc.wait()
            if temp_files:
                import credentials

                credentials.cleanup_temp_files(temp_files)
            raise YtDlpError(f"yt-dlp mweb fallback timed out after {timeout} seconds", cookie_ids=cookie_ids)
        proc = retry_proc
        stderr_text = stderr.decode(errors="replace").strip() if stderr else ""
        if proc.returncode == 0:
            logger.info("[Egress] stage=yt-dlp fallback=mweb+pot result=success")
        else:
            logger.warning("[Egress] stage=yt-dlp fallback=mweb+pot result=failed")

    # Clean up credential files only after the optional retry because that
    # retry may need to reuse the same cookie file.
    if temp_files:
        import credentials

        credentials.cleanup_temp_files(temp_files)
    if cookie_ids:
        import cookie_health

        cookie_health.inspect_ytdlp_stderr(stderr_text, cookie_ids)

    if proc.returncode != 0:
        # Never let the egress proxy URL / credentials reach logs or API errors.
        raw_proxy = s.yt_egress_proxy if s.yt_egress_proxy_enabled else None
        stderr_text = egress.redact_secrets(stderr_text, raw_proxy)
        error_msg = stderr_text or "Unknown error"
        logger.error(f"yt-dlp failed (exit code {proc.returncode}) for URL: {url}")
        logger.error(f"yt-dlp stderr: {error_msg}")
        if raw_proxy:
            logger.error(
                "[Egress] stage=yt-dlp cause=%s proxy=%s",
                egress.classify_egress_failure(error_msg, proxy_configured=True),
                egress.redact_proxy_url(raw_proxy),
            )
        raise YtDlpError(f"yt-dlp failed: {error_msg}", stderr=stderr_text, cookie_ids=cookie_ids)

    logger.debug(f"yt-dlp succeeded for URL: {url}")

    return YtDlpRun(stdout=stdout.decode(), stderr=stderr_text, cookie_ids=cookie_ids)
