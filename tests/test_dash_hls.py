"""Tests for the DASH -> byte-range HLS translation (routers/proxy/_dash_hls.py)."""

import struct
from unittest.mock import AsyncMock, patch

import pytest

from routers.proxy import _dash_hls as dh

GV = "https://rr1---sn-test.googlevideo.com/videoplayback?itag={itag}&mime={mime}"


def _fmt(
    itag,
    *,
    ext,
    vcodec="none",
    acodec="none",
    height=None,
    width=None,
    fps=None,
    tbr=100,
    language=None,
    language_preference=None,
    format_note=None,
    protocol="https",
):
    return {
        "format_id": itag,
        "ext": ext,
        "vcodec": vcodec,
        "acodec": acodec,
        "height": height,
        "width": width,
        "fps": fps,
        "tbr": tbr,
        "language": language,
        "language_preference": language_preference,
        "format_note": format_note,
        "protocol": protocol,
        "url": GV.format(itag=itag, mime="video/mp4" if vcodec != "none" else "audio/mp4"),
    }


FORMATS = [
    _fmt("160", ext="mp4", vcodec="avc1.4d400c", height=144, width=256, fps=24, tbr=100),
    _fmt("137", ext="mp4", vcodec="avc1.640028", height=1080, width=1920, fps=24, tbr=3700),
    _fmt("399", ext="mp4", vcodec="av01.0.08M.08", height=1080, width=1920, fps=24, tbr=2500),
    _fmt("401", ext="mp4", vcodec="av01.0.12M.08", height=2160, width=3840, fps=24, tbr=8500),
    _fmt("248", ext="webm", vcodec="vp9", height=1080, width=1920, fps=24, tbr=2900),  # webm: skipped
    _fmt("91-0", ext="mp4", vcodec="avc1", acodec="mp4a", height=144, protocol="m3u8_native"),  # hls: skipped
    _fmt(
        "140-20",
        ext="m4a",
        acodec="mp4a.40.2",
        tbr=129,
        language="en-US",
        language_preference=10,
        format_note="English (US) original (default), medium",
    ),
    _fmt(
        "139-20",
        ext="m4a",
        acodec="mp4a.40.5",
        tbr=48,
        language="en-US",
        language_preference=10,
        format_note="English (US) original (default), low",
    ),
    _fmt(
        "140-2",
        ext="m4a",
        acodec="mp4a.40.2",
        tbr=129,
        language="pl",
        language_preference=-1,
        format_note="Polish, medium",
    ),
    _fmt(
        "140-3",
        ext="m4a",
        acodec="mp4a.40.2",
        tbr=129,
        language="de-DE",
        language_preference=-1,
        format_note="German (DE), medium",
    ),
    _fmt("251-20", ext="webm", acodec="opus", tbr=130, language="en-US", language_preference=10),  # skipped
]


class TestPlanning:
    def test_plan_video_prefers_h264_up_to_1080p_and_av1_above(self):
        planned = dh.plan_video(FORMATS)
        assert [(f["format_id"], f["height"]) for f in planned] == [("401", 2160), ("137", 1080), ("160", 144)]

    def test_plan_video_can_prefer_av1(self):
        planned = dh.plan_video(FORMATS, prefer_av1=True)
        assert [f["format_id"] for f in planned if f["height"] == 1080] == ["399"]

    def test_pick_video_falls_back_to_nearest_lower(self):
        planned = dh.plan_video(FORMATS)
        assert dh.pick_video(planned, 2160, None)["format_id"] == "401"
        assert dh.pick_video(planned, 720, None)["format_id"] == "160"
        assert dh.pick_video(planned, 100, None)["format_id"] == "160"

    def test_plan_audio_original_first_then_requested_languages(self):
        audios = dh.plan_audio(FORMATS, extra_languages=["pl"])
        assert [a["format_id"] for a in audios] == ["140-20", "140-2"]

    def test_plan_audio_without_extra_languages_is_original_only(self):
        assert [a["format_id"] for a in dh.plan_audio(FORMATS)] == ["140-20"]

    def test_plan_audio_single_track_video(self):
        single = [_fmt("140", ext="m4a", acodec="mp4a.40.2", tbr=129)]
        assert [a["format_id"] for a in dh.plan_audio(single, extra_languages=["pl"])] == ["140"]


def _box(btype: bytes, payload: bytes) -> bytes:
    return struct.pack(">I", 8 + len(payload)) + btype + payload


def _sidx(refs, *, timescale=1000, first_offset=0, version=0):
    body = bytes([version, 0, 0, 0]) + struct.pack(">II", 1, timescale)
    body += struct.pack(">II" if version == 0 else ">QQ", 0, first_offset)
    body += struct.pack(">HH", 0, len(refs))
    for size, dur in refs:
        body += struct.pack(">III", size, dur, 0x90000000)
    return _box(b"sidx", body)


