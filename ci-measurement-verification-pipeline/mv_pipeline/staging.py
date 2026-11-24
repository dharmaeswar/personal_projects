"""Staging layer: clean raw meter readings into stg_readings.

Rules, applied in order:
1. Drop rows with an unknown site id (quarantined, never loaded).
2. Drop rows with missing or negative kW (quarantined with a reason).
3. Normalise timestamps to UTC (offsets and naive values are treated
   as UTC and stored in ISO form).
4. Dedupe on (site_id, timestamp): the first row wins; later copies
   are counted, not loaded.
5. Flag late arrivals: a reading that arrived more than 24 hours after
   its timestamp is loaded but flagged, so downstream models can see it.

Loads are idempotent: staging into a table that already holds a batch
loads 0 new rows, because the (site_id, timestamp) key already exists.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .readings import SITES

LATE_ARRIVAL_LIMIT = timedelta(hours=24)


def _parse_ts(value):
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def stage_readings(raw_readings, existing_keys=None):
    """Stage raw readings. Returns (staged, quarantine, stats).

    ``existing_keys`` is a set of (site_id, timestamp) already staged —
    rows matching it are skipped as already-loaded, which is what makes
    a re-run of the same batch a no-op.
    """
    existing = set(existing_keys or ())
    staged, quarantine = [], []
    stats = {"raw": len(raw_readings), "staged": 0, "duplicates": 0,
             "quarantined": 0, "late_arrivals": 0, "already_loaded": 0}
    seen = set(existing)
    for row in raw_readings:
        site = row.get("site_id")
        if site not in SITES:
            quarantine.append({**row, "reason": "unknown site_id"})
            stats["quarantined"] += 1
            continue
        kw = row.get("kw")
        if kw is None or kw < 0:
            quarantine.append({**row, "reason": "invalid kw"})
            stats["quarantined"] += 1
            continue
        try:
            ts = _parse_ts(row["timestamp"])
            arrived = _parse_ts(row["arrived_at"])
        except (ValueError, TypeError, KeyError):
            quarantine.append({**row, "reason": "bad timestamp"})
            stats["quarantined"] += 1
            continue
        key = (site, ts.isoformat())
        if key in seen:
            if key in existing:
                stats["already_loaded"] += 1
            else:
                stats["duplicates"] += 1
            continue
        seen.add(key)
        late = arrived - ts > LATE_ARRIVAL_LIMIT
        if late:
            stats["late_arrivals"] += 1
        staged.append({"site_id": site, "timestamp": ts.isoformat(),
                       "kw": float(kw), "late_arrival": late})
        stats["staged"] += 1
    return staged, quarantine, stats
