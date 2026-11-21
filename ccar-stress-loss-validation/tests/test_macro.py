"""Tests for the macro-forecasting validation module."""
import numpy as np
import pandas as pd
import pytest

from ccar_validation.data import generate_portfolio, train_test_split
from ccar_validation.macro import (
    build_macro_section,
    coefficient_stability,
    macro_sensitivity,
    regime_accuracy,
    scenario_reasonableness,
    sensitivity_is_monotone,
    validate_macro_model,
)
from ccar_validation.models import BenchmarkModel, ChampionModel, fit_all


@pytest.fixture(scope="module")
def portfolio():
    return generate_portfolio()


@pytest.fixture(scope="module")
def split(portfolio):
    return train_test_split(portfolio)


@pytest.fixture(scope="module")
def models(split):
    train, _ = split
    return fit_all(train)


def test_sensitivity_rises_with_unemployment(models, split):
    _, test = split
    table = macro_sensitivity(models["champion"], test)
    assert list(table["level"]) == [3.0, 5.0, 7.0, 9.0, 11.0]
    assert sensitivity_is_monotone(table, "increasing")
    assert table["mean_forecast_loss_rate"].iloc[-1] > table["mean_forecast_loss_rate"].iloc[0]


def test_sensitivity_falls_with_gdp_growth(models, split):
    _, test = split
    table = macro_sensitivity(models["champion"], test, variable="gdp_growth",
                              levels=(-2.0, 0.0, 2.0, 4.0))
    assert sensitivity_is_monotone(table, "decreasing")


def test_sensitivity_rejects_unknown_variable(models, split):
    _, test = split
    with pytest.raises(ValueError, match="Unknown macro variable"):
        macro_sensitivity(models["champion"], test, variable="oil_price")


def test_sensitivity_rejects_unknown_direction(models, split):
    _, test = split
    table = macro_sensitivity(models["champion"], test)
    with pytest.raises(ValueError, match="Unknown direction"):
        sensitivity_is_monotone(table, "sideways")


def test_flat_model_fails_sensitivity(models, split):
    _, test = split
    table = macro_sensitivity(models["benchmark"], test)
    assert not sensitivity_is_monotone(table, "increasing")


def test_regime_accuracy_splits_both_regimes(split, models):
    _, test = split
    forecast = models["champion"].predict(test)
    regimes = regime_accuracy(test["observed_loss_rate"].to_numpy(), forecast,
                              test["gdp_growth"].to_numpy())
    assert regimes["expansion"]["n"] > 0
    assert regimes["recession"]["n"] > 0
    assert regimes["expansion"]["mae"] >= 0
    assert regimes["recession"]["mae"] >= 0


def test_coefficient_stability_same_sign(split):
    train, _ = split
    stability = coefficient_stability(train)
    assert len(stability) == 3
    assert (stability["coefficient"] > 0).all()  # unemployment raises losses
    assert (stability["n"] > 500).all()


def test_coefficient_stability_rejects_unknown_feature(split):
    train, _ = split
    with pytest.raises(ValueError, match="Unknown feature"):
        coefficient_stability(train, variable="oil_price")


def test_scenario_uplift_positive_every_quarter(models, split):
    _, test = split
    scenarios = scenario_reasonableness(models["champion"], test)
    assert (scenarios["stress_uplift"] > 0).all()
    assert scenarios["stress_uplift"].max() > 0.01


def test_validate_macro_model_all_pass(split, models):
    train, test = split
    checks = validate_macro_model(models["champion"], train, test)
    assert [c["check"] for c in checks] == [
        "unemployment_sensitivity", "regime_accuracy",
        "coefficient_stability", "scenario_reasonableness",
    ]
    assert all(c["status"] == "pass" for c in checks)


def test_validate_macro_model_flags_flat_model(split, models):
    train, test = split
    checks = validate_macro_model(models["benchmark"], train, test)
    by_name = {c["check"]: c["status"] for c in checks}
    assert by_name["unemployment_sensitivity"] == "fail"
    assert by_name["scenario_reasonableness"] == "fail"


def test_build_macro_section_lists_all_checks(split, models):
    train, test = split
    section = build_macro_section(train, test, models["champion"])
    assert "MACRO-FORECASTING MODEL VALIDATION" in section
    for name in ("unemployment_sensitivity", "regime_accuracy",
                 "coefficient_stability", "scenario_reasonableness"):
        assert name in section
    assert "[PASS]" in section
