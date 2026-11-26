from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from session_stream.streaming import (
    apply_watermark, process_micro_batches, sessionize, to_frame,
    tumbling_aggregates,
)

T0 = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)


def _ev(sid, minutes, etype="heartbeat", playhead=30.0, bitrate=4500,
        title="title-001"):
    return {
        "event_id": f"{sid}-{minutes}", "session_id": sid, "user_id": "u1",
        "title_id": title, "device": "tv", "region": "us-west",
        "app": "video", "event_type": etype,
        "event_ts": T0 + timedelta(minutes=minutes),
        "playhead_seconds": playhead, "bitrate_kbps": bitrate,
    }


def test_to_frame_empty():
    assert to_frame([]).empty


def test_watermark_keeps_on_time_events():
    df = to_frame([_ev("s1", 0), _ev("s1", 5), _ev("s1", 20)])
    on_time, late, seen = apply_watermark(df, allowed_lateness_minutes=25)
    assert len(on_time) == 3 and len(late) == 0
    assert seen == T0 + timedelta(minutes=20)


def test_process_micro_batches_keeps_in_order_events():
    from session_stream.events import generate_sessions
    df = to_frame(generate_sessions(5, seed=42))
    on_time, late = process_micro_batches(df)
    assert len(on_time) == len(df) and len(late) == 0


def test_process_micro_batches_catches_out_of_order_event():
    from session_stream.events import generate_sessions
    df = to_frame(generate_sessions(5, seed=42))
    # A stale event that ARRIVES last, hours behind the watermark.
    late_ev = _ev("s-late", 0, etype="heartbeat")
    late_ev["event_ts"] = T0  # far behind the generated stream's max
    combined = pd.concat([df, to_frame([late_ev])], ignore_index=True)
    on_time, late = process_micro_batches(combined)
    assert len(late) >= 1
    assert "s-late" in set(late["session_id"])


def test_watermark_flags_late_events():
    df = to_frame([_ev("s1", 0), _ev("s1", 60)])
    _, _, seen = apply_watermark(df, allowed_lateness_minutes=10)
    late_ev = to_frame([_ev("s1", 5, etype="seek")])
    on_time, late, _ = apply_watermark(
        late_ev, allowed_lateness_minutes=10, max_seen_ts=seen)
    assert len(late) == 1 and len(on_time) == 0


def test_watermark_empty_frame():
    on_time, late, seen = apply_watermark(pd.DataFrame())
    assert on_time.empty and late.empty and seen is None


def test_sessionize_one_session():
    evs = [_ev("s1", 0, "session_start", 0.0),
           _ev("s1", 1, playhead=30.0),
           _ev("s1", 2, "session_end", 60.0)]
    sessions = sessionize(to_frame(evs))
    assert len(sessions) == 1
    row = sessions.iloc[0]
    assert row["event_count"] == 3
    assert row["duration_seconds"] == 120.0
    assert row["max_playhead_seconds"] == 60.0
    assert row["error_count"] == 0


def test_sessionize_splits_on_gap():
    evs = [_ev("s1", 0, "session_start", 0.0),
           _ev("s1", 1, playhead=30.0),
           _ev("s1", 60, playhead=90.0),
           _ev("s1", 61, "session_end", 120.0)]
    sessions = sessionize(to_frame(evs), gap_minutes=30)
    assert len(sessions) == 2
    assert sorted(sessions["event_count"]) == [2, 2]


def test_sessionize_counts_errors():
    evs = [_ev("s1", 0, "session_start", 0.0),
           _ev("s1", 1, "error", 30.0, bitrate=0),
           _ev("s1", 2, "error", 30.0, bitrate=0),
           _ev("s1", 3, "session_end", 60.0)]
    sessions = sessionize(to_frame(evs))
    assert sessions.iloc[0]["error_count"] == 2


def test_sessionize_empty():
    assert sessionize(pd.DataFrame()).empty


def test_tumbling_aggregates():
    evs = [_ev("s1", 0, "session_start", 0.0),
           _ev("s1", 1, playhead=30.0),
           _ev("s2", 2, "session_start", 0.0, title="title-002"),
           _ev("s1", 16, "session_start", 0.0)]
    agg = tumbling_aggregates(to_frame(evs), window_minutes=15)
    assert len(agg) == 3  # two titles in window 0, one title in window 1
    w0 = agg[agg["title_id"] == "title-001"]
    assert w0.iloc[0]["plays"] == 1
    assert w0.iloc[0]["distinct_sessions"] == 1
    assert w0.iloc[0]["avg_bitrate_kbps"] == 4500.0


def test_tumbling_aggregates_empty():
    assert tumbling_aggregates(pd.DataFrame()).empty
