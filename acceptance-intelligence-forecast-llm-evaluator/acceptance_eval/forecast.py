"""Forecasters and error metrics (pure standard library).

Three forecasters, all fit on a plain list of floats:
- seasonal_naive: repeat the value from one period ago (period 7).
- holt: Holt linear exponential smoothing (level + trend).
- trend_seasonal_forecast: least-squares fit of trend + day-of-week
  dummies, solved with Gaussian elimination on the normal equations.
"""

import math


def _solve(matrix, rhs):
    """Gaussian elimination with partial pivoting; returns solution list."""
    n = len(rhs)
    aug = [row[:] + [rhs[i]] for i, row in enumerate(matrix)]
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(aug[r][col]))
        if abs(aug[piv][col]) < 1e-12:
            raise ValueError("singular system")
        aug[col], aug[piv] = aug[piv], aug[col]
        for r in range(col + 1, n):
            factor = aug[r][col] / aug[col][col]
            for c in range(col, n + 1):
                aug[r][c] -= factor * aug[col][c]
    out = [0.0] * n
    for i in range(n - 1, -1, -1):
        out[i] = (aug[i][n] - sum(aug[i][j] * out[j] for j in range(i + 1, n))) / aug[i][i]
    return out


def seasonal_naive(values, horizon, period=7):
    if len(values) < period:
        raise ValueError("need at least one full period of history")
    if horizon < 1:
        raise ValueError("horizon must be >= 1")
    return [values[-period + (i % period)] for i in range(horizon)]


def holt(values, horizon, alpha=0.3, beta=0.1):
    if len(values) < 2:
        raise ValueError("need at least 2 observations")
    if not (0 < alpha <= 1 and 0 <= beta <= 1):
        raise ValueError("alpha in (0, 1], beta in [0, 1]")
    level = values[0]
    trend = values[1] - values[0]
    for y in values[1:]:
        prev_level = level
        level = alpha * y + (1 - alpha) * (level + trend)
        trend = beta * (level - prev_level) + (1 - beta) * trend
    return [level + (i + 1) * trend for i in range(horizon)]


def trend_seasonal_forecast(values, horizon, period=7):
    """OLS: intercept + linear trend + (period-1) day-of-week dummies."""
    n = len(values)
    if n < 2 * period:
        raise ValueError("need at least two full periods of history")
    p = 2 + (period - 1)  # intercept, trend, dummies
    # Build normal equations X'X b = X'y.
    xtx = [[0.0] * p for _ in range(p)]
    xty = [0.0] * p
    for t, y in enumerate(values):
        row = [1.0, float(t)]
        dow = t % period
        row += [1.0 if dow == k else 0.0 for k in range(1, period)]
        for i in range(p):
            xty[i] += row[i] * y
            for j in range(p):
                xtx[i][j] += row[i] * row[j]
    beta = _solve(xtx, xty)
    preds = []
    for h in range(horizon):
        t = n + h
        row = [1.0, float(t)]
        dow = t % period
        row += [1.0 if dow == k else 0.0 for k in range(1, period)]
        preds.append(sum(b * x for b, x in zip(beta, row)))
    return preds


def mae(actual, predicted):
    if len(actual) != len(predicted) or not actual:
        raise ValueError("actual and predicted must be non-empty and equal length")
    return sum(abs(a - p) for a, p in zip(actual, predicted)) / len(actual)


def rmse(actual, predicted):
    if len(actual) != len(predicted) or not actual:
        raise ValueError("actual and predicted must be non-empty and equal length")
    return math.sqrt(sum((a - p) ** 2 for a, p in zip(actual, predicted)) / len(actual))


def mape(actual, predicted):
    if len(actual) != len(predicted) or not actual:
        raise ValueError("actual and predicted must be non-empty and equal length")
    if any(a == 0 for a in actual):
        raise ValueError("MAPE undefined when an actual value is 0")
    return sum(abs((a - p) / a) for a, p in zip(actual, predicted)) / len(actual) * 100.0
