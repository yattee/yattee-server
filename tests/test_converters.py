"""Tests for converters.py data transformation functions."""

import os
import sys

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from converters import (
    _extract_region_from_label,
    _label_to_lang_code,
    build_mime_type,
    construct_author_url,
    convert_captions,
    convert_formats,
    convert_thumbnails,
    format_published_text,
    format_subscriber_count,
    format_view_count,
    get_valid_timestamp,
    invidious_to_channel_list_item,
    invidious_to_playlist_list_item,
    invidious_to_video_list_item,
    invidious_to_video_response,
    parse_cookies_to_header,
    parse_upload_date,
    resolve_invidious_url,
    ytdlp_to_video_list_item,
)

# =============================================================================
# Tests for parse_upload_date
# =============================================================================


class TestParseUploadDate:
    """Tests for parse_upload_date function."""

    def test_valid_date(self):
        """Test parsing a valid YYYYMMDD date."""
        assert parse_upload_date("20230101") == 1672531200

    def test_another_valid_date(self):
        """Test parsing another valid date."""
        assert parse_upload_date("20091025") == 1256428800

    def test_invalid_format(self):
        """Test that invalid date format returns None."""
        assert parse_upload_date("invalid") is None

    def test_none_input(self):
        """Test that None input returns None."""
        assert parse_upload_date(None) is None

    def test_empty_string(self):
        """Test that empty string returns None."""
        assert parse_upload_date("") is None

    def test_partial_date(self):
        """Test that partial date returns None."""
        assert parse_upload_date("202301") is None

    def test_wrong_separator(self):
        """Test date with separators returns None."""
        assert parse_upload_date("2023-01-01") is None


# =============================================================================
# Tests for get_valid_timestamp
# =============================================================================


class TestGetValidTimestamp:
    """Tests for get_valid_timestamp function."""

    def test_valid_timestamp(self):
        """Test that a valid timestamp is returned."""
        info = {"timestamp": 1700000000}  # Nov 2023
        assert get_valid_timestamp(info) == 1700000000

    def test_valid_release_timestamp(self):
        """Test that release_timestamp is used when timestamp is missing."""
        info = {"release_timestamp": 1700000000}
        assert get_valid_timestamp(info) == 1700000000

    def test_timestamp_preferred_over_release_timestamp(self):
        """Test that timestamp is preferred over release_timestamp."""
        info = {"timestamp": 1700000000, "release_timestamp": 1600000000}
        assert get_valid_timestamp(info) == 1700000000

    def test_zero_timestamp_rejected(self):
        """Test that timestamp=0 (Unix epoch) is rejected."""
        info = {"timestamp": 0}
        assert get_valid_timestamp(info) is None

    def test_zero_release_timestamp_rejected(self):
        """Test that release_timestamp=0 is rejected."""
        info = {"release_timestamp": 0}
        assert get_valid_timestamp(info) is None

    def test_fallback_to_release_timestamp_when_timestamp_zero(self):
        """Test fallback to release_timestamp when timestamp is 0."""
        info = {"timestamp": 0, "release_timestamp": 1700000000}
        assert get_valid_timestamp(info) == 1700000000

    def test_very_old_timestamp_rejected(self):
        """Test that timestamps before 2005 are rejected."""
        info = {"timestamp": 1000000000}  # Sep 2001
        assert get_valid_timestamp(info) is None

    def test_boundary_timestamp_rejected(self):
        """Test that timestamp exactly at boundary (Jan 1, 2005) is rejected."""
        info = {"timestamp": 1104537600}  # Jan 1, 2005 00:00:00 UTC
        assert get_valid_timestamp(info) is None

    def test_just_above_boundary_accepted(self):
        """Test that timestamp just above boundary is accepted."""
        info = {"timestamp": 1104537601}  # Jan 1, 2005 00:00:01 UTC
        assert get_valid_timestamp(info) == 1104537601

    def test_empty_dict(self):
        """Test that empty dict returns None."""
        assert get_valid_timestamp({}) is None

    def test_none_values(self):
        """Test that None values are handled."""
        info = {"timestamp": None, "release_timestamp": None}
        assert get_valid_timestamp(info) is None

    def test_both_invalid_returns_none(self):
        """Test that when both timestamps are invalid, None is returned."""
        info = {"timestamp": 0, "release_timestamp": 0}
        assert get_valid_timestamp(info) is None


# =============================================================================
# Tests for format_view_count
# =============================================================================


