"""Tests for ops/datastore_adoption.py (demo project)."""

from ops.datastore_adoption import (
    adoption_report,
    adoption_summary,
    check_adoption,
    demo_candidates,
)


def _ready_candidate():
    return {
        "name": "candidate-a",
        "replicas": 3,
        "p99_read_ms": 4.0,
        "p99_write_ms": 9.0,
        "durable_writes": True,
        "backups_enabled": True,
        "backup_restore_test_age_days": 12,
        "failover_test_age_days": 40,
        "observability": True,
        "encryption_at_rest": True,
        "data_residency_ok": True,
    }


def _statuses(checks):
    return {c["name"]: c["status"] for c in checks}


def test_ready_candidate_adopts():
    summary = adoption_summary(_ready_candidate())
    assert summary["verdict"] == "adopt"
    assert summary["checks_passed"] == summary["checks_total"] == 10
    assert summary["failed_checks"] == []


def test_missing_durable_writes_is_not_ready():
    candidate = _ready_candidate()
    candidate["durable_writes"] = False
    summary = adoption_summary(candidate)
    assert summary["verdict"] == "not ready"
    assert "durable-writes" in summary["failed_checks"]


def test_too_few_replicas_is_not_ready():
    candidate = _ready_candidate()
    candidate["replicas"] = 2
    assert adoption_summary(candidate)["verdict"] == "not ready"
    assert _statuses(check_adoption(candidate))["replication"] == "fail"


def test_stale_failover_test_is_pilot_only():
    candidate = _ready_candidate()
    candidate["failover_test_age_days"] = 140
    summary = adoption_summary(candidate)
    assert summary["verdict"] == "pilot"
    assert summary["failed_checks"] == ["failover-test"]


def test_slow_p99_write_and_missing_observability_are_pilot():
    candidate = _ready_candidate()
    candidate["p99_write_ms"] = 31.0
    candidate["observability"] = False
    summary = adoption_summary(candidate)
    assert summary["verdict"] == "pilot"
    assert set(summary["failed_checks"]) == {"p99-write", "observability"}


def test_demo_candidates_cover_all_three_verdicts():
    verdicts = {adoption_summary(c)["verdict"] for c in demo_candidates()}
    assert verdicts == {"adopt", "pilot", "not ready"}
    report = adoption_report(demo_candidates())
    assert "cache-store: adopt" in report
    assert "analytics-store: pilot" in report
    assert "sharded-store: not ready" in report
