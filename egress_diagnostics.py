"""Safe, credential-free diagnostics for the YouTube egress proxy.

Answers, in production, the question that logs alone cannot: when YouTube
extraction fails after a proxy was configured, is it
  * the proxy configuration (malformed value),
  * DNS for the proxy host ("[Errno -2] Name or service not known"),
  * TCP connectivity to the proxy,
  * proxy authentication (HTTP 407), or
  * YouTube itself rejecting the proxy's IP?

Credentials are only ever sent to the proxy itself (as Proxy-Authorization on a
CONNECT) and never appear in the returned report or in any log line.
"""

import asyncio
import base64
import logging
import socket
import ssl
import urllib.parse
from typing import Any, Dict, Optional

import egress

logger = logging.getLogger(__name__)

CONNECT_PROBE_TARGET = "www.youtube.com:443"

# Every network step is individually bounded, and the whole preflight has a hard
# ceiling, so a dead proxy can never hold anything (or anyone) for long.
STEP_TIMEOUT = 5.0
TOTAL_TIMEOUT = 15.0
_MAX_STATUS_LINE = 4096

_CONNECT_MEANINGS = {
    200: "tunnel established",
    407: "proxy rejected the credentials",
    403: "proxy refused the destination or the account",
    502: "proxy could not reach the destination",
}


async def _resolve(host: str, port: int) -> Dict[str, Any]:
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as e:
        return {"ok": False, "error": "gaierror", "errno": e.errno, "name": _gai_name(e.errno)}
    except OSError as e:
        return {"ok": False, "error": type(e).__name__}
    families = sorted({"ipv6" if i[0] == socket.AF_INET6 else "ipv4" for i in infos})
    return {"ok": True, "addresses": len(infos), "families": families}


def _gai_name(code: Optional[int]) -> str:
    return {
        -2: "EAI_NONAME (name or service not known)",
        -3: "EAI_AGAIN (temporary DNS failure)",
        -5: "EAI_NODATA",
    }.get(code if code is not None else 0, "EAI_other")


async def diagnose_proxy(raw_proxy: Optional[str], *, timeout: float = STEP_TIMEOUT) -> Dict[str, Any]:
    """Run config -> DNS -> TCP -> CONNECT checks. Never raises; never leaks."""
    report: Dict[str, Any] = egress.describe_proxy(raw_proxy)
    if raw_proxy is None or not report.get("configured") or not report.get("valid"):
        return report

    scheme, host, port = report["scheme"], report["host"], report["port"]
    port = port or {"http": 80, "https": 443}.get(scheme, 1080)
    connect_host = host[1:-1] if host.startswith("[") else host

    try:
        report["dns"] = await asyncio.wait_for(_resolve(connect_host, port), timeout=timeout)
    except asyncio.TimeoutError:
        report["dns"] = {"ok": False, "error": "timeout"}
    if not report["dns"]["ok"]:
        return report

    ssl_ctx = ssl.create_default_context() if scheme == "https" else None
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(
                connect_host,
                port,
                ssl=ssl_ctx,
                server_hostname=connect_host if ssl_ctx else None,
                limit=_MAX_STATUS_LINE,
            ),
            timeout=timeout,
        )
    except asyncio.TimeoutError:
        report["tcp"] = {"ok": False, "error": "timeout"}
        return report
    except (OSError, ssl.SSLError) as e:
        report["tcp"] = {"ok": False, "error": type(e).__name__, "errno": getattr(e, "errno", None)}
        return report
    report["tcp"] = {"ok": True}

    if scheme in ("http", "https"):
        report["connect"] = await _connect_probe(reader, writer, raw_proxy, timeout)
    else:
        writer.close()
    return report


async def _connect_probe(reader, writer, raw_proxy: str, timeout: float) -> Dict[str, Any]:
    """HTTP CONNECT www.youtube.com:443 through the proxy; report only the status class."""
    headers = [f"CONNECT {CONNECT_PROBE_TARGET} HTTP/1.1", f"Host: {CONNECT_PROBE_TARGET}"]
    parsed = urllib.parse.urlsplit(egress.normalize_proxy_url(raw_proxy))
    if parsed.username is not None:
        token = base64.b64encode(
            f"{urllib.parse.unquote(parsed.username)}:{urllib.parse.unquote(parsed.password or '')}".encode()
        ).decode()
        headers.append(f"Proxy-Authorization: Basic {token}")
    try:
        writer.write(("\r\n".join(headers) + "\r\n\r\n").encode())
        await asyncio.wait_for(writer.drain(), timeout=timeout)
        # Only the status line is read (bounded by the stream limit); the body
        # and any tunnel traffic are never touched, and nothing is sent after CONNECT.
        status_line = await asyncio.wait_for(reader.readline(), timeout=timeout)
    except asyncio.TimeoutError:
        return {"ok": False, "error": "timeout"}
    except (OSError, ValueError, asyncio.LimitOverrunError, asyncio.IncompleteReadError) as e:
        return {"ok": False, "error": type(e).__name__}
    finally:
        writer.close()
    parts = status_line.decode(errors="replace").split()
    status = int(parts[1]) if len(parts) >= 2 and parts[1].isdigit() else None
    return {
        "ok": status == 200,
        "status": status,
        "meaning": (
            _CONNECT_MEANINGS.get(status, "unexpected proxy response") if status is not None else "no HTTP status"
        ),
    }


def summarize(report: Dict[str, Any]) -> str:
    """One log-safe line for a diagnose_proxy() report."""
    if not report.get("configured"):
        return "proxy=not-configured"
    if not report.get("valid"):
        return f"proxy=INVALID reason={report.get('error')}"
    parts = [
        f"proxy={report['scheme']}://{'***@' if report['authenticated'] else ''}{report['host']}"
        + (f":{report['port']}" if report.get("port") else "")
    ]
    dns = report.get("dns")
    if dns is not None:
        parts.append("dns=ok" if dns["ok"] else f"dns=FAILED({dns.get('name') or dns.get('error')})")
    tcp = report.get("tcp")
    if tcp is not None:
        parts.append("tcp=ok" if tcp["ok"] else f"tcp=FAILED({tcp.get('error')})")
    connect = report.get("connect")
    if connect is not None:
        parts.append(f"connect={connect.get('status') or connect.get('error')}({connect.get('meaning', '')})")
    return " ".join(parts)


async def log_proxy_preflight(raw_proxy: Optional[str]) -> None:
    """Startup hook: one concise line saying whether the egress proxy is usable."""
    if not raw_proxy:
        return
    try:
        report = await asyncio.wait_for(diagnose_proxy(raw_proxy), timeout=TOTAL_TIMEOUT)
        ok = (
            report.get("valid")
            and report.get("dns", {}).get("ok")
            and report.get("tcp", {}).get("ok")
            and report.get("connect", {"ok": True}).get("ok")
        )
        (logger.info if ok else logger.error)("[Egress] preflight %s", summarize(report))
    except asyncio.TimeoutError:
        logger.error("[Egress] preflight timed out after %ss (proxy unreachable or unresponsive)", TOTAL_TIMEOUT)
    except Exception as e:  # diagnostics must never take the server down
        logger.warning("[Egress] preflight failed to run: %s", type(e).__name__)
