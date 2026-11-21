"""Tests for prepayment model validation: decomposition, seasoning,
burnout, incentive monotonicity, backtest scoring, and the full battery."""

import pytest

from term_structure_mbs.prepay_validation import (
    backtest,
    burnout_factor,
    decompose_cpr,
    incentive_response_curve,
    seasoning_factor,
    validate_model,
)
from term_structure_mbs.prepayment import monthly_cpr


def test_decompose_splits_turnover_and_refi():
    result = decompose_cpr(0.10, turnover_cpr=0.02)
    assert result["refi_cpr"] == pytest.approx(0.08)
    assert result["refi_share"] == pytest.approx(0.8)


def test_decompose_rejects_turnover_above_total():
    with pytest.raises(ValueError):
        decompose_cpr(0.05, turnover_cpr=0.08)


def test_decompose_rejects_cpr_out_of_range():
    with pytest.raises(ValueError):
        decompose_cpr(1.0)


def test_seasoning_ramps_and_plateaus():
    assert seasoning_factor(1) == pytest.approx(1 / 30)
    assert seasoning_factor(15) == pytest.approx(0.5)
    assert seasoning_factor(30) == 1.0
    assert seasoning_factor(120) == 1.0


def test_seasoning_rejects_month_zero():
    with pytest.raises(ValueError):
        seasoning_factor(0)


def test_burnout_halves_every_twelve_months():
    assert burnout_factor(0) == 1.0
    assert burnout_factor(12) == pytest.approx(0.5)
    assert burnout_factor(24) == pytest.approx(0.25)


def test_backtest_scores_a_good_forecast():
    forecast = [0.06, 0.07, 0.08]
    actual = [0.061, 0.069, 0.081]
    result = backtest(forecast, actual)
    assert result["months"] == 3
    assert result["mae"] == pytest.approx(0.001)
    assert result["within_tolerance"] is True


def test_backtest_flags_a_bad_forecast():
    forecast = [0.06, 0.07, 0.08]
    actual = [0.12, 0.13, 0.14]
    result = backtest(forecast, actual)
    assert result["within_tolerance"] is False
    assert result["bias"] == pytest.approx(-0.06)


def test_backtest_rejects_mismatched_lengths():
    with pytest.raises(ValueError):
        backtest([0.06, 0.07], [0.06])


def test_backtest_rejects_empty_history():
    with pytest.raises(ValueError):
        backtest([], [])


def test_incentive_response_falls_as_rate_rises():
    curve = incentive_response_curve(0.07, [0.05, 0.06, 0.07, 0.08])
    cprs = [point["cpr"] for point in curve]
    assert cprs == sorted(cprs, reverse=True)
    assert cprs[0] > cprs[-1]


def test_validate_model_passes_with_good_backtest():
    forecast = [monthly_cpr(m, 0.07, 0.065) for m in range(31, 37)]
    actual = [c + 0.001 for c in forecast]
    result = validate_model(0.07, 0.065, forecast_cpr=forecast,
                            actual_cpr=actual)
    assert result["model_fit_for_use"] is True
    assert result["failed"] == 0


def test_validate_model_fails_with_bad_backtest():
    forecast = [0.06] * 6
    actual = [0.12] * 6
    result = validate_model(0.07, 0.065, forecast_cpr=forecast,
                            actual_cpr=actual)
    assert result["model_fit_for_use"] is False
    assert result["failed"] == 1
    failed = [f for f in result["findings"] if not f["passed"]]
    assert "backtest" in failed[0]["check"]
