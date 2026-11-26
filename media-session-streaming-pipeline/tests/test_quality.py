from datetime import datetime, timezone

import pytest

from session_stream.quality import check_event, cleanse, quarantine_summary


def _ev(**over):
    ev = {
        "event_id": "e1", "session_id": "s1", "user_id": "u1",
        "title_id": "title-001", "device": "tv", "region": "us-west",
        "app": "video", "event_type": "heartbeat",
        "event_ts": datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc),
        "playhead_seconds": 30.0, "bitrate_kbps": 4500,
    }
    ev.update(over)
    return ev


def test_clean_event_has_no_issues():
    assert check_event(_ev()) == []


def test_missing_field_flagged():
    ev = _ev()
    del ev["title_id"]
    issues = check_event(ev)
    assert issues == ["missing:title_id"]


def test_bad_event_type_flagged():
    assert any(i.startswith("bad_event_type") for i in
               check_event(_ev(event_type="rewind")))


def test_bad_device_flagged():
    assert any(i.startswith("bad_device") for i in
               check_event(_ev(device="toaster")))


def test_negative_playhead_flagged():
    assert "negative_playhead" in check_event(_ev(playhead_seconds=-5))


def test_playhead_too_large_flagged():
    assert "playhead_too_large" in check_event(_ev(playhead_seconds=999999))


def test_bitrate_bounds_flagged():
    assert "negative_bitrate" in check_event(_ev(bitrate_kbps=-1))
    assert "bitrate_too_large" in check_event(_ev(bitrate_kbps=999999))


def test_cleanse_splits_good_and_bad():
    good, quar = cleanse([_ev(), _ev(event_id="e2", event_type="nope"),
                          _ev(event_id="e3", bitrate_kbps=-3)])
    assert len(good) == 1 and len(quar) == 2
    assert all("quarantine_reason" in q for q in quar)


def test_cleanse_dedupes_event_ids():
    good, quar = cleanse([_ev(), _ev()])
    assert len(good) == 1 and len(quar) == 1
    assert quar[0]["quarantine_reason"] == "duplicate_event_id"


def test_cleanse_empty():
    assert cleanse([]) == ([], [])


def test_quarantine_summary_counts_reasons():
    _, quar = cleanse([_ev(event_id="e2", event_type="nope"),
                       _ev(event_id="e3", event_type="nope"),
                       _ev(event_id="e4", bitrate_kbps=-1)])
    summary = quarantine_summary(quar)
    assert summary["count"].sum() == 3
    assert len(summary) == 2


def test_quarantine_summary_empty():
    summary = quarantine_summary([])
    assert summary.empty
    assert list(summary.columns) == ["quarantine_reason", "count"]
