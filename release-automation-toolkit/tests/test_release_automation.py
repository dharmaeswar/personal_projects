"""Tests for the release automation toolkit."""

from __future__ import annotations

import sys

import pytest

from release_automation.ci_runner import run_step, run_steps
from release_automation.gates import (
    gate_config_review,
    gate_dependency_freshness,
    gate_migration_safety,
    gate_rollback_plan,
    gate_unit_tests,
    run_readiness_gates,
)
from release_automation.history import (
    connect,
    record_release,
    record_rollout_event,
    release_by_version,
    releases_for_service,
    rollback_count,
    rollout_events_for_release,
)
from release_automation.report import render_report
from release_automation.rollout import (
    HealthThresholds,
    StageMetrics,
    check_health,
    simulate_canary_rollout,
)


def clean_release(**overrides):
    """A release that passes every gate."""
    release = {
        "service": "checkout-api",
        "version": "v2.4.0",
        "author": "dharma",
        "ci": {"unit_tests_passed": True, "commit": "abc123", "tests_run": 18},
        "config": {"diff_present": True, "reviewed_by": "teammate"},
        "migration_sql": "ALTER TABLE orders ADD COLUMN gift_message TEXT;",
        "dependencies": {"requests": (2, 2), "pyyaml": (6, 6)},
        "rollback_plan": {
            "previous_version": "v2.3.1",
            "steps": ["shift traffic back", "verify success rate"],
        },
    }
    release.update(overrides)
    return release


def healthy_metrics(n=4):
    return [
        StageMetrics(error_rate=0.002, p95_latency_ms=180, success_rate=0.998)
        for _ in range(n)
    ]


# --- Gates ---


def test_clean_release_passes_all_gates():
    report = run_readiness_gates(clean_release())
    assert report.passed is True
    assert report.passed_count == 5
    assert report.blocking_reasons == []


def test_failed_unit_tests_block_release():
    release = clean_release(ci={"unit_tests_passed": False, "commit": "abc123"})
    result = gate_unit_tests(release)
    assert result.passed is False
    assert "abc123" in result.reason
    assert run_readiness_gates(release).passed is False


def test_config_without_diff_fails():
    result = gate_config_review(clean_release(config={"diff_present": False}))
    assert result.passed is False
    assert "No config diff" in result.reason


def test_config_without_reviewer_fails():
    result = gate_config_review(clean_release(config={"diff_present": True}))
    assert result.passed is False
    assert "no reviewer" in result.reason


def test_config_self_review_fails():
    release = clean_release(
        config={"diff_present": True, "reviewed_by": "dharma"}
    )
    assert gate_config_review(release).passed is False


def test_migration_with_no_sql_passes():
    assert gate_migration_safety(clean_release(migration_sql="")).passed is True


def test_drop_table_migration_fails():
    result = gate_migration_safety(
        clean_release(migration_sql="DROP TABLE legacy_invoices;")
    )
    assert result.passed is False
    assert "drop table" in result.reason


def test_safe_migration_passes():
    result = gate_migration_safety(
        clean_release(migration_sql="CREATE INDEX idx_orders ON orders (id);")
    )
    assert result.passed is True


def test_stale_dependency_fails():
    result = gate_dependency_freshness(
        clean_release(dependencies={"celery": (3, 5), "requests": (2, 2)})
    )
    assert result.passed is False
    assert "celery" in result.reason


def test_dependency_one_major_behind_passes():
    result = gate_dependency_freshness(
        clean_release(dependencies={"requests": (1, 2)})
    )
    assert result.passed is True


def test_rollback_plan_without_previous_version_fails():
    result = gate_rollback_plan(clean_release(rollback_plan={"steps": ["x"]}))
    assert result.passed is False


def test_rollback_plan_without_steps_fails():
    result = gate_rollback_plan(
        clean_release(rollback_plan={"previous_version": "v2.3.1"})
    )
    assert result.passed is False


def test_blocked_release_lists_every_blocking_reason():
    release = clean_release(
        config={"diff_present": False},
        migration_sql="TRUNCATE TABLE sessions;",
    )
    report = run_readiness_gates(release)
    assert report.passed is False
    assert report.passed_count == 3
    assert len(report.blocking_reasons) == 2


# --- Canary rollout ---


def test_healthy_rollout_completes_at_100_percent():
    result = simulate_canary_rollout(
        "checkout-api", "v2.4.0", "v2.3.1", healthy_metrics()
    )
    assert result.completed is True
    assert result.rolled_back is False
    assert result.stages_completed == 4
    assert result.final_traffic_percent == 100
    assert result.rollback_events == []


def test_error_rate_breach_rolls_back():
    metrics = healthy_metrics()
    metrics[1] = StageMetrics(
        error_rate=0.024, p95_latency_ms=640, success_rate=0.976
    )
    result = simulate_canary_rollout(
        "search-api", "v3.1.0", "v3.0.4", metrics
    )
    assert result.completed is False
    assert result.rolled_back is True
    assert result.stages_completed == 2  # stopped at the 25% stage
    assert result.final_traffic_percent == 0
    assert len(result.rollback_events) == 1
    assert "25%" in result.rollback_events[0]
    assert "v3.0.4" in result.rollback_events[0]


