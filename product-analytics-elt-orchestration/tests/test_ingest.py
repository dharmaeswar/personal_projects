"""Tests for ingest and staging (dedupe, quarantine, partitioning)."""
from product_analytics import db, ingest, seed


def _events():
    return [
        {"event_id": "e1", "user_id": "u1", "event_type": "page_view",
         "event_ts": "2026-11-03T10:00:00", "payload": {"page": "home"}},
        {"event_id": "e2", "user_id": "u1", "event_type": "pin_save",
         "event_ts": "2026-11-03T10:05:00", "payload": {"pin_id": "p1", "board_id": "b1"}},
        {"event_id": "e1", "user_id": "u1", "event_type": "page_view",
         "event_ts": "2026-11-03T10:00:00", "payload": {"page": "home"}},
        {"event_id": "e3", "user_id": "", "event_type": "page_view",
         "event_ts": "2026-11-03T10:00:00", "payload": {"page": "home"}},
    ]


def test_load_raw_quarantines_bad_rows():
    conn = db.connect()
    result = ingest.load_raw(conn, _events())
    assert result["loaded"] == 3  # e1 twice counts as valid twice at load time
    assert result["quarantined"] == 1
    assert conn.execute("SELECT COUNT(*) FROM raw_events").fetchone()[0] == 2
    assert conn.execute("SELECT COUNT(*) FROM quarantine").fetchone()[0] == 1


def test_build_staging_dedupes_and_partitions():
    conn = db.connect()
    ingest.load_raw(conn, _events())
    result = ingest.build_staging(conn)
    assert result["staged"] == 2  # duplicate e1 staged once
    assert result["partitions"] == 1
    assert conn.execute("SELECT COUNT(*) FROM events_20261103").fetchone()[0] == 2
    assert conn.execute("SELECT COUNT(*) FROM events_all").fetchone()[0] == 2


def test_seed_data_is_deterministic():
    first = seed.generate_events(count=100)
    second = seed.generate_events(count=100)
    assert first == second
    assert len(first) == 104  # 100 generated + 4 deliberately broken rows
