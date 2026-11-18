import math
import pytest

from acceptance_eval import (
    seasonal_naive, holt, trend_seasonal_forecast, mae, rmse, mape,
)


def test_seasonal_naive_repeats_last_week():
    vals = [0.80, 0.81, 0.82, 0.83, 0.84, 0.85, 0.86, 0.87]
    assert seasonal_naive(vals, 3) == [0.81, 0.82, 0.83]
    assert seasonal_naive(vals, 7) == vals[1:8]


def test_seasonal_naive_needs_full_period():
    with pytest.raises(ValueError):
        seasonal_naive([0.8, 0.9], 2)


def test_holt_length_and_trend_direction():
    vals = [0.80 + 0.01 * i for i in range(30)]
    preds = holt(vals, 5)
    assert len(preds) == 5
    assert preds[-1] > preds[0]  # upward trend continues
    assert all(p > vals[-1] for p in preds)


def test_holt_rejects_bad_params():
    with pytest.raises(ValueError):
        holt([0.8, 0.9], 2, alpha=0.0)
    with pytest.raises(ValueError):
        holt([0.8], 2)


def test_trend_seasonal_recovers_linear_series():
    vals = [1.0 + 0.02 * t for t in range(60)]
    preds = trend_seasonal_forecast(vals, 3)
    assert len(preds) == 3
    for pred, t in zip(preds, [60, 61, 62]):
        assert abs(pred - (1.0 + 0.02 * t)) < 0.01


def test_trend_seasonal_needs_two_periods():
    with pytest.raises(ValueError):
        trend_seasonal_forecast([0.8] * 10, 2)


def test_metrics_zero_on_perfect_forecast():
    actual = [0.85, 0.86, 0.87]
    assert mae(actual, actual) == 0.0
    assert rmse(actual, actual) == 0.0
    assert mape(actual, actual) == 0.0


def test_metrics_known_values():
    assert mae([1.0, 2.0], [1.5, 1.5]) == 0.5
    assert rmse([1.0, 2.0], [1.0, 2.0]) == 0.0
    assert abs(mape([100.0, 200.0], [110.0, 180.0]) - 10.0) < 1e-9


def test_metrics_reject_mismatched_lengths():
    with pytest.raises(ValueError):
        mae([1.0], [1.0, 2.0])
    with pytest.raises(ValueError):
        mape([0.0, 1.0], [0.0, 1.0])
