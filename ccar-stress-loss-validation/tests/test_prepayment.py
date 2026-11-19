"""Tests for the agency prepayment model validation module."""

import numpy as np
import pandas as pd
import pytest

from ccar_validation.prepayment import (
    build_prepayment_section,
    calibration_by_incentive,
    check_monotonicity,
    cpr_from_psa,
    generate_prepayment_pool,
    predict_cpr,
    rate_incentive,
    seasoning_factor,
    sensitivity_table,
    validate_prepayment_model,
)


@pytest.fixture(scope="module")
def pool():
    return generate_prepayment_pool()


def test_pool_generation_deterministic():
    pd.testing.assert_frame_equal(generate_prepayment_pool(), generate_prepayment_pool())


def test_pool_shape_and_columns(pool):
    assert len(pool) == 3000
    expected = {
        "loan_id", "loan_age_months", "coupon_rate", "current_rate",
        "balance", "fico_score", "ltv", "burnout_months", "observed_cpr",
    }
    assert set(pool.columns) == expected
    assert pool["observed_cpr"].between(0.0, 0.60).all()


def test_psa_benchmark_values():
    # 100 PSA fully seasoned (30 months) = 6% CPR; half-seasoned = 3%.
    assert cpr_from_psa(100, 30) == pytest.approx(0.06)
    assert cpr_from_psa(100, 15) == pytest.approx(0.03)
    assert cpr_from_psa(200, 30) == pytest.approx(0.12)
    assert cpr_from_psa(100, 0) == pytest.approx(0.0)
    with pytest.raises(ValueError):
        cpr_from_psa(-50, 30)


def test_seasoning_factor_ramps():
    ages = np.array([0, 15, 30, 60])
    np.testing.assert_allclose(seasoning_factor(ages), [0.0, 0.5, 1.0, 1.0])


def test_rate_incentive_sign():
    assert rate_incentive(np.array([7.0]), np.array([6.0]))[0] == pytest.approx(1.0)
    assert rate_incentive(np.array([5.0]), np.array([6.0]))[0] == pytest.approx(-1.0)


def test_predicted_cpr_in_valid_range(pool):
    preds = predict_cpr(pool)
    assert len(preds) == len(pool)
    assert np.all((preds >= 0.0) & (preds <= 0.60))


def test_new_loans_prepay_slowly(pool):
    young = pool[pool["loan_age_months"] <= 3]
    old = pool[pool["loan_age_months"] >= 30]
    assert predict_cpr(young).mean() < predict_cpr(old).mean()


def test_high_incentive_prepays_faster(pool):
    incentive = rate_incentive(pool["coupon_rate"].to_numpy(), pool["current_rate"].to_numpy())
    high = pool[incentive > 1.5]
    low = pool[incentive < -1.0]
    assert predict_cpr(high).mean() > predict_cpr(low).mean()


def test_model_beats_mean_benchmark(pool):
    actual = pool["observed_cpr"].to_numpy()
    predicted = predict_cpr(pool)
    model = validate_prepayment_model(actual, predicted)
    benchmark = validate_prepayment_model(actual, np.full(len(pool), actual.mean()))
    assert model["mae"] < benchmark["mae"]
    assert model["hit_rate"] > 0.5


def test_sensitivity_table_monotone(pool):
    table = sensitivity_table(pool)
    assert list(table["rate_shock_bps"]) == [-200, -100, 0, 100, 200]
    assert check_monotonicity(table)
    assert table["mean_forecast_cpr"].iloc[0] > table["mean_forecast_cpr"].iloc[-1]


def test_sensitivity_table_shape(pool):
    table = sensitivity_table(pool, rate_shocks_bps=(-100, 0, 100))
    assert list(table.columns) == ["rate_shock_bps", "mean_forecast_cpr", "median_forecast_cpr"]
    assert len(table) == 3


def test_calibration_by_incentive_shape(pool):
    actual = pool["observed_cpr"].to_numpy()
    predicted = predict_cpr(pool)
    incentive = rate_incentive(pool["coupon_rate"].to_numpy(), pool["current_rate"].to_numpy())
    cal = calibration_by_incentive(actual, predicted, incentive)
    assert list(cal.columns) == ["bucket", "n", "mean_actual", "mean_predicted", "calibration_gap"]
    assert cal["n"].sum() == len(pool)
    assert (cal["calibration_gap"].abs() < 0.05).all()


def test_report_section_contains_key_content(pool):
    section = build_prepayment_section(pool)
    for text in [
        "AGENCY PREPAYMENT MODEL VALIDATION",
        "Outcomes:",
        "Rate sensitivity",
        "Monotonicity check",
        "Calibration by rate-incentive bucket",
    ]:
        assert text in section
