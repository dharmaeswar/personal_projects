"""Tests for anomaly detection."""

import pytest

from security_analytics.anomalies import find_all_anomalies
from security_analytics.data import generate_all
from security_analytics.pipeline import (
    connect,
    create_tables,
    load_dimensions,
    load_raw,
    normalize,
)


@pytest.fixture
def db(tmp_path):
    data = generate_all()
    conn = connect(tmp_path / "test.db")
    create_tables(conn)
    load_raw(conn, data)
    load_dimensions(conn, data)
    normalize(conn, data)
    yield conn
    conn.close()


def test_impossible_travel_detected(db):
    anomalies = find_all_anomalies(db)
    travel = anomalies["impossible_travel"]
    assert len(travel) == 1
    pair = travel[0]
    assert pair["identity_id"] == "id-003"
    assert pair["first_country"] == "US"
    assert pair["second_country"] == "JP"
    assert pair["gap_minutes"] == 30.0


def test_dormant_privileged_detected(db):
    anomalies = find_all_anomalies(db)
    dormant = anomalies["dormant_privileged"]
    assert {d["identity_id"] for d in dormant} == {"id-001", "id-021"}
    assert all(d["last_login_days_ago"] > 90 for d in dormant)


def test_overdue_findings_detected(db):
    anomalies = find_all_anomalies(db)
    overdue = anomalies["overdue_findings"]
    assert len(overdue) == 6
    assert {o["finding_id"] for o in overdue} == {
        f"find-{n:03d}" for n in range(21, 27)
    }
    assert all(o["due_date"][:10] == "2026-11-13" for o in overdue)


def test_brute_force_detected(db):
    anomalies = find_all_anomalies(db)
    bursts = anomalies["brute_force"]
    assert len(bursts) == 1
    burst = bursts[0]
    assert burst["identity_id"] == "id-007"
    assert burst["failed_logins"] == 6
    assert burst["ip"] == "198.51.100.44"
    assert burst["event_ids"] == [f"login-{n}" for n in range(909, 915)]