class TestFormatViewCount:
    """Tests for format_view_count function."""

    def test_small_count(self):
        """Test view count under 1000."""
        assert format_view_count(100) == "100 views"

    def test_thousands(self):
        """Test view count in thousands."""
        assert format_view_count(1500) == "1.5K views"

    def test_millions(self):
        """Test view count in millions."""
        assert format_view_count(1000000) == "1.0M views"

    def test_billions(self):
        """Test view count in billions."""
        assert format_view_count(1500000000) == "1.5B views"

    def test_none_input(self):
        """Test that None returns None."""
        assert format_view_count(None) is None

    def test_zero(self):
        """Test zero views."""
        assert format_view_count(0) == "0 views"

    def test_exact_thousand(self):
        """Test exactly 1000 views."""
        assert format_view_count(1000) == "1.0K views"

    def test_exact_million(self):
        """Test exactly 1 million views."""
        assert format_view_count(1000000) == "1.0M views"


# =============================================================================
# Tests for _label_to_lang_code
# =============================================================================


class TestLabelToLangCode:
    """Tests for _label_to_lang_code function."""

    def test_simple_english(self):
        """Test simple English label."""
        assert _label_to_lang_code("English") == "en"

    def test_auto_generated_suffix(self):
        """Test English with auto-generated suffix."""
        assert _label_to_lang_code("English (auto-generated)") == "en"

    def test_regional_variant(self):
        """Test language with regional variant."""
        assert _label_to_lang_code("Spanish (Latin America)") == "es"

    def test_unknown_language(self):
        """Test unknown language returns empty string."""
        assert _label_to_lang_code("Unknown Language") == ""

    def test_chinese(self):
        """Test Chinese language."""
        assert _label_to_lang_code("Chinese") == "zh"

    def test_chinese_simplified(self):
        """Test Chinese (Simplified)."""
        assert _label_to_lang_code("Chinese (Simplified)") == "zh"

    def test_japanese(self):
        """Test Japanese language."""
        assert _label_to_lang_code("Japanese") == "ja"

    def test_german(self):
        """Test German language."""
        assert _label_to_lang_code("German") == "de"

    def test_case_insensitive(self):
        """Test that lookup is case-insensitive."""
        assert _label_to_lang_code("ENGLISH") == "en"
        assert _label_to_lang_code("english") == "en"

    def test_empty_string(self):
        """Test empty string returns empty string."""
        assert _label_to_lang_code("") == ""


# =============================================================================
# Tests for _extract_region_from_label
# =============================================================================


class TestExtractRegionFromLabel:
    """Tests for _extract_region_from_label function."""

    def test_united_states(self):
        """Test extracting US region code."""
        assert _extract_region_from_label("English (United States)") == "US"

    def test_united_kingdom(self):
        """Test extracting GB region code."""
        assert _extract_region_from_label("English (United Kingdom)") == "GB"

    def test_brazil(self):
        """Test extracting BR region code."""
        assert _extract_region_from_label("Portuguese (Brazil)") == "BR"

    def test_portugal(self):
        """Test extracting PT region code."""
        assert _extract_region_from_label("Portuguese (Portugal)") == "PT"

    def test_mexico(self):
        """Test extracting MX region code."""
        assert _extract_region_from_label("Spanish (Mexico)") == "MX"

    def test_spain(self):
        """Test extracting ES region code."""
        assert _extract_region_from_label("Spanish (Spain)") == "ES"

    def test_latin_america(self):
        """Test extracting Latin America UN M.49 code."""
        assert _extract_region_from_label("Spanish (Latin America)") == "419"

    def test_auto_generated_returns_empty(self):
        """Test that auto-generated labels return empty string."""
        assert _extract_region_from_label("English (auto-generated)") == ""

    def test_auto_returns_empty(self):
        """Test that (auto) labels return empty string."""
        assert _extract_region_from_label("English (auto)") == ""

    def test_no_parentheses_returns_empty(self):
        """Test that labels without parentheses return empty string."""
        assert _extract_region_from_label("English") == ""

    def test_unknown_region_returns_empty(self):
        """Test that unknown regions return empty string."""
        assert _extract_region_from_label("English (Simplified)") == ""

    def test_case_insensitive(self):
        """Test that region matching is case-insensitive."""
        assert _extract_region_from_label("English (UNITED STATES)") == "US"
        assert _extract_region_from_label("English (united states)") == "US"


# =============================================================================
# Tests for resolve_invidious_url
# =============================================================================


