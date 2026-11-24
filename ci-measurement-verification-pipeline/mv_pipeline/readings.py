"""Synthetic meter readings for the seeded M&V run.

Three commercial sites, 15-minute interval kW readings. The generator
is deterministic (seeded) so the pipeline output is reproducible.
Readings carry an ``arrived_at`` timestamp so late arrivals can be
tested, and a small number of deliberate defects: duplicates, negative
values and late rows.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

SITES = {
    "SITE-A": {"base_kw": 210.0, "amplitude": 25.0, "rate_usd_per_kwh": 5.0},
    "SITE-B": {"base_kw": 95.0, "amplitude": 12.0, "rate_usd_per_kwh": 5.0},
    "SITE-C": {"base_kw": 150.0, "amplitude": 18.0, "rate_usd_per_kwh": 5.0},
}

# Event: 2026-06-15, 14:00-16:00 UTC. Baseline pool: the 10 prior days.
EVENT_DATE = datetime(2026, 6, 15, tzinfo=timezone.utc)
EVENT_START_HOUR = 14
EVENT_HOURS = 2
INTERVAL_MINUTES = 15
BASELINE_DAYS = 10


def _interval_kw(site, day, interval_index, rng, curtailed=False):
    """Deterministic load shape: daily curve + noise, minus curtailment."""
    cfg = SITES[site]
    hour = interval_index * INTERVAL_MINUTES / 60.0
    # Afternoon peak shape, deterministic per site/day/interval.
    shape = cfg["amplitude"] * (0.5 + 0.5 * ((hour - 6) / 12.0))
    value = cfg["base_kw"] + shape + rng.uniform(-3.0, 3.0)
    if curtailed:
        value -= {"SITE-A": 41.2, "SITE-B": 18.6, "SITE-C": 0.0}[site]
    return round(max(value, 0.0), 2)


def generate_readings():
    """Return a list of raw reading dicts for the seeded run.

    Each reading: site_id, timestamp (UTC ISO), kw, arrived_at (UTC ISO).
    Includes 6 exact duplicates, 3 negative readings and 2 late
    arrivals, all deterministic.
    """
    rng = random.Random(20260615)
    readings = []
    days = [EVENT_DATE - timedelta(days=d) for d in range(BASELINE_DAYS, 0, -1)]
    days.append(EVENT_DATE)
    for day in days:
        is_event_day = day == EVENT_DATE
        for interval in range(24 * 60 // INTERVAL_MINUTES):
            ts = day + timedelta(minutes=interval * INTERVAL_MINUTES)
            for site in SITES:
                in_event = (is_event_day
                            and EVENT_START_HOUR
                            <= ts.hour < EVENT_START_HOUR + EVENT_HOURS)
                kw = _interval_kw(site, day, interval, rng,
                                  curtailed=in_event)
                arrived = ts + timedelta(minutes=30)
                readings.append({"site_id": site,
                                 "timestamp": ts.isoformat(),
                                 "kw": kw,
                                 "arrived_at": arrived.isoformat()})
    # Deliberate defects: 6 duplicates, 3 negative, 2 late arrivals.
    # Late arrivals replace the on-time copy of their own reading: the
    # day stays complete, but the row is staged flagged as late.
    for row in readings:
        if (row["site_id"] == "SITE-A"
                and row["timestamp"].startswith("2026-06-10T12:00")):
            row["arrived_at"] = "2026-06-12T12:00:00+00:00"
        if (row["site_id"] == "SITE-B"
                and row["timestamp"].startswith("2026-06-10T12:15")):
            row["arrived_at"] = "2026-06-12T12:15:00+00:00"
    readings.extend(readings[0:6])
    for i in (100, 500, 900):
        bad = dict(readings[i])
        bad["kw"] = -12.5
        readings.append(bad)
    rng.shuffle(readings)
    return readings
