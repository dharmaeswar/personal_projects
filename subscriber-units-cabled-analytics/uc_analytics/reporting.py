"""Daily / weekly / monthly Units Cabled reporting.

Aggregates daily actuals (and forecast snapshots) into the recurring
reporting the role owns: actuals, forecast, variance in units and
percent, and period-over-period trend. Pure standard library.
"""

from collections import defaultdict
from datetime import timedelta


def aggregate(rows, period="daily"):
    """Sum ``(date, region, community, units)`` rows into periods.

    Returns a list of dicts sorted by (period_start, region) with keys
    ``period_start``, ``region``, ``units``. ``period`` is one of
    ``daily``, ``weekly`` (Monday start) or ``monthly``.
    """
    totals = defaultdict(int)
    for day, region, _community, units in rows:
        if period == "daily":
            key = (day, region)
        elif period == "weekly":
            key = (day - timedelta(days=day.weekday()), region)
        elif period == "monthly":
            key = (day.replace(day=1), region)
        else:
            raise ValueError(f"unknown period: {period}")
        totals[key] += units
    return [{"period_start": k[0], "region": k[1], "units": v}
            for k, v in sorted(totals.items())]


def variance_report(actual_rows, forecast_rows, period="monthly"):
    """Join actuals to forecasts per period/region and add variance.

    ``forecast_rows`` are ``(snapshot_date, target_date, region, units)``
    snapshots; the latest snapshot at or before each period start is the
    forecast for that period. Returns rows with ``actual``, ``forecast``,
    ``variance`` (actual - forecast) and ``variance_pct``.
    """
    actuals = aggregate(actual_rows, period)
    last_actual = max(d for d, _r, _c, _u in actual_rows)
    out = []
    for row in actuals:
        start = row["period_start"]
        # Skip periods the actuals do not fully cover (e.g. the current
        # partial month): comparing them with a full-period forecast
        # would report a false large negative variance.
        if period == "weekly" and last_actual < start + timedelta(days=6):
            continue
        if period == "monthly":
            next_month = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
            if last_actual < next_month - timedelta(days=1):
                continue
        region = row["region"]
        snaps = [f for f in forecast_rows
                 if f[2] == region and f[0] <= start]
        if not snaps:
            continue
        latest = max(s[0] for s in snaps)
        if period == "daily":
            fcast = sum(f[3] for f in snaps
                        if f[0] == latest and f[1] == start)
        elif period == "weekly":
            fcast = sum(f[3] for f in snaps
                        if f[0] == latest and start <= f[1] < start + timedelta(days=7))
        else:
            fcast = sum(f[3] for f in snaps
                        if f[0] == latest and f[1].year == start.year
                        and f[1].month == start.month)
        var = row["units"] - fcast
        out.append({**row, "actual": row["units"], "forecast": fcast,
                    "variance": var,
                    "variance_pct": round(100.0 * var / fcast, 2) if fcast else None})
    return out


def trend(rows, period="weekly"):
    """Period-over-period change per region from aggregated rows."""
    agg = aggregate(rows, period)
    by_region = defaultdict(list)
    for row in agg:
        by_region[row["region"]].append(row)
    out = []
    for region, series in by_region.items():
        for prev, cur in zip(series, series[1:]):
            change = cur["units"] - prev["units"]
            out.append({"period_start": cur["period_start"], "region": region,
                        "units": cur["units"], "change": change,
                        "change_pct": round(100.0 * change / prev["units"], 2)
                        if prev["units"] else None})
    return out
