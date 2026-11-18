"""Tests for KPI computation, including math on a hand-built fixture."""

import pytest
from datetime import datetime

from security_analytics.data import generate_all
from security_analytics.kpis import compute_kpis
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
    yield conn, data
    conn.close()


def test_kpi_values_on_generated_data(db):
    conn, data = db
    kpis = compute_kpis(conn)
    assert kpis["total_identities"] == 40
    assert kpis["privileged_identities"] == 8
    assert kpis["privileged_with_mfa"] == 6
    assert kpis["mfa_coverage_privileged_pct"] == 75.0
    assert kpis["mfa_coverage_all_pct"] == 92.5
    assert kpis["dormant_privileged"] == 2
    assert kpis["stale_access_pct"] == 25.0
    assert kpis["total_events"] == 460
    assert kpis["late_events"] == 2
    assert kpis["quarantined_rows"] == 11
    assert kpis["total_findings"] == 58
    assert kpis["remediated_findings"] == 20
    assert kpis["open_findings"] == 38
    assert kpis["overdue_findings"] == 6
    assert 2.0 <= kpis["mttr_days"] <= 12.0
    # MFA login usage must match the normalized events table exactly.
    successful = conn.execute(
        "SELECT COUNT(*) FROM events WHERE event_type='login' AND success=1"
    ).fetchone()[0]
    with_mfa = conn.execute(
        "SELECT COUNT(*) FROM events WHERE event_type='login' "
        "AND success=1 AND mfa_used=1"
    ).fetchone()[0]
    assert kpis["successful_logins"] == successful
    assert kpis["successful_logins_with_mfa"] == with_mfa
    assert kpis["mfa_login_usage_pct"] == round(100.0 * with_mfa / successful, 1)


def _small_data():
    identities = [
        {
            "identity_id": "id-001",
            "name": "A One",
            "email": "a@example.internal",
            "department": "IT",
            "privileged": True,
            "mfa_enabled": True,
            "last_login_days_ago": 5,
            "status": "active",
        },
        {
            "identity_id": "id-002",
            "name": "B Two",
            "email": "b@example.internal",
            "department": "IT",
            "privileged": True,
            "mfa_enabled": False,
            "last_login_days_ago": 200,
            "status": "active",
        },
        {
            "identity_id": "id-003",
            "name": "C Three",
            "email": "c@example.internal",
            "department": "IT",
            "privileged": False,
            "mfa_enabled": True,
            "last_login_days_ago": 1,
            "status": "active",
        },
    ]
    return {
        "identities": identities,
        "assets": [
            {
                "asset_id": "asset-001",
                "hostname": "h1.example.internal",
                "asset_type": "server",
                "owner_identity_id": "id-001",
                "criticality": "high",
                "last_seen_days_ago": 0,
            }
        ],
        "login_events": [],
        "audit_events": [],
        "findings": [
            {
                "finding_id": "find-001",
                "asset_id": "asset-001",
                "severity": "high",
                "title": "t",
                "discovered_date": datetime(2026, 11, 1),
                "due_date": datetime(2026, 11, 15),
                "status": "remediated",
                "remediated_date": datetime(2026, 11, 6),
            },
            {
                "finding_id": "find-002",
                "asset_id": "asset-001",
                "severity": "low",
                "title": "t",
                "discovered_date": datetime(2026, 11, 1),
                "due_date": datetime(2026, 12, 31),
                "status": "open",
                "remediated_date": None,
            },
        ],
    }


def test_kpi_math_on_fixture(tmp_path):
    data = _small_data()
    conn = connect(tmp_path / "fixture.db")
    create_tables(conn)
    load_raw(conn, data)
    load_dimensions(conn, data)
    normalize(conn, data)
    kpis = compute_kpis(conn)
    assert kpis["mfa_coverage_privileged_pct"] == 50.0  # 1 of 2 privileged
    assert kpis["dormant_privileged"] == 1
    assert kpis["stale_access_pct"] == 50.0
    assert kpis["mttr_days"] == 5.0  # Nov 1 -> Nov 6
    assert kpis["overdue_findings"] == 0
    assert kpis["open_findings"] == 1
    assert kpis["staged_rows"] == 2  # 0 events + 0 quarantined + 2 findings
    conn.close()