class TestResolveInvidiousUrl:
    """Tests for resolve_invidious_url function."""

    def test_protocol_relative_url(self):
        """Test protocol-relative URL conversion."""
        url = "//yt3.ggpht.com/ytc/some-avatar.jpg"
        result = resolve_invidious_url(url, "https://invidious.example.com")
        assert result == "https://yt3.ggpht.com/ytc/some-avatar.jpg"

    def test_relative_path(self):
        """Test relative path URL conversion."""
        url = "/vi/dQw4w9WgXcQ/maxres.jpg"
        result = resolve_invidious_url(url, "https://invidious.example.com")
        assert result == "https://invidious.example.com/vi/dQw4w9WgXcQ/maxres.jpg"

    def test_absolute_url_unchanged(self):
        """Test absolute URL is returned unchanged."""
        url = "https://example.com/image.jpg"
        result = resolve_invidious_url(url, "https://invidious.example.com")
        assert result == url

    def test_empty_url(self):
        """Test empty URL returns empty."""
        assert resolve_invidious_url("", "https://invidious.example.com") == ""

    def test_none_url(self):
        """Test None-like empty URL."""
        assert resolve_invidious_url("", "") == ""

    def test_base_url_with_trailing_slash(self):
        """Test base URL with trailing slash is handled correctly."""
        url = "/api/v1/test"
        result = resolve_invidious_url(url, "https://invidious.example.com/")
        assert result == "https://invidious.example.com/api/v1/test"


# =============================================================================
# Tests for format_published_text
# =============================================================================


class TestFormatPublishedText:
    """Tests for format_published_text function."""

    def test_none_input(self):
        """Test None input returns None."""
        assert format_published_text(None) is None

    def test_empty_string(self):
        """Test empty string returns None."""
        assert format_published_text("") is None

    def test_invalid_date(self):
        """Test invalid date format returns None."""
        assert format_published_text("invalid") is None


# =============================================================================
# Tests for format_subscriber_count
# =============================================================================


class TestFormatSubscriberCount:
    """Tests for format_subscriber_count function."""

    def test_small_count(self):
        """Test subscriber count under 1000."""
        assert format_subscriber_count(500) == "500"

    def test_thousands(self):
        """Test subscriber count in thousands."""
        assert format_subscriber_count(1500) == "1.5K"

    def test_millions(self):
        """Test subscriber count in millions."""
        assert format_subscriber_count(4200000) == "4.2M"

    def test_billions(self):
        """Test subscriber count in billions."""
        assert format_subscriber_count(1500000000) == "1.5B"

    def test_none_input(self):
        """Test None returns None."""
        assert format_subscriber_count(None) is None

    def test_zero(self):
        """Test zero subscribers."""
        assert format_subscriber_count(0) == "0"


# =============================================================================
# Tests for convert_thumbnails
# =============================================================================


class TestConvertThumbnails:
    """Tests for convert_thumbnails function."""

    def test_empty_list(self):
        """Test empty list returns empty list."""
        assert convert_thumbnails([]) == []

    def test_none_input(self):
        """Test None input returns empty list."""
        assert convert_thumbnails(None) == []

    def test_maxres_quality(self):
        """Test thumbnail with width >= 1280 gets maxres quality."""
        thumbnails = [{"url": "https://example.com/thumb.jpg", "width": 1280, "height": 720}]
        result = convert_thumbnails(thumbnails)
        assert len(result) == 1
        assert result[0].quality == "maxres"

    def test_sddefault_quality(self):
        """Test thumbnail with width >= 640 gets sddefault quality."""
        thumbnails = [{"url": "https://example.com/thumb.jpg", "width": 640, "height": 480}]
        result = convert_thumbnails(thumbnails)
        assert len(result) == 1
        assert result[0].quality == "sddefault"

    def test_high_quality(self):
        """Test thumbnail with width >= 480 gets high quality."""
        thumbnails = [{"url": "https://example.com/thumb.jpg", "width": 480, "height": 360}]
        result = convert_thumbnails(thumbnails)
        assert len(result) == 1
        assert result[0].quality == "high"

    def test_medium_quality(self):
        """Test thumbnail with width >= 320 gets medium quality."""
        thumbnails = [{"url": "https://example.com/thumb.jpg", "width": 320, "height": 180}]
        result = convert_thumbnails(thumbnails)
        assert len(result) == 1
        assert result[0].quality == "medium"

    def test_default_quality(self):
        """Test thumbnail with small width gets default quality."""
        thumbnails = [{"url": "https://example.com/thumb.jpg", "width": 120, "height": 90}]
        result = convert_thumbnails(thumbnails)
        assert len(result) == 1
        assert result[0].quality == "default"

    def test_no_dimensions(self):
        """Test thumbnail without dimensions gets default quality."""
        thumbnails = [{"url": "https://example.com/thumb.jpg"}]
        result = convert_thumbnails(thumbnails)
        assert len(result) == 1
        assert result[0].quality == "default"

    def test_multiple_thumbnails(self):
        """Test multiple thumbnails are all converted."""
        thumbnails = [
            {"url": "https://example.com/small.jpg", "width": 120, "height": 90},
            {"url": "https://example.com/large.jpg", "width": 1280, "height": 720},
        ]
        result = convert_thumbnails(thumbnails)
        assert len(result) == 2


