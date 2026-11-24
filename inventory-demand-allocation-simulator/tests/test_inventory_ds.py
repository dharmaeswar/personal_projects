import numpy as np
import pandas as pd
import pytest

from inventory_ds import ab_test, data_gen, forecast
from inventory_ds.allocate import allocation_metrics, greedy_allocate, lp_allocate
from inventory_ds.simulate import simulate, simulation_summary


@pytest.fixture(scope="module")
def history():
    return data_gen.generate_demand_history()


@pytest.fixture(scope="module")
def inventory():
    return data_gen.generate_inventory()


@pytest.fixture(scope="module")
def fc(history):
    return forecast.forecast_all(history)


def test_data_gen_shapes():
    h = data_gen.generate_demand_history()
    assert len(h) == 104 * 4 * 3
    assert set(h.columns) == {"week", "style", "region", "demand"}
    assert (h["demand"] >= 0).all()
    inv = data_gen.generate_inventory()
    assert len(inv) == 12
    assert (inv["on_hand"] >= 0).all()
    # Deterministic: same seed gives the same data.
    pd.testing.assert_frame_equal(h, data_gen.generate_demand_history())


def test_holt_winters_forecast(history):
    series = history[(history["style"] == "style_A") & (history["region"] == "east")]["demand"]
    preds, mape = forecast.holt_winters_forecast(series.astype(float))
    assert len(preds) == 4
    assert np.all(np.isfinite(preds))
    assert 0 <= mape < 0.5


def test_ridge_forecast(history):
    series = history[(history["style"] == "style_B") & (history["region"] == "west")]["demand"]
    preds, mape, coefs = forecast.ridge_forecast(series.astype(float))
    assert len(preds) == 4
    assert np.all(preds >= 0)
    assert 0 <= mape < 0.5
    assert "lag_1" in coefs and "sin52" in coefs


def test_forecast_all(history):
    fc = forecast.forecast_all(history)
    assert len(fc) == 12
    assert set(fc["best_model"]) <= {"ridge", "holt_winters"}
    assert (fc["forecast_week1"] > 0).all()


def test_greedy_allocate_respects_inventory(fc, inventory):
    alloc = greedy_allocate(fc, inventory)
    used = alloc[alloc["fc"] != "UNMET"].groupby(["style", "fc"])["units"].sum()
    for (style, f), units in used.items():
        on_hand = inventory[(inventory["style"] == style) & (inventory["fc"] == f)]["on_hand"].iloc[0]
        assert units <= on_hand + 1e-6
    m = allocation_metrics(alloc, fc)
    assert 0 < m["fill_rate"] <= 1.0


def test_lp_beats_or_matches_greedy_on_cost(fc, inventory):
    g = allocation_metrics(greedy_allocate(fc, inventory), fc)
    lp = allocation_metrics(lp_allocate(fc, inventory), fc)
    assert lp["total_cost"] <= g["total_cost"] + 1e-6
    assert lp["fill_rate"] >= g["fill_rate"] - 1e-6


def test_lp_never_exceeds_demand(fc, inventory):
    alloc = lp_allocate(fc, inventory)
    served = alloc.groupby(["style", "region"])["units"].sum()
    for (style, region), units in served.items():
        demand = fc[(fc["style"] == style) & (fc["region"] == region)]["forecast_week1"].iloc[0]
        assert units <= demand + 1e-6


def test_simulate_summary(history, fc, inventory):
    results = simulate(fc, inventory, history, n_reps=50, seed=1)
    assert set(results["policy"]) == {"greedy", "lp"}
    assert len(results) == 100
    summary = simulation_summary(results)
    assert len(summary) == 2
    assert (summary["mean_fill_rate"] > 0.8).all()
    assert (summary["p5_fill_rate"] <= summary["mean_fill_rate"]).all()
    assert (summary["mean_fill_rate"] <= summary["p95_fill_rate"]).all()


def test_ab_test_treatment_wins():
    exp = data_gen.generate_ab_experiment()
    result = ab_test.analyse_ab(exp)
    assert result["treatment_fill_rate"] > result["control_fill_rate"]
    assert result["fill_rate_p_value"] < 0.05
    assert result["recommendation"].startswith("GO")
    assert result["cost_diff_per_order"] < 0


def test_ab_test_needs_both_groups():
    exp = data_gen.generate_ab_experiment()
    with pytest.raises(ValueError):
        ab_test.analyse_ab(exp[exp["group"] == "control"])
