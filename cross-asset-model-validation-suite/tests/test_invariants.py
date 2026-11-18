"""Tests for the invariant framework: registry, runner, pass and fail paths."""

from pathlib import Path

import pytest

from model_validation_suite.invariants import REGISTRY, run_suite
from model_validation_suite.models.rates import DiscountCurve
from model_validation_suite.scenarios import expand_scenarios, load_config

CONFIG = Path(__file__).resolve().parent.parent / "configs" / "scenarios.yaml"


def test_registry_covers_all_three_asset_classes():
    assert set(REGISTRY.asset_classes()) == {"rates", "fx", "equity"}
    for asset in ("rates", "fx", "equity"):
        assert len(REGISTRY.for_asset(asset)) >= 3


def test_full_suite_passes_on_shipped_config():
    scenarios = expand_scenarios(load_config(CONFIG))
    results = run_suite(scenarios)
    assert results, "runner produced no checks"
    failures = [r for r in results if not r.passed]
    assert failures == [], f"unexpected breaches: {failures[:3]}"


def test_runner_flags_broken_curve():
    # Negative zero rates make discount factors exceed 1: the unit-interval
    # invariant must fail while well-formed checks still run.
    bad_curve = DiscountCurve([1, 2, 5], [-0.01, -0.01, -0.01])
    scenario = {
        "id": "rates/broken",
        "asset_class": "rates",
        "context": {
            "curve": bad_curve,
            "par_yields": [0.02, 0.022, 0.025],
            "par_maturities": [1, 2, 3],
            "vasicek": {"a": 0.3, "theta": 0.03, "sigma": 0.01, "r0": 0.025},
            "tolerances": {"parity": 1e-9, "short_end": 1e-3},
        },
    }
    results = run_suite([scenario])
    by_name = {r.invariant: r for r in results}
    assert by_name["discount_factors_in_unit_interval"].passed is False
    assert by_name["discount_factors_in_unit_interval"].status == "FAIL"
    assert by_name["par_bond_repricing"].passed is True


def test_crashing_invariant_is_recorded_as_failure():
    from model_validation_suite.invariants.framework import InvariantRegistry

    registry = InvariantRegistry()

    @registry.register("equity", "boom")
    def _boom(ctx):
        raise RuntimeError("model exploded")

    scenario = {"id": "equity/x", "asset_class": "equity", "context": {}}
    results = run_suite([scenario], registry=registry)
    assert len(results) == 1
    assert results[0].passed is False
    assert "model exploded" in results[0].detail


@pytest.mark.parametrize("asset", ["rates", "fx", "equity"])
def test_each_asset_class_produces_results(asset):
    scenarios = [s for s in expand_scenarios(load_config(CONFIG))
                 if s["asset_class"] == asset]
    assert scenarios
    results = run_suite(scenarios)
    assert {r.asset_class for r in results} == {asset}