# =============================================================================
# Tests for build_mime_type
# =============================================================================


class TestBuildMimeType:
    """Tests for build_mime_type function."""

    def test_video_mp4_with_codecs(self):
        """Test video/mp4 with both codecs."""
        result = build_mime_type("avc1.42001E", "mp4a.40.2", "mp4")
        assert result == 'video/mp4; codecs="avc1.42001E, mp4a.40.2"'

    def test_video_only(self):
        """Test video-only format."""
        result = build_mime_type("avc1.640028", "none", "mp4")
        assert result == 'video/mp4; codecs="avc1.640028"'

    def test_audio_only_mp4(self):
        """Test audio-only mp4 format."""
        result = build_mime_type("none", "mp4a.40.2", "mp4")
        assert result == 'audio/mp4; codecs="mp4a.40.2"'

    def test_audio_m4a_container(self):
        """Test m4a audio container."""
        result = build_mime_type(None, "mp4a.40.2", "m4a")
        assert result == 'audio/m4a; codecs="mp4a.40.2"'

    def test_video_webm(self):
        """Test video webm format."""
        result = build_mime_type("vp9", None, "webm")
        assert result == 'video/webm; codecs="vp9"'

    def test_audio_webm(self):
        """Test audio webm format."""
        result = build_mime_type("none", "opus", "webm")
        assert result == 'audio/webm; codecs="opus"'

    def test_no_codecs(self):
        """Test when no codecs provided."""
        result = build_mime_type(None, None, "mp4")
        assert result == "audio/mp4"

    def test_3gp_container(self):
        """Test 3gp container."""
        result = build_mime_type("h264", "aac", "3gp")
        assert result == 'video/3gpp; codecs="h264, aac"'

    def test_has_video_override(self):
        """Test has_video parameter override."""
        # Force video even though vcodec is none
        result = build_mime_type("none", "aac", "mp4", has_video=True)
        assert result.startswith("video/mp4")


# =============================================================================
# Tests for parse_cookies_to_header
# =============================================================================


class TestParseCookiesToHeader:
    """Tests for parse_cookies_to_header function."""

    def test_simple_cookie(self):
        """Test simple cookie parsing."""
        result = parse_cookies_to_header("name=value")
        assert result == "name=value"

    def test_multiple_cookies(self):
        """Test multiple cookies."""
        result = parse_cookies_to_header("name1=value1; name2=value2")
        assert "name1=value1" in result
        assert "name2=value2" in result

    def test_strips_domain(self):
        """Test that Domain attribute is stripped."""
        result = parse_cookies_to_header("name=value; Domain=.example.com")
        assert result == "name=value"
        assert "Domain" not in result

    def test_strips_path(self):
        """Test that Path attribute is stripped."""
        result = parse_cookies_to_header("name=value; Path=/")
        assert result == "name=value"
        assert "Path" not in result

    def test_strips_secure(self):
        """Test that Secure flag is stripped."""
        result = parse_cookies_to_header("name=value; Secure")
        assert result == "name=value"

    def test_empty_string(self):
        """Test empty string returns empty."""
        assert parse_cookies_to_header("") == ""

    def test_complex_cookie(self):
        """Test complex cookie with multiple attributes."""
        cookie = "session=abc123; Domain=.tiktok.com; Path=/; Secure; HttpOnly; SameSite=None"
        result = parse_cookies_to_header(cookie)
        assert result == "session=abc123"


# =============================================================================
# Tests for construct_author_url
# =============================================================================


class TestConstructAuthorUrl:
    """Tests for construct_author_url function."""

    def test_dailymotion(self):
        """Test Dailymotion URL construction."""
        result = construct_author_url("dailymotion", "user123", None)
        assert result == "https://www.dailymotion.com/user123"

    def test_vimeo(self):
        """Test Vimeo URL construction."""
        result = construct_author_url("vimeo", "username", None)
        assert result == "https://vimeo.com/username"

    def test_tiktok(self):
        """Test TikTok URL construction."""
        result = construct_author_url("tiktok", "username", None)
        assert result == "https://www.tiktok.com/@username"

    def test_twitch(self):
        """Test Twitch URL construction."""
        result = construct_author_url("twitch", "streamer", None)
        assert result == "https://www.twitch.tv/streamer"

    def test_soundcloud(self):
        """Test SoundCloud URL construction."""
        result = construct_author_url("soundcloud", "artist", None)
        assert result == "https://soundcloud.com/artist"

    def test_no_author_id(self):
        """Test that None author_id returns None."""
        result = construct_author_url("vimeo", None, None)
        assert result is None

    def test_empty_author_id(self):
        """Test that empty author_id returns None."""
        result = construct_author_url("vimeo", "", None)
        assert result is None

    def test_unknown_extractor_with_url(self):
        """Test unknown extractor falls back to URL domain."""
        result = construct_author_url("unknown_site", "user123", "https://example.com/video/123")
        assert result == "https://example.com/user123"

    def test_case_insensitive(self):
        """Test extractor matching is case-insensitive."""
        result = construct_author_url("DailyMotion", "user123", None)
        assert result == "https://www.dailymotion.com/user123"


