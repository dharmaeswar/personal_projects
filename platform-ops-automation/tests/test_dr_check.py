"""Tests for ops/dr_check.py (demo project)."""

from datetime import date

from ops.dr_check import check_readiness, demo_config, readiness_report

TODAY = date(2026, 11, 19)


def _fresh_config():
    return {
        "runbook_last_reviewed": "2026-11-01",
        "last_failover_test": "2026-11-10",
        "backup_last_verified": "2026-11-18",
        "oncall_roster_filled": True,
    }


def _statuses(checks):
    return {c["name"]: c["status"] for c in checks}


def test_all_fresh_passes():
    checks = check_readiness(_fresh_config(), TODAY)
    assert _statuses(checks) == {
        "runbook-reviewed": "pass",
        "failover-tested": "pass",
        "backup-verified": "pass",
        "oncall-roster-filled": "pass",
    }
    report = readiness_report(checks)
    assert report["overall"] == "pass"
    assert report["passed"] == 4
    assert report["failed"] == 0


def test_stale_failover_fails():
    config = _fresh_config()
    config["last_failover_test"] = "2026-07-22"
    checks = check_readiness(config, TODAY)
    assert _statuses(checks)["failover-tested"] == "fail"
    report = readiness_report(checks)
    assert report["overall"] == "fail"
    assert report["failed_checks"] == ["failover-tested"]


def test_stale_backup_fails():
    config = _fresh_config()
    config["backup_last_verified"] = "2026-11-01"
    checks = check_readiness(config, TODAY)
    assert _statuses(checks)["backup-verified"] == "fail"


def test_stale_runbook_fails():
    config = _fresh_config()
    config["runbook_last_reviewed"] = "2026-01-01"
    checks = check_readiness(config, TODAY)
    assert _statuses(checks)["runbook-reviewed"] == "fail"


def test_roster_gap_fails():
    config = _fresh_config()
    config["oncall_roster_filled"] = False
    checks = check_readiness(config, TODAY)
    assert _statuses(checks)["oncall-roster-filled"] == "fail"


def test_demo_config_has_one_failure():
    checks = check_readiness(demo_config(), TODAY)
    report = readiness_report(checks)
    assert report["overall"] == "fail"
    assert report["failed"] == 1
    assert report["failed_checks"] == ["failover-tested"]
