"""Tests for the evidence report and the rendered validation report."""

import pytest

from security_analytics.anomalies import find_all_anomalies
from security_analytics.checks import run_all_checks
from security_analytics.data import generate_all
from security_analytics.evidence import build_evidence, evidence_completeness
from security_analytics.kpis import compute_kpis
from security_analytics.pipeline import (
    connect,
    create_tables,
    load_dimensions,
    load_raw,
    normalize,
    table_counts,
)
from security_analytics.report import render_report


@pytest.fixture
def full_run(tmp_path):
    data = generate_all()
    conn = connect(tmp_path / "test.db")
    create_tables(conn)
    load_raw(conn, data)
    load_dimensions(conn, data)
    result = normalize(conn, data)
    counts = table_counts(conn)
    counts.update(result)
    kpis = compute_kpis(conn)
    anomalies = find_all_anomalies(conn)
    checks = run_all_checks(data)
    evidence = build_evidence(kpis, anomalies, checks)
    yield conn, counts, kpis, anomalies, checks, evidence
    conn.close()


def test_evidence_report(full_run):
    _, _, _, _, _, evidence = full_run
    assert len(evidence) == 5
    assert evidence_completeness(evidence) == 100.0
    by_id = {e["control_id"]: e for e in evidence}
    assert by_id["CTRL-01"]["passed"] is False  # MFA 75%, threshold 100%
    assert by_id["CTRL-01"]["value"] == "75.0%"
    assert by_id["CTRL-02"]["passed"] is False  # 2 dormant privileged
    assert by_id["CTRL-03"]["passed"] is False  # 6 overdue findings
    assert by_id["CTRL-04"]["passed"] is False  # travel + brute force found
    assert by_id["CTRL-05"]["passed"] is False  # 11 quarantined rows
    for e in evidence:
        assert e["checked"]  # every control has evidence text
        assert e["threshold"]


def test_evidence_completeness_empty():
    assert evidence_completeness([]) == 0.0


def test_report_renders(full_run):
    _, counts, kpis, anomalies, checks, evidence = full_run
    report = render_report(
        checks=checks,
        counts=counts,
        kpis=kpis,
        anomalies=anomalies,
        evidence=evidence,
        evidence_pct=evidence_completeness(evidence),
    )
    assert "MFA coverage (privileged): 75.0%" in report
    assert "Stale privileged access: 25.0%" in report
    assert "Overdue findings: 6 of 58" in report
    assert "Checks: 3 of 13 passed" in report
    assert "Quarantined rows:     11" in report
    assert "CTRL-01 [FAIL]" in report
    assert "Evidence completeness: 100.0%" in report
    assert "id-003" in report
    assert "synthetic" in report
