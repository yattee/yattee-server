"""Tests for streaming a file while yt-dlp is still writing it (fast download)."""

import os

import pytest

from routers.proxy._cleanup import _active_downloads
from routers.proxy._fast_download import stream_file_as_it_downloads

CHUNK = 256 * 1024


def _register(key: str, path):
    _active_downloads[key] = {"path": path, "complete": False, "error": None, "process": None}


@pytest.mark.asyncio
async def test_file_replaced_mid_stream_keeps_original_bytes(tmp_path):
    """A post-processing remux os.replace()s the output; the client must get the original file intact (#23)."""
    key = "test_replaced"
    path = tmp_path / "video_139.m4a"
    original = b"A" * (CHUNK * 3)
    remuxed = b"B" * (CHUNK * 2)

    path.write_bytes(original[: CHUNK * 2])
    _register(key, path)
    try:
        gen = stream_file_as_it_downloads(path, key, len(original))
        received = await gen.__anext__()

        # Finish writing the original, then swap in a different (smaller) file like FixupM4a does
        with open(path, "ab") as fh:
            fh.write(original[CHUNK * 2 :])
        tmp = tmp_path / "video_139.temp.m4a"
        tmp.write_bytes(remuxed)
        os.replace(tmp, path)
        _active_downloads[key]["complete"] = True

        async for chunk in gen:
            received += chunk
    finally:
        _active_downloads.pop(key, None)

    assert received == original


@pytest.mark.asyncio
async def test_file_appears_later_and_grows(tmp_path):
    key = "test_grows"
    path = tmp_path / "video_18.mp4"
    _register(key, path)
    try:
        gen = stream_file_as_it_downloads(path, key, 0)
        path.write_bytes(b"x" * 1000)
        received = await gen.__anext__()
        with open(path, "ab") as fh:
            fh.write(b"y" * 500)
        _active_downloads[key]["complete"] = True
        async for chunk in gen:
            received += chunk
    finally:
        _active_downloads.pop(key, None)

    assert received == b"x" * 1000 + b"y" * 500
