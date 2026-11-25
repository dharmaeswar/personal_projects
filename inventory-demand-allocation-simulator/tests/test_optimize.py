import pandas as pd
import pytest

from inventory_ds import data_gen, forecast
from inventory_ds.allocate import allocation_metrics, lp_allocate
from inventory_ds.optimize import (
    LEAD_TIME_DAYS, lp_relaxation_allocate, milp_allocate, scenario_analysis,
    sensitivity_analysis,
)


@pytest.fixture(scope="module")
def fc():
    return forecast.forecast_all(data_gen.generate_demand_history())


@pytest.fixture(scope="module")
def inventory():
    return data_gen.generate_inventory()


def test_milp_units_are_integer(fc, inventory):
    alloc = milp_allocate(fc, inventory)
    shipped = alloc[alloc["fc"] != "UNMET"]
    assert (shipped["units"] == shipped["units"].round()).all()
    assert (alloc["units"] > 0).all()


def test_milp_respects_inventory_and_demand(fc, inventory):
    alloc = milp_allocate(fc, inventory)
    used = alloc[alloc["fc"] != "UNMET"].groupby(["style", "fc"])["units"].sum()
    for (style, f), units in used.items():
        on_hand = inventory[(inventory["style"] == style) & (inventory["fc"] == f)]["on_hand"].iloc[0]
        assert units <= on_hand + 1e-6
    served = alloc.groupby(["style", "region"])["units"].sum()
    for (style, region), units in served.items():
        demand = fc[(fc["style"] == style) & (fc["region"] == region)]["forecast_week1"].iloc[0]
        assert units <= demand + 1e-6


def test_milp_matches_lp_relaxation_cost(fc, inventory):
    # Integer units are whole demand units here, so MILP and LP agree closely.
    milp_m = allocation_metrics(milp_allocate(fc, inventory), fc)
    lp_m = allocation_metrics(lp_relaxation_allocate(fc, inventory), fc)
    base_lp = allocation_metrics(lp_allocate(fc, inventory), fc)
    assert abs(milp_m["total_cost"] - lp_m["total_cost"]) < 100.0
    assert abs(lp_m["total_cost"] - base_lp["total_cost"]) < 1.0
    assert milp_m["fill_rate"] == pytest.approx(lp_m["fill_rate"], abs=0.01)


def test_lead_time_table_complete():
    assert len(LEAD_TIME_DAYS) == 9
    assert min(LEAD_TIME_DAYS.values()) == 1
    assert max(LEAD_TIME_DAYS.values()) == 5


def test_scenario_analysis_rows(fc, inventory):
    out = scenario_analysis(fc, inventory)
    assert len(out) == 6
    assert set(out["scenario"]) == {"base", "ship_cost_+20pct", "ship_cost_-20pct",
                                    "demand_+10pct", "stockout_penalty_x2", "lead_time_penalty"}
    assert (out["fill_rate"] > 0).all() and (out["fill_rate"] <= 1.0).all()
    base = out[out["scenario"] == "base"].iloc[0]
    surge = out[out["scenario"] == "demand_+10pct"].iloc[0]
    assert surge["unmet_units"] >= base["unmet_units"]


def test_sensitivity_analysis_monotone_cost(fc, inventory):
    out = sensitivity_analysis(fc, inventory)
    assert len(out) == 6
    cost_rows = out[out["parameter"] == "ship_cost_multiplier"].sort_values("value")
    # Higher shipping-cost multiplier cannot lower the scored shipping cost trend.
    assert cost_rows["total_cost"].iloc[-1] >= cost_rows["total_cost"].iloc[0]