# =============================================================================
# Tests for convert_formats
# =============================================================================


class TestConvertFormats:
    """Tests for convert_formats function."""

    def test_empty_formats(self):
        """Test empty formats list."""
        format_streams, adaptive_formats = convert_formats([])
        assert format_streams == []
        assert adaptive_formats == []

    def test_none_formats(self):
        """Test None formats."""
        format_streams, adaptive_formats = convert_formats(None)
        assert format_streams == []
        assert adaptive_formats == []

    def test_muxed_format(self):
        """Test muxed format (video + audio) goes to format_streams."""
        formats = [
            {
                "format_id": "18",
                "ext": "mp4",
                "url": "https://example.com/video.mp4",
                "width": 640,
                "height": 360,
                "vcodec": "avc1.42001E",
                "acodec": "mp4a.40.2",
            }
        ]
        format_streams, adaptive_formats = convert_formats(formats)
        assert len(format_streams) == 1
        assert len(adaptive_formats) == 0
        assert format_streams[0].itag == "18"

    def test_video_only_format(self):
        """Test video-only format goes to adaptive_formats."""
        formats = [
            {
                "format_id": "137",
                "ext": "mp4",
                "url": "https://example.com/video.mp4",
                "width": 1920,
                "height": 1080,
                "vcodec": "avc1.640028",
                "acodec": "none",
            }
        ]
        format_streams, adaptive_formats = convert_formats(formats)
        assert len(format_streams) == 0
        assert len(adaptive_formats) == 1
        assert adaptive_formats[0].itag == "137"

    def test_audio_only_format(self):
        """Test audio-only format goes to adaptive_formats."""
        formats = [
            {
                "format_id": "140",
                "ext": "m4a",
                "url": "https://example.com/audio.m4a",
                "vcodec": "none",
                "acodec": "mp4a.40.2",
            }
        ]
        format_streams, adaptive_formats = convert_formats(formats)
        assert len(format_streams) == 0
        assert len(adaptive_formats) == 1
        assert adaptive_formats[0].itag == "140"

    def test_skips_storyboard_formats(self):
        """Test that storyboard formats are skipped."""
        formats = [
            {"format_id": "sb0", "ext": "mhtml", "url": "https://example.com/sb"},
            {
                "format_id": "18",
                "ext": "mp4",
                "url": "https://example.com/video.mp4",
                "vcodec": "avc1",
                "acodec": "mp4a",
            },
        ]
        format_streams, adaptive_formats = convert_formats(formats)
        assert len(format_streams) == 1
        assert format_streams[0].itag == "18"

    def test_proxy_url_generation(self):
        """Test proxy URL generation when proxy_base_url provided."""
        formats = [
            {
                "format_id": "18",
                "ext": "mp4",
                "url": "https://example.com/video.mp4",
                "vcodec": "avc1",
                "acodec": "mp4a",
            }
        ]
        format_streams, _ = convert_formats(formats, video_id="abc123", proxy_base_url="http://localhost:8080/proxy")
        assert "http://localhost:8080/proxy/fast/abc123?itag=18" in format_streams[0].url


# =============================================================================
# Tests for convert_captions
# =============================================================================


