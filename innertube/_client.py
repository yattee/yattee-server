"""InnerTube API client - direct access to YouTube's internal API."""

import asyncio
import logging
import os
import tempfile
from typing import Any, Dict, Optional

import httpx
from cryptography.fernet import InvalidToken

import config
import database
import encryption

logger = logging.getLogger("innertube")

# InnerTube API base URL
INNERTUBE_API_URL = "https://www.youtube.com/youtubei/v1"

# Public API key embedded in YouTube's web client (not a secret)
INNERTUBE_API_KEY = "AIzaSyAO_FJ2SlqU8Q4STEHLGCilw_Y9_11qcW8"

# WEB client context
INNERTUBE_CLIENT_NAME = "WEB"
INNERTUBE_CLIENT_VERSION = "2.20260409.02.00"

# Shared HTTP client
_client: Optional[httpx.AsyncClient] = None
_client_version: Optional[str] = None
_client_version_fetched: float = 0


class InnerTubeError(Exception):
    """Error from InnerTube API."""

    def __init__(self, message: str, status_code: Optional[int] = None, is_retryable: bool = False):
        super().__init__(message)
        self.status_code = status_code
        self.is_retryable = is_retryable


async def _get_client_version() -> str:
    """Get the current YouTube client version, refreshing from YouTube periodically."""
    global _client_version, _client_version_fetched
    import re
    import time

    # Cache for 24 hours
    now = time.time()
    if _client_version and (now - _client_version_fetched) < 86400:
        return _client_version

    try:
        client = await get_client()
        resp = await client.get("https://www.youtube.com/")
        match = re.search(r'"INNERTUBE_CLIENT_VERSION":"([^"]+)"', resp.text)
        if match:
            _client_version = match.group(1)
            _client_version_fetched = now
            logger.info(f"[InnerTube] Refreshed client version: {_client_version}")
            return _client_version
    except Exception as e:
        logger.debug(f"[InnerTube] Failed to fetch client version: {e}")

    return _client_version or INNERTUBE_CLIENT_VERSION


def _build_context(language: str = "en", region: str = "US", client_version: Optional[str] = None) -> Dict[str, Any]:
    """Build the InnerTube client context."""
    return {
        "client": {
            "clientName": INNERTUBE_CLIENT_NAME,
            "clientVersion": client_version or INNERTUBE_CLIENT_VERSION,
            "hl": language,
            "gl": region,
        }
    }


def _load_cookies_from_netscape(content: str) -> Dict[str, str]:
    """Parse a Netscape-format cookie file and extract YouTube cookies.

    Returns dict of cookie name -> value for youtube.com domains.
    """
    cookies = {}
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 7:
            continue
        domain, _flag, _path, _secure, _expiry, name, value = parts[:7]
        if "youtube.com" in domain or "google.com" in domain:
            cookies[name] = value
    return cookies


async def _load_youtube_cookies() -> Dict[str, str]:
    """Load YouTube cookies from the credential system.

    Checks the database for cookies_file or cookies_browser credentials
    matching the YouTube site, decrypts them, and returns as a dict.
    """
    try:
        sites = database.get_enabled_sites()
    except Exception as e:
        logger.debug(f"[InnerTube] Could not load sites for cookies: {e}")
        return {}

    cookies = {}

    for site in sites:
        if site.get("extractor_pattern", "").lower() != "youtube":
            continue

        for cred in site.get("credentials", []):
            cred_type = cred["credential_type"]
            value = cred["value"]

            if cred.get("is_encrypted"):
                try:
                    value = encryption.decrypt(value)
                except InvalidToken as e:
                    logger.error(f"[InnerTube] Failed to decrypt credential: {e}")
                    continue

            if cred_type == "cookies_file":
                parsed = _load_cookies_from_netscape(value)
                cookies.update(parsed)

            elif cred_type == "cookies_browser":
                browser_cookies = await _export_browser_cookies(cred.get("key") or value)
                cookies.update(browser_cookies)

    return cookies


async def _export_browser_cookies(browser_spec: str) -> Dict[str, str]:
    """Export YouTube cookies from a browser using yt-dlp.

    Uses yt-dlp's --cookies-from-browser to export cookies to a temp file,
    then parses the Netscape-format file.
    """
    from settings import get_settings

    s = get_settings()
    ytdlp_path = s.ytdlp_path or "yt-dlp"

    temp_path = None
    try:
        fd, temp_path = tempfile.mkstemp(suffix=".txt", dir=os.path.join(config.DATA_DIR, "temp"))
        os.close(fd)
        os.chmod(temp_path, 0o600)

        cmd = [ytdlp_path, "--cookies-from-browser", browser_spec, "--cookies", temp_path, "--skip-download", "https://www.youtube.com"]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await asyncio.wait_for(proc.wait(), timeout=30)

        if proc.returncode == 0 and os.path.exists(temp_path):
            with open(temp_path) as f:
                return _load_cookies_from_netscape(f.read())
    except Exception as e:
        logger.warning(f"[InnerTube] Failed to export browser cookies: {e}")
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.unlink(temp_path)
            except OSError:
                pass

    return {}


def _format_cookie_header(cookies: Dict[str, str]) -> str:
    """Format cookies dict as a Cookie header value."""
    return "; ".join(f"{k}={v}" for k, v in cookies.items())


