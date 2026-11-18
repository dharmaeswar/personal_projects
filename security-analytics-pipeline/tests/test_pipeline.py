"""End-to-end pipeline tests: staging, normalization, quarantine, lineage."""

import sqlite3
from pathlib import Path

import pytest

from security_analytics.data import generate_all
from security_analytics.pipeline import (
    connect,
    create_tables,
    load_dimensions,
    load_raw,
    normalize,
    table_counts,
)


@pytest.fixture
def built_db(tmp_path):
    data = generate_all()
    conn = connect(tmp_path / "test.db")
    create_tables(conn)
    load_raw(conn, data)
    load_dimensions(conn, data)
    result = normalize(conn, data)
    yield conn, data, result
    conn.close()


def test_end_to_end_counts(built_db):
    conn, data, result = built_db
    counts = table_counts(conn)
    assert counts["raw_login_events"] == 316
    assert counts["raw_audit_events"] == 153
    assert counts["raw_findings"] == 60
    assert counts["identities"] == 40
    assert counts["assets"] == 30
    assert counts["events"] == 460
    assert counts["findings"] == 58
    assert counts["quarantine"] == 11
    assert result["events"] == 460
    assert result["findings"] == 58
    assert result["quarantine"] == 11
    late = conn.execute(
        "SELECT COUNT(*) FROM events WHERE late_arriving = 1"
    ).fetchone()[0]
    assert late == 2


def test_lineage_maps_every_normalized_row(built_db):
    conn, data, result = built_db
    lineage = result["lineage"]
    assert len(lineage) == 460 + 58
    event_ids = {
        r[0] for r in conn.execute("SELECT event_id FROM events").fetchall()
    }
    finding_ids = {
        r[0] for r in conn.execute("SELECT finding_id FROM findings").fetchall()
    }
    assert set(lineage) == event_ids | finding_ids
    assert lineage["login-0001"] == "raw_login_events"
    assert lineage["audit-0001"] == "raw_audit_events"
    assert lineage["find-001"] == "raw_findings"


def test_quarantine_reasons(built_db):
    conn, data, result = built_db
    reasons = {
        r[0]: r[1]
        for r in conn.execute(
            "SELECT reason, COUNT(*) FROM quarantine GROUP BY reason"
        ).fetchall()
    }
    assert reasons == {
        "duplicate event_id": 3,
        "null identity_id": 2,
        "unknown identity_id": 3,
        "unknown asset_id": 2,
        "due_date before discovered_date": 1,
    }
    quarantined_ids = {
        r[0] for r in conn.execute("SELECT source_id FROM quarantine").fetchall()
    }
    assert "login-0010" in quarantined_ids
    assert "find-059" in quarantined_ids
    assert "find-060" in quarantined_ids


def test_normalized_events_keep_source_types(built_db):
    conn, data, result = built_db
    types = {
        r[0]: r[1]
        for r in conn.execute(
            "SELECT event_type, COUNT(*) FROM events GROUP BY event_type"
        ).fetchall()
    }
    assert types == {"login": 310, "audit": 150}