class TestConvertCaptions:
    """Tests for convert_captions function."""

    def test_empty_captions(self):
        """Test empty subtitles."""
        result = convert_captions(None, None, "video123", "")
        assert result == []

    def test_manual_captions(self):
        """Test manual captions conversion."""
        subtitles = {"en": [{"ext": "vtt", "url": "https://example.com/en.vtt", "name": "English"}]}
        result = convert_captions(subtitles, None, "video123", "http://localhost")
        assert len(result) == 1
        assert result[0].languageCode == "en"
        assert result[0].auto_generated is False

    def test_auto_generated_captions(self):
        """Test auto-generated captions conversion."""
        automatic_captions = {"en": [{"ext": "vtt", "url": "https://example.com/en_auto.vtt", "name": "English"}]}
        result = convert_captions(None, automatic_captions, "video123", "http://localhost")
        assert len(result) == 1
        assert result[0].auto_generated is True
        assert "(auto-generated)" in result[0].label

    def test_mixed_captions(self):
        """Test both manual and auto-generated captions."""
        subtitles = {"en": [{"ext": "vtt", "url": "url1", "name": "English"}]}
        automatic_captions = {"es": [{"ext": "vtt", "url": "url2", "name": "Spanish"}]}
        result = convert_captions(subtitles, automatic_captions, "video123", "http://localhost")
        assert len(result) == 2

    def test_captions_with_user_id_include_token(self):
        """Test that captions include token when user_id is provided."""
        subtitles = {"en": [{"ext": "vtt", "url": "url1", "name": "English"}]}
        result = convert_captions(subtitles, None, "video123", "http://localhost", user_id=1)
        assert len(result) == 1
        assert "token=" in result[0].url

    def test_captions_without_user_id_no_token(self):
        """Test that captions don't include token when user_id is not provided."""
        subtitles = {"en": [{"ext": "vtt", "url": "url1", "name": "English"}]}
        result = convert_captions(subtitles, None, "video123", "http://localhost")
        assert len(result) == 1
        assert "token=" not in result[0].url


# =============================================================================
# Tests for ytdlp_to_video_list_item
# =============================================================================


class TestYtdlpToVideoListItem:
    """Tests for ytdlp_to_video_list_item function."""

    def test_basic_conversion(self):
        """Test basic video list item conversion."""
        info = {
            "id": "abc123",
            "title": "Test Video",
            "uploader": "Test Channel",
            "channel_id": "UC123",
            "duration": 120,
            "view_count": 1000,
        }
        result = ytdlp_to_video_list_item(info)
        assert result.videoId == "abc123"
        assert result.title == "Test Video"
        assert result.author == "Test Channel"
        assert result.lengthSeconds == 120

    def test_flat_playlist_fields(self):
        """Test conversion with flat-playlist field names."""
        info = {
            "id": "abc123",
            "title": "Test Video",
            "playlist_uploader": "Test Channel",
            "playlist_channel_id": "UC123",
        }
        result = ytdlp_to_video_list_item(info)
        assert result.author == "Test Channel"
        assert result.authorId == "UC123"

    def test_live_video(self):
        """Test live video detection."""
        info = {"id": "abc123", "title": "Live Stream", "is_live": True}
        result = ytdlp_to_video_list_item(info)
        assert result.liveNow is True

    def test_upcoming_video(self):
        """Test upcoming video detection."""
        info = {"id": "abc123", "title": "Premiere", "live_status": "is_upcoming"}
        result = ytdlp_to_video_list_item(info)
        assert result.isUpcoming is True


# =============================================================================
# Tests for invidious_to_video_list_item
# =============================================================================


class TestInvidiousToVideoListItem:
    """Tests for invidious_to_video_list_item function."""

    def test_basic_conversion(self):
        """Test basic Invidious video conversion."""
        info = {
            "videoId": "abc123",
            "title": "Test Video",
            "author": "Test Channel",
            "authorId": "UC123",
            "lengthSeconds": 120,
            "viewCount": 1000,
        }
        result = invidious_to_video_list_item(info, "https://invidious.example.com")
        assert result.videoId == "abc123"
        assert result.title == "Test Video"
        assert result.author == "Test Channel"

    def test_relative_url_resolution(self):
        """Test that relative author URL is resolved."""
        info = {
            "videoId": "abc123",
            "title": "Test",
            "author": "Channel",
            "authorId": "UC123",
            "authorUrl": "/channel/UC123",
        }
        result = invidious_to_video_list_item(info, "https://invidious.example.com")
        assert result.authorUrl == "https://invidious.example.com/channel/UC123"

    def test_iso_published_conversion(self):
        """Test ISO 8601 published date conversion."""
        info = {
            "videoId": "abc123",
            "title": "Test",
            "published": "2023-06-15T00:00:00Z",
        }
        result = invidious_to_video_list_item(info, "")
        assert result.published == 1686787200

    def test_zero_published_rejected(self):
        """Test that published=0 (Unix epoch) is rejected."""
        info = {
            "videoId": "abc123",
            "title": "Test",
            "published": 0,
            "publishedText": "56 years ago",
        }
        result = invidious_to_video_list_item(info, "")
        assert result.published is None
        assert result.publishedText is None

    def test_very_old_published_rejected(self):
        """Test that timestamps before 2005 are rejected."""
        info = {
            "videoId": "abc123",
            "title": "Test",
            "published": 1000000000,  # Sep 2001
            "publishedText": "23 years ago",
        }
        result = invidious_to_video_list_item(info, "")
        assert result.published is None
        assert result.publishedText is None

    def test_valid_published_keeps_text(self):
        """Test that valid timestamps keep publishedText."""
        info = {
            "videoId": "abc123",
            "title": "Test",
            "published": 1700000000,  # Nov 2023
            "publishedText": "2 months ago",
        }
        result = invidious_to_video_list_item(info, "")
        assert result.published == 1700000000
        assert result.publishedText == "2 months ago"

    def test_boundary_published_rejected(self):
        """Test that timestamp exactly at boundary (Jan 1, 2005) is rejected."""
        info = {
            "videoId": "abc123",
            "title": "Test",
            "published": 1104537600,  # Jan 1, 2005 00:00:00 UTC
            "publishedText": "20 years ago",
        }
        result = invidious_to_video_list_item(info, "")
        assert result.published is None
        assert result.publishedText is None


