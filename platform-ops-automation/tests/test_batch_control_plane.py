"""Tests for ops/batch_control_plane.py (demo project)."""

from ops.batch_control_plane import (
    check_control_plane,
    control_plane_report,
    control_plane_summary,
    demo_state,
)


def _healthy_state():
    return {
        "queue_depth": 420_000,
        "queue_capacity": 40_000_000,
        "jobs_created_per_hour": 4_200_000,
        "jobs_fulfilled_per_hour": 4_200_000,
        "stalled_jobs": 12,
        "retry_exhausted_per_hour": 8,
        "components": [
            {"name": "loan-payments", "fulfill_p95_seconds": 180},
            {"name": "escrow", "fulfill_p95_seconds": 240},
        ],
    }


def _statuses(checks):
    return {c["name"]: c["status"] for c in checks}


def test_healthy_plane_is_growth_ready():
    summary = control_plane_summary(_healthy_state())
    assert summary["overall"] == "healthy"
    assert summary["checks_passed"] == summary["checks_total"]
    assert summary["headroom_x"] == 9.5
    # Headroom 9.5x is under the 10x growth target, so not growth-ready.
    assert summary["growth_ready"] is False


def test_larger_capacity_is_growth_ready():
    state = _healthy_state()
    state["queue_capacity"] = 50_000_000
    summary = control_plane_summary(state)
    assert summary["headroom_x"] == 11.9
    assert summary["growth_ready"] is True


def test_fulfillment_lagging_creation_fails():
    state = _healthy_state()
    state["jobs_fulfilled_per_hour"] = 3_900_000
    statuses = _statuses(check_control_plane(state))
    assert statuses["creation-vs-fulfillment"] == "fail"
    assert control_plane_summary(state)["overall"] == "degraded"


def test_stalled_jobs_over_limit_fail():
    state = _healthy_state()
    state["stalled_jobs"] = 250
    assert _statuses(check_control_plane(state))["stalled-jobs"] == "fail"


def test_slow_component_fulfill_p95_fails():
    state = _healthy_state()
    state["components"] = [
        {"name": "statements", "fulfill_p95_seconds": 420},
    ]
    statuses = _statuses(check_control_plane(state))
    assert statuses["fulfill-p95:statements"] == "fail"


def test_demo_state_is_degraded_and_not_growth_ready():
    summary = control_plane_summary(demo_state())
    assert summary["overall"] == "degraded"
    assert summary["growth_ready"] is False
    assert summary["headroom_x"] == 9.5
    report = control_plane_report(demo_state())
    assert "degraded" in report
    assert "fulfill-p95:statements" in report
