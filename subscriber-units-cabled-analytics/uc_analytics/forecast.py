"""Rolling 120-day Units Cabled forecast and backtest.

The forecast is deliberately simple and explainable, the way an
operational analyst would build it in Excel/Python: a trailing
moving-average daily rate, a linear trend fitted to recent daily
totals, and a day-of-week seasonal factor. The backtest replays the
same method on history so the reported accuracy (MAPE) is measured,
not asserted.
"""

from datetime import timedelta
from statistics import mean


def daily_region_totals(actual_rows, region):
    """Sorted list of (date, total units) for one region."""
    totals = {}
    for day, r, _c, units in actual_rows:
        if r == region:
            totals[day] = totals.get(day, 0) + units
    return sorted(totals.items())


def _trend_per_day(series):
    """Least-squares slope (units/day) of a [(date, units)] series."""
    n = len(series)
    if n < 2:
        return 0.0
    xs = [(d - series[0][0]).days for d, _ in series]
    ys = [u for _, u in series]
    xbar, ybar = mean(xs), mean(ys)
    denom = sum((x - xbar) ** 2 for x in xs)
    if denom == 0:
        return 0.0
    return sum((x - xbar) * (y - ybar) for x, y in zip(xs, ys)) / denom


def forecast_120(series, horizon=120, window=28):
    """Forecast the next ``horizon`` days from a daily totals series.

    Uses the last ``window`` days: mean daily level, linear trend, and a
    day-of-week factor (each weekday's mean / overall mean). Returns a
    list of (date, forecast_units).
    """
    if not series:
        return []
    recent = series[-window:]
    level = mean(u for _, u in recent)
    slope = _trend_per_day(recent)
    dow_factor = {}
    for dow in range(7):
        vals = [u for d, u in recent if d.weekday() == dow]
        dow_factor[dow] = (mean(vals) / level) if vals and level else 1.0
    last_date = series[-1][0]
    out = []
    for h in range(1, horizon + 1):
        day = last_date + timedelta(days=h)
        value = (level + slope * h) * dow_factor[day.weekday()]
        out.append((day, max(0, int(round(value)))))
    return out


def backtest(series, horizon=28, window=28, step=7):
    """Replay the forecast on history; return MAPE per origin and mean.

    Origins step through history every ``step`` days; each origin
    forecasts ``horizon`` days ahead and is scored against actuals.
    """
    if len(series) < window + horizon:
        return {"origins": [], "mean_mape_pct": None}
    actual = dict(series)
    results = []
    for origin in range(window, len(series) - horizon + 1, step):
        train = series[:origin]
        preds = dict(forecast_120(train, horizon=horizon, window=window))
        errors = [abs(preds[d] - actual[d]) / actual[d]
                  for d, _ in series[origin:origin + horizon] if actual[d]]
        if errors:
            results.append({"origin": series[origin - 1][0].isoformat(),
                            "mape_pct": round(100.0 * mean(errors), 2)})
    mean_mape = round(mean(r["mape_pct"] for r in results), 2) if results else None
    return {"origins": results, "mean_mape_pct": mean_mape}