# =============================================================================
# Tests for invidious_to_channel_list_item
# =============================================================================


class TestInvidiousToChannelListItem:
    """Tests for invidious_to_channel_list_item function."""

    def test_basic_conversion(self):
        """Test basic channel conversion."""
        info = {
            "authorId": "UC123",
            "author": "Test Channel",
            "subCount": 1000000,
            "description": "A test channel",
        }
        result = invidious_to_channel_list_item(info, "")
        assert result.authorId == "UC123"
        assert result.author == "Test Channel"
        assert result.subCount == 1000000

    def test_thumbnail_url_resolution(self):
        """Test thumbnail URL resolution."""
        info = {
            "authorId": "UC123",
            "author": "Test",
            "authorThumbnails": [{"url": "/ggpht/avatar.jpg", "width": 48, "height": 48}],
        }
        result = invidious_to_channel_list_item(info, "https://invidious.example.com")
        assert result.authorThumbnails[0].url == "https://invidious.example.com/ggpht/avatar.jpg"


# =============================================================================
# Tests for invidious_to_playlist_list_item
# =============================================================================


class TestInvidiousToPlaylistListItem:
    """Tests for invidious_to_playlist_list_item function."""

    def test_basic_conversion(self):
        """Test basic playlist conversion."""
        info = {
            "playlistId": "PL123",
            "title": "Test Playlist",
            "author": "Test Channel",
            "videoCount": 10,
        }
        result = invidious_to_playlist_list_item(info, "")
        assert result.playlistId == "PL123"
        assert result.title == "Test Playlist"
        assert result.videoCount == 10

    def test_with_videos(self):
        """Test playlist with video entries."""
        info = {
            "playlistId": "PL123",
            "title": "Test Playlist",
            "videoCount": 1,
            "videos": [{"videoId": "abc123", "title": "Video 1", "lengthSeconds": 120}],
        }
        result = invidious_to_playlist_list_item(info, "")
        assert len(result.videos) == 1
        assert result.videos[0].videoId == "abc123"


# =============================================================================
# Tests for invidious_to_video_response caption processing
# =============================================================================


