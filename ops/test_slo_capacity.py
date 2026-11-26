"""Tests for ops.slo_capacity — SLI/SLO, burn-rate alerts, capacity planning."""

import pytest

from ops.slo_capacity import (
    BURN_ALERT_RULES,
    SLO,
    CapacityPlan,
    burn_rate,
    error_budget_remaining,
    evaluate_burn_windows,
)


@pytest.fixture()
def slo():
    return SLO(name="checkout availability", target=0.999, window_days=30)


def test_error_budget_fraction(slo):
    assert slo.error_budget_fraction == pytest.approx(0.001)
    assert slo.allowed_bad_events(1_000_000) == pytest.approx(1000.0)


def test_error_budget_remaining_healthy(slo):
    # 100 bad out of 1,000,000 events: 10% of the 1,000-event budget spent.
    result = error_budget_remaining(slo, 999_900, 1_000_000)
    assert result["availability"] == pytest.approx(0.9999)
    assert result["budget_consumed"] == pytest.approx(0.1)
    assert result["status"] == "healthy"


def test_error_budget_remaining_watch_then_exhausted(slo):
    watch = error_budget_remaining(slo, 999_400, 1_000_000)
    assert watch["budget_consumed"] == pytest.approx(0.6)
    assert watch["status"] == "watch"
    exhausted = error_budget_remaining(slo, 998_500, 1_000_000)
    assert exhausted["availability"] < slo.target
    assert exhausted["status"] == "exhausted"


def test_slo_rejects_bad_target():
    with pytest.raises(ValueError):
        SLO(name="bad", target=1.0)


def test_burn_rate_on_budget(slo):
    # Exactly 0.1% bad events over the window: burn rate 1.0.
    assert burn_rate(slo, 999_000, 1_000_000) == pytest.approx(1.0)


def test_burn_rate_fast_burn(slo):
    # 1.44% bad events in an hour: 14.4x budget, pages.
    assert burn_rate(slo, 98_560, 100_000) == pytest.approx(14.4)


def test_evaluate_burn_windows_pages_on_fast_burn(slo):
    windows = {
        "1h": (98_560, 100_000),  # burn 14.4 -> page
        "6h": (999_400, 1_000_000),  # burn 0.6 -> quiet
        "3d": (999_900, 1_000_000),  # burn 0.1 -> quiet
    }
    alerts = evaluate_burn_windows(slo, windows)
    assert len(alerts) == 1
    assert alerts[0]["window"] == "1h"
    assert alerts[0]["severity"] == "page"
    assert alerts[0]["action"] == "page on-call"


def test_evaluate_burn_windows_slow_burn_opens_ticket(slo):
    windows = {
        "1h": (999_900, 1_000_000),
        "6h": (999_400, 1_000_000),
        "3d": (998_800, 1_000_000),  # burn 1.2 -> ticket
    }
    alerts = evaluate_burn_windows(slo, windows)
    assert len(alerts) == 1
    assert alerts[0]["window"] == "3d"
    assert alerts[0]["severity"] == "ticket"


def test_evaluate_burn_windows_quiet_when_on_budget(slo):
    windows = {label: (999_900, 1_000_000) for label, _, _ in BURN_ALERT_RULES}
    assert evaluate_burn_windows(slo, windows) == []


def test_capacity_plan_growth_forecast():
    # Usage grows 10 units/day from 400 toward capacity 1000.
    plan = CapacityPlan(resource="cpu", capacity=1000.0,
                        history=[400.0, 410.0, 420.0, 430.0, 440.0])
    assert plan.daily_growth == pytest.approx(10.0)
    assert plan.current_utilization == pytest.approx(0.44)
    assert plan.days_until_full() == pytest.approx(56.0)
    assert plan.days_until_headroom_target() == pytest.approx(26.0)
    forecast = plan.forecast(days_ahead=30)
    assert forecast["projected_usage_in_days"] == pytest.approx(740.0)
    assert "plan scale-out" in forecast["recommendation"]


def test_capacity_plan_flat_usage_needs_no_action():
    plan = CapacityPlan(resource="disk", capacity=500.0,
                        history=[200.0, 200.0, 200.0])
    assert plan.daily_growth == 0.0
    assert plan.days_until_full() is None
    assert "no action" in plan.forecast(days_ahead=30)["recommendation"]


def test_capacity_plan_over_capacity_projects_scale_out_now():
    plan = CapacityPlan(resource="connections", capacity=100.0,
                        history=[80.0, 90.0, 95.0])
    forecast = plan.forecast(days_ahead=30)
    assert forecast["projected_utilization"] > 1.0
    assert "scale out now" in forecast["recommendation"]


def test_capacity_plan_rejects_bad_inputs():
    with pytest.raises(ValueError):
        CapacityPlan(resource="x", capacity=0.0)
    with pytest.raises(ValueError):
        CapacityPlan(resource="x", capacity=100.0, history=[-5.0])
    plan = CapacityPlan(resource="x", capacity=100.0, history=[10.0])
    with pytest.raises(ValueError):
        plan.forecast(days_ahead=0)
