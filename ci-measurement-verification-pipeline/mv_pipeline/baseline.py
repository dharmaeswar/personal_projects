"""Intermediate layer: the baseline model.

For each site and each 15-minute interval of the event window, the
baseline is the mean of that same interval across the 10 most recent
eligible non-event days. A day contributes to an interval only if its
reading for that interval is staged — days with gaps are excluded for
the intervals they are missing, never filled in silently.
"""

from __future__ import annotations

from datetime import datetime, timezone

from .readings import BASELINE_DAYS, EVENT_DATE, INTERVAL_MINUTES


def _interval_index(ts):
    return (ts.hour * 60 + ts.minute) // INTERVAL_MINUTES


def build_baseline(staged, event_date=EVENT_DATE,
                   baseline_days=BASELINE_DAYS):
    """Return {(site_id, interval_index): baseline_kw}.

    ``staged`` is the staging output: dicts with site_id, timestamp
    (ISO, UTC) and kw.
    """
    pool_start = event_date.replace(hour=0, minute=0, second=0,
                                    microsecond=0)
    by_key = {}
    for row in staged:
        ts = datetime.fromisoformat(row["timestamp"])
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        days_before = (pool_start - ts).days
        if not (1 <= days_before <= baseline_days):
            continue
        key = (row["site_id"], _interval_index(ts))
        by_key.setdefault(key, []).append(row["kw"])
    return {key: round(sum(values) / len(values), 2)
            for key, values in by_key.items()}
