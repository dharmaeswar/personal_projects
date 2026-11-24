import math

import pytest

from capplanner import forecast


def test_fit_needs_48_points():
    with pytest.raises(ValueError):
        forecast.fit([100.0] * 47)


def test_fit_recovers_trend_and_seasonality():
    rates = forecast.generate_synthetic(24 * 14, base=1000.0, daily_growth=8.0)
    model = forecast.fit(rates)
    assert model["n_points"] == 24 * 14
    # Trend coefficient is per day: ~8 rps/day.
    assert 4.0 < model["coefficients"][1] < 12.0
    # Residual spread stays small relative to the signal.
    assert model["residual_std"] < 60.0


def test_forecast_length_and_shape():
    rates = forecast.generate_synthetic(24 * 14)
    model = forecast.fit(rates)
    rows = forecast.forecast(model, 24)
    assert len(rows) == 24
    for r in rows:
        assert r["lower"] <= r["forecast"] <= r["upper"]
        assert r["forecast"] >= 0


def test_forecast_grows_with_trend():
    rates = forecast.generate_synthetic(24 * 14, base=1000.0, daily_growth=50.0)
    model = forecast.fit(rates)
    rows = forecast.forecast(model, 48)
    assert rows[-1]["forecast"] > rows[0]["forecast"]


def test_peak_is_max_upper_band():
    rates = forecast.generate_synthetic(24 * 14)
    model = forecast.fit(rates)
    rows = forecast.forecast(model, 24)
    pk = forecast.peak(rows)
    assert pk["peak_upper"] == max(r["upper"] for r in rows)
    assert pk["hour"] == max(rows, key=lambda r: r["upper"])["hour"]


def test_generate_synthetic_is_deterministic():
    a = forecast.generate_synthetic(100, seed=7)
    b = forecast.generate_synthetic(100, seed=7)
    assert a == b
    assert all(v >= 0 for v in a)
    assert len(a) == 100


def test_predict_matches_forecast_first_hour():
    rates = forecast.generate_synthetic(24 * 14)
    model = forecast.fit(rates)
    rows = forecast.forecast(model, 1)
    assert rows[0]["forecast"] == pytest.approx(
        max(0.0, forecast.predict(model, model["start_hour"] + model["n_points"])))