class TestInvidiousToVideoResponseCaptions:
    """Tests for caption processing in invidious_to_video_response function."""

    def test_caption_with_region_code_in_label(self):
        """Test that captions with region in label get proper locale code.

        Invidious returns languageCode 'en' for both auto-generated and regional
        manual captions. The label 'English (United States)' should result in
        languageCode 'en-US' in the URL.
        """
        info = {
            "videoId": "test123",
            "title": "Test Video",
            "captions": [
                {
                    "label": "English (United States)",
                    "languageCode": "en",
                    "url": "/api/v1/captions/test123?label=English+%28United+States%29",
                }
            ],
        }
        result = invidious_to_video_response(info, base_url="http://localhost")
        assert len(result.captions) == 1
        caption = result.captions[0]
        assert caption.languageCode == "en-US"
        assert "lang=en-US" in caption.url
        assert "auto=true" not in caption.url

    def test_auto_generated_caption_keeps_base_code(self):
        """Test that auto-generated captions don't get region appended.

        Auto-generated captions should use the base language code (e.g., 'en')
        with the auto=true parameter.
        """
        info = {
            "videoId": "test123",
            "title": "Test Video",
            "captions": [
                {
                    "label": "English (auto-generated)",
                    "languageCode": "en",
                    "url": "/api/v1/captions/test123?label=English+%28auto-generated%29",
                }
            ],
        }
        result = invidious_to_video_response(info, base_url="http://localhost")
        assert len(result.captions) == 1
        caption = result.captions[0]
        assert caption.languageCode == "en"
        assert "lang=en" in caption.url
        assert "auto=true" in caption.url

    def test_mixed_auto_and_regional_captions(self):
        """Test video with both auto-generated and regional manual captions.

        This is the real-world case: a video has 'English (auto-generated)' and
        'English (United States)' captions, both with languageCode 'en' from
        Invidious. The manual caption should become 'en-US'.
        """
        info = {
            "videoId": "test123",
            "title": "Test Video",
            "captions": [
                {
                    "label": "English (auto-generated)",
                    "languageCode": "en",
                    "url": "/api/v1/captions/test123?label=English+%28auto-generated%29",
                },
                {
                    "label": "English (United States)",
                    "languageCode": "en",
                    "url": "/api/v1/captions/test123?label=English+%28United+States%29",
                },
            ],
        }
        result = invidious_to_video_response(info, base_url="http://localhost")
        assert len(result.captions) == 2

        # Find captions by label
        auto_caption = next(c for c in result.captions if "auto-generated" in c.label)
        manual_caption = next(c for c in result.captions if "United States" in c.label)

        # Auto-generated should use base code
        assert auto_caption.languageCode == "en"
        assert "lang=en" in auto_caption.url
        assert "auto=true" in auto_caption.url

        # Manual should use full locale
        assert manual_caption.languageCode == "en-US"
        assert "lang=en-US" in manual_caption.url
        assert "auto=true" not in manual_caption.url

    def test_portuguese_regional_variants(self):
        """Test Portuguese regional variants are correctly handled."""
        info = {
            "videoId": "test123",
            "title": "Test Video",
            "captions": [
                {
                    "label": "Portuguese (Brazil)",
                    "languageCode": "pt",
                    "url": "/api/v1/captions/test123?label=Portuguese+%28Brazil%29",
                },
                {
                    "label": "Portuguese (Portugal)",
                    "languageCode": "pt",
                    "url": "/api/v1/captions/test123?label=Portuguese+%28Portugal%29",
                },
            ],
        }
        result = invidious_to_video_response(info, base_url="http://localhost")
        assert len(result.captions) == 2

        brazil_caption = next(c for c in result.captions if "Brazil" in c.label)
        portugal_caption = next(c for c in result.captions if "Portugal" in c.label)

        assert brazil_caption.languageCode == "pt-BR"
        assert "lang=pt-BR" in brazil_caption.url

        assert portugal_caption.languageCode == "pt-PT"
        assert "lang=pt-PT" in portugal_caption.url

    def test_caption_without_region_keeps_base_code(self):
        """Test that captions without regional info keep base language code."""
        info = {
            "videoId": "test123",
            "title": "Test Video",
            "captions": [
                {
                    "label": "Japanese",
                    "languageCode": "ja",
                    "url": "/api/v1/captions/test123?label=Japanese",
                }
            ],
        }
        result = invidious_to_video_response(info, base_url="http://localhost")
        assert len(result.captions) == 1
        caption = result.captions[0]
        assert caption.languageCode == "ja"
        assert "lang=ja" in caption.url

    def test_caption_with_unknown_region_keeps_base_code(self):
        """Test that unknown regions in labels don't modify the language code."""
        info = {
            "videoId": "test123",
            "title": "Test Video",
            "captions": [
                {
                    "label": "Chinese (Simplified)",
                    "languageCode": "zh",
                    "url": "/api/v1/captions/test123?label=Chinese+%28Simplified%29",
                }
            ],
        }
        result = invidious_to_video_response(info, base_url="http://localhost")
        assert len(result.captions) == 1
        caption = result.captions[0]
        # "Simplified" is not a region, so should keep base code
        assert caption.languageCode == "zh"
        assert "lang=zh" in caption.url

    def test_caption_urls_include_token_when_user_id_provided(self):
        """Test that caption URLs include token when user_id is provided."""
        info = {
            "videoId": "test123",
            "title": "Test Video",
            "captions": [
                {
                    "label": "English",
                    "languageCode": "en",
                    "url": "/api/v1/captions/test123?label=English",
                }
            ],
        }
        result = invidious_to_video_response(info, base_url="http://localhost", user_id=1)
        assert len(result.captions) == 1
        caption = result.captions[0]
        assert "token=" in caption.url

    def test_caption_urls_no_token_without_user_id(self):
        """Test that caption URLs don't include token when user_id is not provided."""
        info = {
            "videoId": "test123",
            "title": "Test Video",
            "captions": [
                {
                    "label": "English",
                    "languageCode": "en",
                    "url": "/api/v1/captions/test123?label=English",
                }
            ],
        }
        result = invidious_to_video_response(info, base_url="http://localhost")
        assert len(result.captions) == 1
        caption = result.captions[0]
        assert "token=" not in caption.url