def test_latency_breach_lists_the_breach():
    metrics = [
        StageMetrics(error_rate=0.001, p95_latency_ms=900, success_rate=0.999)
    ]
    result = simulate_canary_rollout(
        "search-api", "v3.1.0", "v3.0.4", metrics, stages=(5, 25, 50, 100)
    )
    assert result.rolled_back is True
    assert "p95 latency 900 ms" in result.stages[0].breaches[0]


def test_check_health_boundary_values_pass():
    metrics = StageMetrics(error_rate=0.01, p95_latency_ms=500, success_rate=0.99)
    assert check_health(metrics, HealthThresholds()) == []


def test_success_rate_breach_rolls_back():
    metrics = [
        StageMetrics(error_rate=0.001, p95_latency_ms=150, success_rate=0.95)
    ]
    result = simulate_canary_rollout(
        "search-api", "v3.1.0", "v3.0.4", metrics
    )
    assert result.rolled_back is True
    assert "success rate" in result.stages[0].breaches[0]


# --- History store ---


def test_history_records_and_queries_releases(tmp_path):
    conn = connect(tmp_path / "history.db")
    record_release(conn, "checkout-api", "v2.4.0", 5, 5)
    record_release(conn, "checkout-api", "v2.3.1", 4, 5, ["config not reviewed"])
    record_release(conn, "search-api", "v3.1.0", 5, 5)

    by_service = releases_for_service(conn, "checkout-api")
    assert len(by_service) == 2
    assert by_service[0]["version"] == "v2.3.1"  # newest first

    one = release_by_version(conn, "checkout-api", "v2.4.0")
    assert one is not None
    assert one["gates_passed"] == 5
    assert release_by_version(conn, "checkout-api", "v9.9.9") is None


def test_history_records_rollout_events_and_counts_rollbacks(tmp_path):
    conn = connect(tmp_path / "history.db")
    record_rollout_event(conn, "search-api", "v3.1.0", 5, "promoted")
    record_rollout_event(
        conn, "search-api", "v3.1.0", 25,
        "Stage 25%: health gate failed; rolled back v3.1.0 -> v3.0.4",
    )
    events = rollout_events_for_release(conn, "search-api", "v3.1.0")
    assert len(events) == 2
    assert events[0]["stage_percent"] == 5
    assert rollback_count(conn, "search-api") == 1
    assert rollback_count(conn, "checkout-api") == 0


def test_history_upserts_same_release(tmp_path):
    conn = connect(tmp_path / "history.db")
    record_release(conn, "checkout-api", "v2.4.0", 3, 5, ["a", "b"])
    record_release(conn, "checkout-api", "v2.4.0", 5, 5)
    rows = releases_for_service(conn, "checkout-api")
    assert len(rows) == 1
    assert rows[0]["gates_passed"] == 5


# --- CI step runner ---


def test_ci_runner_passing_command():
    result = run_step("echo", f"{sys.executable} -c \"print('ok')\"")
    assert result.passed is True
    assert result.returncode == 0
    assert "ok" in result.stdout


def test_ci_runner_failing_command():
    result = run_step("fail", f"{sys.executable} -c \"import sys; sys.exit(3)\"")
    assert result.passed is False
    assert result.returncode == 3


def test_ci_runner_stops_at_first_failure():
    steps = [
        {"name": "ok", "command": f"{sys.executable} -c \"print('ok')\""},
        {"name": "bad", "command": f"{sys.executable} -c \"import sys; sys.exit(1)\""},
        {"name": "never", "command": f"{sys.executable} -c \"print('never')\""},
    ]
    results = run_steps(steps)
    assert len(results) == 2
    assert results[1].name == "bad"


def test_ci_runner_timeout():
    result = run_step("slow", f"{sys.executable} -c \"import time; time.sleep(5)\"",
                      timeout_seconds=0.2)
    assert result.passed is False
    assert result.timed_out is True


# --- Report ---


def test_report_shows_blocked_release_and_no_rollout():
    gates = run_readiness_gates(
        clean_release(config={"diff_present": False})
    )
    text = render_report(gates, None)
    assert "BLOCKED" in text
    assert "[FAIL] config_review" in text
    assert "not attempted" in text


def test_report_shows_rollback_events():
    gates = run_readiness_gates(clean_release())
    metrics = healthy_metrics()
    metrics[1] = StageMetrics(
        error_rate=0.024, p95_latency_ms=640, success_rate=0.976
    )
    rollout = simulate_canary_rollout(
        "search-api", "v3.1.0", "v3.0.4", metrics
    )
    text = render_report(gates, rollout)
    assert "Rollback events:" in text
    assert "25%" in text
    assert "0% of traffic" in text
