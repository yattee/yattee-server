"""Audio track selection for fast downloads on multi-language videos."""

from routers.proxy._fast_download import _prefer_original_track, _track_rank


def _fmt(format_id, language, pref, note=""):
    return {
        "format_id": format_id,
        "language": language,
        "language_preference": pref,
        "format_note": note,
        "vcodec": "none",
        "acodec": "mp4a.40.2",
        "abr": 129.4,
    }


def test_original_track_wins_over_list_order():
    formats = [
        _fmt("140-0", "bn", -1, "Bangla, medium"),
        _fmt("140-1", "de-DE", -1, "German (DE), medium"),
        _fmt("140-18", "en-US", 10, "English (US) original (default), medium"),
    ]
    assert _prefer_original_track(formats)["format_id"] == "140-18"


def test_single_track_is_returned():
    only = _fmt("140", "en", 0)
    assert _prefer_original_track([only]) is only


def test_ties_keep_list_order():
    formats = [_fmt("140-0", None, None), _fmt("140-1", None, None)]
    assert _prefer_original_track(formats)["format_id"] == "140-0"


def test_falls_back_to_format_note_when_preference_missing():
    dub = {"format_id": "140-0", "format_note": "German, medium"}
    orig = {"format_id": "140-1", "format_note": "English original (default), medium"}
    assert _track_rank(orig) > _track_rank(dub)
    assert _prefer_original_track([dub, orig]) is orig


def test_no_candidates():
    assert _prefer_original_track([]) is None
