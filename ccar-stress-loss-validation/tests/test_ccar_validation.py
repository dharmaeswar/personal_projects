"""Tests for the CCAR stress-loss validation project."""

import numpy as np
import pandas as pd
import pytest

from ccar_validation.backtest import backtest_all, calibration_by_decile, compute_metrics
from ccar_validation.data import MACRO_COLUMNS, generate_portfolio, train_test_split
from ccar_validation.models import fit_all
from ccar_validation.monitoring import drift_report, mean_drift_bps, psi
from ccar_validation.report import build_report
from ccar_validation.scenarios import compare_scenarios, scenario_frame, scenario_forecast


@pytest.fixture(scope="module")
def portfolio():
    return generate_portfolio()


@pytest.fixture(scope="module")
def split(portfolio):
    return train_test_split(portfolio)


@pytest.fixture(scope="module")
def fitted(split):
    train, test = split
    return fit_all(train), train, test


# --- Data generation determinism ---

def test_data_generation_deterministic():
    a = generate_portfolio()
    b = generate_portfolio()
    pd.testing.assert_frame_equal(a, b)


def test_data_generation_different_seed_differs():
    a = generate_portfolio(seed=42)
    b = generate_portfolio(seed=7)
    assert not a.equals(b)


def test_data_has_expected_columns_and_rows(portfolio):
    expected = {
        "loan_id", "segment", "origination_year", "ltv", "fico_score",
        "loan_balance", "gdp_growth", "unemployment_rate", "hpi_growth",
        "credit_spread", "observed_loss_rate", "defaulted",
    }
    assert set(portfolio.columns) == expected
    assert len(portfolio) == 5000


def test_loss_rates_in_valid_range(portfolio):
    assert portfolio["observed_loss_rate"].between(0.0, 1.0).all()
    assert set(portfolio["defaulted"].unique()) <= {0, 1}


def test_train_test_split_sizes_and_no_overlap(split):
    train, test = split
    assert len(train) == 3750
    assert len(test) == 1250
    assert set(train["loan_id"]).isdisjoint(set(test["loan_id"]))


# --- Models ---

def test_champion_beats_benchmark_on_mae(fitted):
    models, train, test = fitted
    actual = test["observed_loss_rate"].to_numpy()
    results = backtest_all(actual, {n: m.predict(test) for n, m in models.items()})
    assert results["champion"]["mae"] < results["benchmark"]["mae"]


def test_forecasts_in_valid_range(fitted):
    _, _, test = fitted
    models, _, _ = fitted
    for name, model in models.items():
        preds = model.predict(test)
        assert len(preds) == len(test)
        assert np.all((preds >= 0.0) & (preds <= 1.0)), name


def test_benchmark_predicts_constant(fitted):
    models, _, test = fitted
    preds = models["benchmark"].predict(test)
    assert np.all(preds == preds[0])


# --- Backtest metrics ---

def test_backtest_metrics_computed_correctly():
    actual = np.array([0.05, 0.10, 0.02])
    predicted = np.array([0.06, 0.08, 0.02])
    m = compute_metrics(actual, predicted, tolerance=0.01)
    assert m["bias"] == pytest.approx((0.01 - 0.02 + 0.0) / 3)
    assert m["mae"] == pytest.approx((0.01 + 0.02 + 0.0) / 3)
    assert m["rmse"] == pytest.approx(np.sqrt((0.0001 + 0.0004 + 0.0) / 3))
    assert m["hit_rate"] == pytest.approx(2 / 3)
    assert m["n"] == 3


def test_calibration_by_decile_shape(fitted):
    models, _, test = fitted
    actual = test["observed_loss_rate"].to_numpy()
    cal = calibration_by_decile(actual, models["champion"].predict(test))
    assert list(cal.columns) == ["decile", "n", "mean_actual", "mean_predicted", "calibration_gap"]
    assert cal["n"].sum() == len(test)
    assert cal["decile"].min() == 1 and cal["decile"].max() == 10


# --- Scenarios ---

def test_scenario_frame_shape():
    frame = scenario_frame("severely_adverse")
    assert len(frame) == 9
    assert list(frame.columns) == ["quarter"] + MACRO_COLUMNS


def test_scenario_stress_raises_forecast_losses(fitted):
    models, _, test = fitted
    comparison = compare_scenarios(models["champion"], test)
    assert (comparison["stress_uplift"] > 0).all()
    assert comparison["mean_forecast_loss_rate_severely_adverse"].mean() > \
        comparison["mean_forecast_loss_rate_baseline"].mean()


def test_unknown_scenario_raises():
    with pytest.raises(ValueError):
        scenario_frame("not_a_scenario")


# --- Monitoring ---

def test_psi_zero_for_identical_samples():
    x = np.random.default_rng(0).normal(0, 1, 1000)
    assert psi(x, x) == pytest.approx(0.0, abs=1e-9)


def test_psi_positive_for_shifted_samples():
    ref = np.random.default_rng(0).normal(0, 1, 5000)
    cur = np.random.default_rng(1).normal(2, 1, 5000)
    assert psi(ref, cur) > 0.25


def test_mean_drift_bps_computed_correctly():
    ref = np.array([0.05, 0.05, 0.05])
    cur = np.array([0.06, 0.06, 0.06])
    assert mean_drift_bps(ref, cur) == pytest.approx(100.0)


def test_drift_report_columns(portfolio):
    ref, cur = train_test_split(portfolio)
    report = drift_report(ref, cur, ["gdp_growth", "ltv"])
    assert list(report.columns) == ["column", "mean_drift_bps", "psi"]
    assert len(report) == 2
    assert (report["psi"] >= 0).all()


# --- Report ---

def test_report_contains_key_sections(fitted):
    models, train, test = fitted
    actual = test["observed_loss_rate"].to_numpy()
    backtest = backtest_all(actual, {n: m.predict(test) for n, m in models.items()})
    cal = calibration_by_decile(actual, models["champion"].predict(test))
    scen = compare_scenarios(models["champion"], test)
    current = generate_portfolio(seed=123)
    drift = drift_report(train, current, MACRO_COLUMNS + ["ltv", "fico_score"])
    report = build_report(backtest, cal, scen, drift, len(train), len(test))
    for section in [
        "CCAR STRESS-LOSS MODEL VALIDATION REPORT",
        "SCOPE",
        "OUTCOMES ANALYSIS",
        "CALIBRATION BY DECILE",
        "SCENARIO ANALYSIS",
        "ONGOING MONITORING",
        "VALIDATION CONCLUSION",
        "champion",
        "benchmark",
    ]:
        assert section in report
