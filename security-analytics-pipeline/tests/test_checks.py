"""Tests for the data-quality checks."""

from security_analytics.checks import (
    check_completeness,
    check_duplicates,
    run_all_checks,
)
from security_analytics.data import generate_all


def test_checks_find_planted_rows():
    data = generate_all()
    results = run_all_checks(data)
    assert len(results) == 13
    passed = [r for r in results if r.passed]
    failed = [r for r in results if not r.passed]
    assert len(passed) == 3
    assert len(failed) == 10
    by_name = {r.name: r for r in results}
    assert by_name["login events complete"].failing_ids == ["login-901", "login-902"]
    assert sorted(by_name["login event_id unique"].failing_ids) == [
        "login-0010",
        "login-0050",
    ]
    assert by_name["login identity references resolve"].failing_ids == [
        "login-903",
        "login-904",
    ]
    assert by_name["audit asset references resolve"].failing_ids == ["audit-901"]
    assert by_name["audit identity references resolve"].failing_ids == ["audit-902"]
    assert by_name["audit event_id unique"].failing_ids == ["audit-0005"]
    assert by_name["finding asset references resolve"].failing_ids == ["find-060"]
    assert by_name["finding dates valid (due_date >= discovered_date)"].failing_ids == [
        "find-059"
    ]
    assert by_name["login events not late"].failing_ids == ["login-905", "login-906"]
    assert by_name["finding discovered_date not in the future"].failing_ids == [
        "find-059"
    ]
    assert by_name["audit events complete"].passed
    assert by_name["findings complete"].passed
    assert by_name["audit events not late"].passed


def test_checks_pass_on_clean_fixture():
    rows = [
        {"event_id": "e1", "identity_id": "id-001", "ts": "2026-11-02T10:00:00"},
        {"event_id": "e2", "identity_id": "id-002", "ts": "2026-11-02T11:00:00"},
    ]
    assert check_completeness(rows, ["event_id", "identity_id", "ts"], "clean").passed
    assert check_duplicates(rows, "event_id", "clean").passed
