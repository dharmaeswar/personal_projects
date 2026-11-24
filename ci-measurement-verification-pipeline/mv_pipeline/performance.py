"""Intermediate layer: event performance and payments.

For each site, over the event window:
- baseline_kw: mean baseline across the window's intervals
- actual_kw: mean metered kW across the window's intervals
- curtailed_kw: baseline minus actual, floored at 0 (a site that used
  *more* than baseline during an event curtailed nothing — it is not
  credited, and the over-use is flagged, not hidden)
- curtailed_kwh: curtailed_kw summed per interval x 0.25 hours
- payment_usd: curtailed_kwh x the site's program rate

Every figure is derived from per-interval rows, so any payment can be
traced back to the baseline and meter readings that produced it.
"""

from __future__ import annotations

from datetime import datetime, timezone

from .readings import (EVENT_DATE, EVENT_HOURS, EVENT_START_HOUR,
                       INTERVAL_MINUTES, SITES)


def _interval_index(ts):
    return (ts.hour * 60 + ts.minute) // INTERVAL_MINUTES


def event_performance(baseline, staged, event_date=EVENT_DATE,
                      start_hour=EVENT_START_HOUR,
                      hours=EVENT_HOURS):
    """Return {site_id: performance dict} for the event window."""
    window = {(start_hour * 60 + m) // INTERVAL_MINUTES
              for m in range(0, hours * 60, INTERVAL_MINUTES)}
    actual = {}
    for row in staged:
        ts = datetime.fromisoformat(row["timestamp"])
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        if ts.date() != event_date.date():
            continue
        idx = _interval_index(ts)
        if idx not in window:
            continue
        actual.setdefault(row["site_id"], {})[idx] = row["kw"]

    results = {}
    for site in SITES:
        base_values, actual_values, curtailed = [], [], []
        for idx in sorted(window):
            base = baseline.get((site, idx))
            act = actual.get(site, {}).get(idx)
            if base is None or act is None:
                continue
            base_values.append(base)
            actual_values.append(act)
            curtailed.append(max(base - act, 0.0))
        if not base_values:
            results[site] = {"site_id": site, "intervals": 0,
                             "baseline_kw": 0.0, "actual_kw": 0.0,
                             "curtailed_kw": 0.0, "curtailed_kwh": 0.0,
                             "payment_usd": 0.0, "over_use": False}
            continue
        avg_base = sum(base_values) / len(base_values)
        avg_actual = sum(actual_values) / len(actual_values)
        curtailed_kw = sum(curtailed) / len(curtailed)
        curtailed_kwh = round(sum(curtailed) * INTERVAL_MINUTES / 60.0, 2)
        rate = SITES[site]["rate_usd_per_kwh"]
        results[site] = {
            "site_id": site, "intervals": len(base_values),
            "baseline_kw": round(avg_base, 2),
            "actual_kw": round(avg_actual, 2),
            "curtailed_kw": round(curtailed_kw, 2),
            "curtailed_kwh": curtailed_kwh,
            "payment_usd": round(curtailed_kwh * rate, 2),
            "over_use": avg_actual > avg_base,
        }
    return results


def payment_for(performance):
    """Total payment across sites, in USD."""
    return round(sum(p["payment_usd"] for p in performance.values()), 2)
