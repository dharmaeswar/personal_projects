"""Demand forecasting for table request rates.

Fits a least-squares model with a linear trend plus daily and weekly
seasonality to an hourly request-rate series, then forecasts ahead with a
prediction band built from the residual spread. Pure standard library.
"""

import math

# Feature vector for hour ``t`` (hours since the first observation).
# [intercept, trend in days, daily sin/cos, weekly sin/cos]
N_FEATURES = 6


def _features(hour, start_hour=0):
    t = hour - start_hour
    day = t / 24.0
    return [
        1.0,
        day,
        math.sin(2 * math.pi * (hour % 24) / 24.0),
        math.cos(2 * math.pi * (hour % 24) / 24.0),
        math.sin(2 * math.pi * ((hour // 24) % 7) / 7.0),
        math.cos(2 * math.pi * ((hour // 24) % 7) / 7.0),
    ]


def _solve(a, b):
    """Solve a small dense linear system by Gaussian elimination."""
    n = len(b)
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(m[r][col]))
        if abs(m[piv][col]) < 1e-12:
            raise ValueError("singular design matrix")
        m[col], m[piv] = m[piv], m[col]
        for r in range(col + 1, n):
            f = m[r][col] / m[col][col]
            for c in range(col, n + 1):
                m[r][c] -= f * m[col][c]
    x = [0.0] * n
    for r in range(n - 1, -1, -1):
        x[r] = (m[r][n] - sum(m[r][c] * x[c] for c in range(r + 1, n))) / m[r][r]
    return x


def fit(hourly_rates):
    """Fit the trend+seasonality model to ``hourly_rates`` (list of floats).

    Returns a dict with coefficients, residual standard deviation and the
    number of fitted points. Needs at least 48 points (2 days).
    """
    if len(hourly_rates) < 48:
        raise ValueError("need at least 48 hourly observations (2 days)")
    start = 0
    # Normal equations: (X^T X) beta = X^T y
    ata = [[0.0] * N_FEATURES for _ in range(N_FEATURES)]
    aty = [0.0] * N_FEATURES
    for i, y in enumerate(hourly_rates):
        x = _features(start + i, start)
        for r in range(N_FEATURES):
            aty[r] += x[r] * y
            for c in range(N_FEATURES):
                ata[r][c] += x[r] * x[c]
    beta = _solve(ata, aty)
    residuals = []
    for i, y in enumerate(hourly_rates):
        x = _features(start + i, start)
        pred = sum(b * v for b, v in zip(beta, x))
        residuals.append(y - pred)
    mean_sq = sum(r * r for r in residuals) / max(1, len(residuals) - N_FEATURES)
    return {
        "coefficients": beta,
        "residual_std": math.sqrt(mean_sq),
        "n_points": len(hourly_rates),
        "start_hour": start,
    }


def predict(model, hour):
    """Point forecast for a single future hour."""
    x = _features(hour, model["start_hour"])
    return sum(b * v for b, v in zip(model["coefficients"], x))


def forecast(model, hours_ahead, band=1.96):
    """Forecast ``hours_ahead`` hours past the fitted data.

    Returns a list of dicts: hour, point forecast, lower and upper band.
    Forecasts are floored at zero (request rates cannot be negative).
    """
    last = model["start_hour"] + model["n_points"]
    out = []
    for h in range(last, last + hours_ahead):
        point = max(0.0, predict(model, h))
        half = band * model["residual_std"]
        out.append(
            {
                "hour": h,
                "forecast": point,
                "lower": max(0.0, point - half),
                "upper": point + half,
            }
        )
    return out


def peak(forecast_rows):
    """Peak (max upper-band) forecast and the hour it occurs at."""
    row = max(forecast_rows, key=lambda r: r["upper"])
    return {"hour": row["hour"], "peak_upper": row["upper"], "peak_point": row["forecast"]}


def generate_synthetic(hours, base=1000.0, daily_growth=8.0, seed=42):
    """Deterministic synthetic hourly request rates with trend + seasonality.

    ``daily_growth`` is extra requests per second added each day. Used for
    demos and tests only.
    """
    import random

    rng = random.Random(seed)
    rates = []
    for h in range(hours):
        day = h / 24.0
        seasonal = 180.0 * math.sin(2 * math.pi * (h % 24) / 24.0 - 1.0)
        weekly = 120.0 * math.sin(2 * math.pi * ((h // 24) % 7) / 7.0)
        noise = rng.gauss(0, 25.0)
        rates.append(max(0.0, base + daily_growth * day + seasonal + weekly + noise))
    return rates
