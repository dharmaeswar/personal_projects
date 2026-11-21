"""Tests for window-function transforms: sessions, retention, funnel, DAU."""
from product_analytics import db, ingest, transforms


def _load(conn, rows):
    ingest.load_raw(conn, rows)
    ingest.build_staging(conn)


def _event(eid, user, etype, ts, payload=None):
    return {"event_id": eid, "user_id": user, "event_type": etype,
            "event_ts": ts, "payload": payload or {}}


def test_sessionization_splits_on_gap():
    conn = db.connect()
    _load(conn, [
        _event("e1", "u1", "page_view", "2026-11-03T10:00:00", {"page": "home"}),
        _event("e2", "u1", "pin_save", "2026-11-03T10:10:00", {"pin_id": "p1", "board_id": "b"}),
        _event("e3", "u1", "page_view", "2026-11-03T12:00:00", {"page": "home"}),
    ])
    result = transforms.build_sessions(conn)
    assert result["sessions"] == 2
    sessions = conn.execute(
        "SELECT event_count FROM sessions ORDER BY started_at").fetchall()
    assert [s[0] for s in sessions] == [2, 1]


def test_session_duration_uses_window_bounds():
    conn = db.connect()
    _load(conn, [
        _event("e1", "u1", "page_view", "2026-11-03T10:00:00", {"page": "home"}),
        _event("e2", "u1", "pin_click", "2026-11-03T10:15:00", {"pin_id": "p1"}),
    ])
    transforms.build_sessions(conn)
    row = conn.execute("SELECT duration_sec FROM sessions").fetchone()
    assert row[0] == 900


def test_retention_counts_day_7_return():
    conn = db.connect()
    _load(conn, [
        _event("e1", "u1", "page_view", "2026-11-01T10:00:00", {"page": "home"}),
        _event("e2", "u1", "page_view", "2026-11-08T10:00:00", {"page": "home"}),
        _event("e3", "u2", "page_view", "2026-11-01T10:00:00", {"page": "home"}),
    ])
    rows = transforms.retention(conn, cohort_days=7)
    day7 = [r for r in rows if r["day_n"] == 7 and r["cohort_date"] == "2026-11-01"]
    assert len(day7) == 1 and day7[0]["users"] == 1


def test_funnel_requires_ordered_steps():
    conn = db.connect()
    _load(conn, [
        _event("e1", "u1", "page_view", "2026-11-03T10:00:00", {"page": "home"}),
        _event("e2", "u1", "pin_save", "2026-11-03T10:01:00", {"pin_id": "p1", "board_id": "b"}),
        _event("e3", "u1", "pin_click", "2026-11-03T10:02:00", {"pin_id": "p1"}),
        _event("e4", "u2", "pin_click", "2026-11-03T10:00:00", {"pin_id": "p2"}),
    ])
    funnel = transforms.funnel(conn, "2026-11-03")
    assert funnel["viewers"] == 1
    assert funnel["savers"] == 1
    assert funnel["clickers"] == 1
    assert transforms.dau(conn, "2026-11-03") == 2
