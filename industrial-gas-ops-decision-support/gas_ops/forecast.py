"""Demand forecasting: trend + weekly-seasonal moving average.

The forecaster is deliberately simple and explainable: a least-squares
linear trend fitted on the recent window, a 7-day moving average for the
level, and a weekly seasonal factor. The backtest trains on the first 60
days and tests on the last 30, and compares against a naive last-value
baseline so the forecast has to earn its keep.
"""

import math
import statistics


def _trend(series):
    """Least-squares slope and intercept of series against day index."""
    n = len(series)
    xs = list(range(n))
    x_mean = statistics.fmean(xs)
    y_mean = statistics.fmean(series)
    num = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, series))
    den = sum((x - x_mean) ** 2 for x in xs)
    slope = num / den if den else 0.0
    return slope, y_mean - slope * x_mean


def _weekly_factor(series, horizon_day):
    """Mean demand on the same weekday / overall mean, from the series."""
    weekday = [v for i, v in enumerate(series) if i % 7 == horizon_day % 7]
    overall = statistics.fmean(series)
    if not weekday or overall == 0:
        return 1.0
    return statistics.fmean(weekday) / overall


def forecast(series, days=7, window=30):
    """Forecast the next `days` values from the last `window` observations.

    Returns a list of rounded daily forecasts. No look-ahead: only the
    window is used.
    """
    recent = series[-window:]
    slope, intercept = _trend(recent)
    level = statistics.fmean(recent[-7:])
    start = len(series)
    out = []
    for h in range(days):
        day = start + h
        trend_value = intercept + slope * (len(recent) - 1 + h + 1)
        seasonal = _weekly_factor(recent, day)
        value = max(0.0, 0.5 * trend_value + 0.5 * level * seasonal)
        out.append(round(value, 2))
    return out


def _mape(actual, predicted):
    errs = [abs(a - p) / a for a, p in zip(actual, predicted) if a > 0]
    return statistics.fmean(errs) * 100.0 if errs else 0.0


def backtest(series, train_days=60, horizon=30):
    """Time-based backtest: train on the first 60 days, test the last 30.

    Returns (forecast MAPE %, naive last-value MAPE %). The naive baseline
    repeats the last training value for the whole horizon.
    """
    train, test = series[:train_days], series[train_days:train_days + horizon]
    preds = forecast(train, days=horizon, window=train_days)
    naive = [train[-1]] * len(test)
    return round(_mape(test, preds), 2), round(_mape(test, naive), 2)
