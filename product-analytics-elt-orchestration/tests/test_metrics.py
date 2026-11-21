"""Tests for metric definitions as code."""
import pytest

from product_analytics import db, ingest, metrics, transforms


def _conn_with_data():
    conn = db.connect()
    ingest.load_raw(conn, [
        {"event_id": "e1", "user_id": "u1", "event_type": "page_view",
         "event_ts": "2026-11-03T10:00:00", "payload": {"page": "home"}},
        {"event_id": "e2", "user_id": "u1", "event_type": "pin_save",
         "event_ts": "2026-11-03T10:01:00", "payload": {"pin_id": "p1", "board_id": "b"}},
        {"event_id": "e3", "user_id": "u2", "event_type": "page_view",
         "event_ts": "2026-11-03T10:00:00", "payload": {"page": "home"}},
    ])
    ingest.build_staging(conn)
    transforms.build_sessions(conn)
    return conn


def test_dau_metric_is_stored():
    conn = _conn_with_data()
    result = metrics.compute(conn, "dau", "2026-11-03")
    assert result["rows"] == [{"dimension": "", "value": 2.0}]
    stored = conn.execute(
        "SELECT value FROM metric_results WHERE metric_name = 'dau'").fetchone()
    assert stored[0] == 2.0


def test_sessions_per_user_metric():
    conn = _conn_with_data()
    result = metrics.compute(conn, "sessions_per_user", "2026-11-03")
    assert result["rows"][0]["value"] == 1.0


def test_funnel_metric_stores_each_step():
    conn = _conn_with_data()
    result = metrics.compute(conn, "funnel_view_save_click", "2026-11-03")
    dims = {r["dimension"]: r["value"] for r in result["rows"]}
    assert dims == {"viewed": 2.0, "saved": 1.0, "clicked": 0.0}


def test_unknown_metric_raises():
    conn = db.connect()
    with pytest.raises(ValueError):
        metrics.compute(conn, "not_a_metric", "2026-11-03")


def test_compute_all_covers_every_definition():
    conn = _conn_with_data()
    results = metrics.compute_all(conn, "2026-11-03")
    assert {r["metric"] for r in results} == set(metrics.DEFINITIONS)
