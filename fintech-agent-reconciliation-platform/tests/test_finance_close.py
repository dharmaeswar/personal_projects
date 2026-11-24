import pytest

from fintech_agents.finance_close import (
    CloseChecklist, CloseTask, arr_roll_forward, billings_vs_revenue,
    consolidate, forecast_variance)


def _checklist():
    return CloseChecklist([
        CloseTask("a", "Accrue", "controllership"),
        CloseTask("b", "Reconcile", "controllership", ["a"]),
        CloseTask("c", "Consolidate", "controllership", ["b"]),
        CloseTask("d", "Report", "fp&a", ["c"]),
    ])


def test_order_respects_dependencies():
    order = [t.task_id for t in _checklist().ordered()]
    assert order == ["a", "b", "c", "d"]


def test_complete_blocked_until_dependency_done():
    cl = _checklist()
    with pytest.raises(ValueError, match="blocked"):
        cl.complete("b")
    cl.complete("a")
    assert cl.complete("b").status == "done"
    assert cl.progress == 0.5


def test_cycle_detected():
    cl = CloseChecklist([
        CloseTask("a", "A", "controllership", ["b"]),
        CloseTask("b", "B", "controllership", ["a"]),
    ])
    with pytest.raises(ValueError, match="cycle"):
        cl.ordered()


def test_unknown_dependency_rejected():
    with pytest.raises(ValueError, match="unknown dependency"):
        CloseChecklist([CloseTask("a", "A", "tax", ["nope"])])


def test_consolidate_converts_each_entity():
    result = consolidate([
        {"entity": "US", "currency": "USD",
         "revenue_minor": 1_000_000, "fx_to_usd": 1.0},
        {"entity": "EU", "currency": "EUR",
         "revenue_minor": 1_000_000, "fx_to_usd": 1.08},
    ])
    assert result["total_usd_minor"] == 2_080_000
    assert result["lines"][1].revenue_usd_minor == 1_080_000


def test_arr_roll_forward_and_nrr():
    result = arr_roll_forward(10_000_000, new_minor=1_500_000,
                              expansion_minor=500_000,
                              churn_minor=400_000,
                              contraction_minor=100_000)
    assert result["ending_minor"] == 11_500_000
    assert result["net_revenue_retention_pct"] == 100.0


def test_billings_vs_revenue_is_deferred_change():
    result = billings_vs_revenue(9_000_000, 8_430_000)
    assert result["deferred_revenue_change_minor"] == 570_000


def test_forecast_variance_flagged_over_threshold():
    result = forecast_variance(1_125_000, 1_000_000)
    assert result["variance_pct"] == 12.5
    assert result["flagged"] is True


def test_forecast_variance_not_flagged_within_threshold():
    result = forecast_variance(10_200_000, 10_000_000)
    assert result["variance_pct"] == 2.0
    assert result["flagged"] is False
