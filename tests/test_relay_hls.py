"""Tests for HLS manifest rewriting in the relay."""

import os
import sys

from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

MANIFEST_URL = "https://manifest.googlevideo.com/api/manifest/hls_variant/id/abc/file/index.m3u8"


def test_segments_stay_on_https_behind_a_reverse_proxy(test_db, httpx_mock, monkeypatch):
    from routers import proxy
    from routers.proxy import _relay, signed_relay_url

    monkeypatch.setattr(_relay, "is_safe_url", lambda url: True)
    httpx_mock.add_response(
        url=MANIFEST_URL,
        headers={"content-type": "application/vnd.apple.mpegurl"},
        text="#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=1\nhttps://manifest.googlevideo.com/variant.m3u8\n",
        is_reusable=True,
    )

    app = FastAPI()
    app.include_router(proxy.router, prefix="/proxy")
    relay_url = signed_relay_url("https://yattee.example", MANIFEST_URL, content_type="application/vnd.apple.mpegurl")

    response = TestClient(app, base_url="http://yattee.example").get(
        relay_url.removeprefix("https://yattee.example"),
        headers={"X-Forwarded-Proto": "https"},
    )

    assert response.status_code == 200
    variant = response.text.splitlines()[2]
    assert variant.startswith("https://yattee.example/proxy/relay?")


SEGMENT_URL = "https://rr1---sn-abc.googlevideo.com/videoplayback/id/abc/itag/232/source/yt_live_broadcast/file/seg.ts"


def test_head_requests_report_the_segment_type(test_db, httpx_mock, monkeypatch):
    """Relay URLs have no file extension, so players ask for the segment type with HEAD."""
    from routers import proxy
    from routers.proxy import _relay, signed_relay_url

    monkeypatch.setattr(_relay, "is_safe_url", lambda url: True)
    httpx_mock.add_response(
        url=SEGMENT_URL,
        status_code=206,
        # googlevideo labels live HLS segments as generic binary data
        headers={"content-type": "application/octet-stream", "content-range": "bytes 0-0/1000"},
        content=b"G",
    )

    app = FastAPI()
    app.include_router(proxy.router, prefix="/proxy")
    relay_url = signed_relay_url("http://testserver", SEGMENT_URL)

    response = TestClient(app).head(relay_url.removeprefix("http://testserver"))

    assert response.status_code == 200
    assert response.headers["content-type"] == "video/mp2t"
    assert response.headers["content-length"] == "1000"
    assert response.content == b""