class TestSidx:
    def test_parse_sidx_sizes_and_durations(self):
        buf = _sidx([(1000, 5000), (2000, 4500)], timescale=1000)
        first_offset, refs = dh.parse_sidx(buf, 0, 8)
        assert first_offset == 0
        assert refs == [(1000, 5.0), (2000, 4.5)]

    def test_parse_sidx_version1_first_offset(self):
        buf = _sidx([(10, 1000)], first_offset=42, version=1)
        first_offset, refs = dh.parse_sidx(buf, 0, 8)
        assert first_offset == 42 and refs == [(10, 1.0)]

    @pytest.mark.asyncio
    async def test_index_file_segments_follow_sidx(self):
        head = _box(b"ftyp", b"dash") + _box(b"moov", b"\0" * 20) + _sidx([(500, 2000), (700, 2000)]) + b"\0" * 10
        dh._sidx_cache.clear()
        with patch.object(dh, "_fetch_range", AsyncMock(return_value=head)):
            idx = await dh.index_file("https://rr1---sn-test.googlevideo.com/videoplayback?itag=137")
        init_end = len(head) - 10
        assert idx["init_end"] == init_end
        assert idx["segments"] == [(init_end, 500, 2.0), (init_end + 500, 700, 2.0)]

    @pytest.mark.asyncio
    async def test_index_file_without_sidx_is_502(self):
        dh._sidx_cache.clear()
        with (
            patch.object(dh, "_fetch_range", AsyncMock(return_value=_box(b"ftyp", b"") + _box(b"moov", b""))),
            pytest.raises(dh.HTTPException) as exc,
        ):
            await dh.index_file("https://rr1---sn-test.googlevideo.com/videoplayback?itag=1")
        assert exc.value.status_code == 502


class TestPlaylists:
    def test_media_playlist_uses_byteranges_and_distinct_segment_urls(self):
        url = "https://rr1---sn-test.googlevideo.com/videoplayback?itag=137"
        body = dh.build_media(url, {"init_end": 5000, "segments": [(5000, 1000, 5.9), (6000, 1200, 5.1)]})
        lines = body.splitlines()
        assert "#EXT-X-TARGETDURATION:6" in lines
        assert '#EXT-X-MAP:URI="%s&rn=0&file=seg.mp4",BYTERANGE="5000@0"' % url in lines
        assert "#EXT-X-BYTERANGE:1000@5000" in lines and "#EXT-X-BYTERANGE:1200@6000" in lines
        seg_urls = [ln for ln in lines if ln.startswith("http")]
        assert len(set(seg_urls)) == 2  # ffmpeg must not coalesce them into one whole-file request
        assert all(u.endswith("&file=seg.mp4") for u in seg_urls)  # extension_picky
        assert lines[-1] == "#EXT-X-ENDLIST"

    def test_master_has_one_variant_and_named_audio_renditions(self):
        video = dh.pick_video(dh.plan_video(FORMATS), 2160, None)
        audios = dh.plan_audio(FORMATS, extra_languages=["pl"])
        body = dh.build_master(video, audios, base_url="https://yt.example", relay=False)
        assert body.count("#EXT-X-STREAM-INF") == 1
        assert "RESOLUTION=3840x2160" in body and 'CODECS="av01.0.12M.08,mp4a.40.2"' in body and 'AUDIO="aud"' in body
        media = [ln for ln in body.splitlines() if ln.startswith("#EXT-X-MEDIA")]
        assert len(media) == 2
        assert (
            'NAME="English (US) original"' in media[0] and "DEFAULT=YES" in media[0] and 'LANGUAGE="en-US"' in media[0]
        )
        assert 'NAME="Polish"' in media[1] and "DEFAULT=NO" in media[1] and 'LANGUAGE="pl"' in media[1]
        assert body.count("https://yt.example/proxy/dash-hls/media?url=") == 3


class TestApiStreams:
    @pytest.mark.asyncio
    async def test_dash_hls_streams_respects_height_bounds(self, test_db):
        with (
            patch("ytdlp_wrapper.get_video_info", AsyncMock(return_value={"formats": FORMATS})),
            patch.object(dh, "_height_bounds", return_value=(480, 1080)),
        ):
            streams = await dh.dash_hls_streams("abc", base_url="https://yt.example", relay=False)
        assert [s.quality for s in streams] == ["1080p"]
        assert streams[0].container == "hls" and streams[0].height == 1080
        assert streams[0].url.startswith("https://yt.example/proxy/dash-hls/master?v=abc&h=1080")

    @pytest.mark.asyncio
    async def test_dash_hls_streams_skips_live(self, test_db):
        with patch("ytdlp_wrapper.get_video_info", AsyncMock(return_value={"is_live": True, "formats": FORMATS})):
            assert await dh.dash_hls_streams("abc", base_url="https://yt.example", relay=False) == []


class TestRelaySetting:
    @pytest.mark.asyncio
    async def test_media_relays_segments_by_default(self, test_db):
        from starlette.requests import Request

        index = {"init_end": 5000, "timescale": 1000, "segments": [(5000, 1000, 1000)]}
        scope = {
            "type": "http",
            "method": "GET",
            "scheme": "https",
            "server": ("yt.example", 443),
            "path": "/proxy/dash-hls/media",
            "headers": [],
            "query_string": b"",
        }
        url = "https://rr1---sn-x.googlevideo.com/videoplayback?id=1"
        with (
            patch.object(dh, "_check"),
            patch.object(dh, "is_safe_url", return_value=True),
            patch.object(dh, "index_file", AsyncMock(return_value=index)),
        ):
            with patch.object(dh, "_relay_segments", return_value=True):
                body = (await dh.dash_hls_media(Request(scope), url=url, sig="x", exp=1)).body.decode()
                assert "https://yt.example/proxy/relay?url=" in body
                assert all(
                    ln.startswith("https://yt.example/proxy/relay?")
                    for ln in body.splitlines()
                    if ln.startswith("http")
                )
            with patch.object(dh, "_relay_segments", return_value=False):
                body = (await dh.dash_hls_media(Request(scope), url=url, sig="x", exp=1)).body.decode()
                assert all(ln.startswith(url) for ln in body.splitlines() if ln.startswith("http"))
