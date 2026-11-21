"""Tests for data-quality checks, catalog generation and query optimization."""
from product_analytics import catalog, db, ingest, optimize, quality, transforms


def _conn_with_data():
    conn = db.connect()
    ingest.load_raw(conn, [
        {"event_id": "e1", "user_id": "u1", "event_type": "page_view",
         "event_ts": "2026-11-03T10:00:00", "payload": {"page": "home"}},
        {"event_id": "e2", "user_id": "u2", "event_type": "pin_save",
         "event_ts": "2026-11-03T10:05:00", "payload": {"pin_id": "p1", "board_id": "b"}},
    ])
    ingest.build_staging(conn)
    transforms.build_sessions(conn)
    return conn


def test_quality_checks_all_pass_on_clean_data():
    conn = _conn_with_data()
    checks = quality.run_checks(conn, "2026-11-03")
    assert quality.all_passed(checks)
    assert {c["check"] for c in checks} == {
        "no_null_users", "unique_event_ids", "valid_timestamps",
        "quarantine_reviewed", "freshness",
    }


def test_freshness_fails_when_latest_date_is_wrong():
    conn = _conn_with_data()
    checks = quality.run_checks(conn, "2026-11-04")
    freshness = [c for c in checks if c["check"] == "freshness"][0]
    assert freshness["status"] == "fail"
    assert not quality.all_passed(checks)


def test_catalog_lists_tables_metrics_and_checks(tmp_path):
    conn = _conn_with_data()
    quality.run_checks(conn, "2026-11-03")
    path = str(tmp_path / "CATALOG.md")
    text = catalog.generate(conn, path)
    assert "staged_events" in text
    assert "dau" in text
    assert "no_null_users" in text


def test_partition_query_matches_full_table():
    conn = _conn_with_data()
    result = optimize.compare(conn, "2026-11-03")
    assert result["distinct_users"] == 2
    assert result["partition_scans_table"] is True
    assert any("events_20261103" in line for line in result["partition_plan"])
    assert not any("events_20261103" in line for line in result["full_table_plan"])