def _generate_sapisidhash(cookies: Dict[str, str]) -> Optional[str]:
    """Generate SAPISIDHASH authorization header from cookies.

    YouTube requires this header for authenticated InnerTube requests.
    It's derived from the SAPISID cookie, current timestamp, and origin.
    This is the same mechanism yt-dlp uses.
    """
    import hashlib
    import time

    sapisid = cookies.get("SAPISID") or cookies.get("__Secure-3PAPISID")
    if not sapisid:
        return None

    origin = "https://www.youtube.com"
    ts = int(time.time())
    hash_input = f"{ts} {sapisid} {origin}"
    hash_value = hashlib.sha1(hash_input.encode()).hexdigest()
    return f"SAPISIDHASH {ts}_{hash_value}"


async def get_client() -> httpx.AsyncClient:
    """Get or create the shared HTTP client."""
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            timeout=httpx.Timeout(15),
            follow_redirects=True,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
                ),
                "Accept-Language": "en-US,en;q=0.9",
                "Origin": "https://www.youtube.com",
                "Referer": "https://www.youtube.com/",
            },
        )
    return _client


async def innertube_post(endpoint: str, body: Dict[str, Any], use_cookies: bool = True) -> Any:
    """Make a POST request to the InnerTube API.

    Args:
        endpoint: API endpoint (e.g., "next", "browse", "search")
        body: Request body (context will be added automatically)
        use_cookies: Whether to include YouTube cookies from credentials

    Returns:
        Parsed JSON response

    Raises:
        InnerTubeError: If InnerTube is disabled or on API errors
    """
    from settings import get_settings

    if not get_settings().innertube_enabled:
        raise InnerTubeError("InnerTube is disabled", is_retryable=False)

    client = await get_client()
    url = f"{INNERTUBE_API_URL}/{endpoint}?key={INNERTUBE_API_KEY}"

    # Add client context to body with dynamic version
    if "context" not in body:
        version = await _get_client_version()
        body["context"] = _build_context(client_version=version)

    headers = {"Content-Type": "application/json"}

    # Load and inject cookies + SAPISIDHASH auth
    if use_cookies:
        try:
            cookies = await _load_youtube_cookies()
            if cookies:
                headers["Cookie"] = _format_cookie_header(cookies)
                sapisidhash = _generate_sapisidhash(cookies)
                if sapisidhash:
                    headers["Authorization"] = sapisidhash
                logger.debug(f"[InnerTube] Using {len(cookies)} cookies for {endpoint} (auth={bool(sapisidhash)})")
            else:
                logger.debug("[InnerTube] No YouTube cookies found in credentials")
        except Exception as e:
            logger.warning(f"[InnerTube] Cookie loading failed (continuing without): {e}")

    max_retries = 2
    base_delay = 1.0
    last_error: Optional[InnerTubeError] = None
    retryable_codes = {500, 502, 503, 504, 408, 429}

    for attempt in range(max_retries + 1):
        if attempt > 0:
            delay = base_delay * (2 ** (attempt - 1))
            logger.info(f"[InnerTube] Retry {attempt}/{max_retries} for {endpoint} after {delay:.1f}s")
            await asyncio.sleep(delay)

        try:
            response = await client.post(url, json=body, headers=headers)
            response.raise_for_status()
            data = response.json()

            # Check for InnerTube-level errors
            if "error" in data:
                error = data["error"]
                msg = error.get("message", str(error))
                code = error.get("code", 0)
                raise InnerTubeError(msg, status_code=code, is_retryable=code in retryable_codes)

            return data

        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            msg = f"HTTP {status}: {e.response.text[:200]}"
            logger.warning(f"[InnerTube] Error: {endpoint} - {msg}")
            last_error = InnerTubeError(msg, status_code=status, is_retryable=status in retryable_codes)
            if not last_error.is_retryable:
                raise last_error

        except httpx.TimeoutException as e:
            msg = f"Timeout: {e}"
            logger.warning(f"[InnerTube] Timeout: {endpoint}")
            last_error = InnerTubeError(msg, is_retryable=True)

        except httpx.RequestError as e:
            msg = f"Request failed: {e}"
            logger.warning(f"[InnerTube] Request error: {endpoint} - {e}")
            last_error = InnerTubeError(msg, is_retryable=True)

        except InnerTubeError:
            raise

        except (ValueError, TypeError) as e:
            raise InnerTubeError(f"Unexpected error: {e}", is_retryable=False)

    logger.warning(f"[InnerTube] All {max_retries} retries exhausted for {endpoint}")
    if last_error:
        raise last_error
    raise InnerTubeError(f"Failed after {max_retries} retries", is_retryable=True)


async def innertube_get(url: str, use_cookies: bool = True) -> httpx.Response:
    """Make a GET request with optional YouTube cookies.

    Used for non-InnerTube endpoints like search suggestions or thumbnail proxy.

    Returns the raw httpx.Response for flexible handling.
    """
    from settings import get_settings

    if not get_settings().innertube_enabled:
        raise InnerTubeError("InnerTube is disabled", is_retryable=False)

    client = await get_client()
    headers = {}

    if use_cookies:
        try:
            cookies = await _load_youtube_cookies()
            if cookies:
                headers["Cookie"] = _format_cookie_header(cookies)
        except Exception:
            pass

    response = await client.get(url, headers=headers)
    return response
