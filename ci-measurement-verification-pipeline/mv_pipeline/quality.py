"""Data quality checks over a staged batch.

Checks, each returning pass/fail plus the offending rows:
- gaps: a site-day missing any of its 96 fifteen-minute intervals
- late_arrivals: staged rows flagged late by the staging layer
- quarantined: rows the staging layer refused (negative kW, unknown
  site, bad timestamp), grouped by reason
- unknown_sites: quarantined rows whose reason is an unknown site id
"""

from __future__ import annotations

from datetime import datetime, timezone

from .readings import INTERVAL_MINUTES

INTERVALS_PER_DAY = 24 * 60 // INTERVAL_MINUTES


def run_quality_checks(staged, quarantine):
    """Return a dict of check results for one staged batch."""
    gaps = {}
    by_site_day = {}
    for row in staged:
        ts = datetime.fromisoformat(row["timestamp"])
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        by_site_day.setdefault((row["site_id"], ts.date()), set()).add(
            (ts.hour * 60 + ts.minute) // INTERVAL_MINUTES)
    for (site, day), seen in by_site_day.items():
        missing = INTERVALS_PER_DAY - len(seen)
        if missing:
            gaps.setdefault(site, []).append(
                {"date": str(day), "missing_intervals": missing})

    late = [r for r in staged if r.get("late_arrival")]
    by_reason = {}
    for row in quarantine:
        by_reason.setdefault(row.get("reason", "unknown"), 0)
        by_reason[row.get("reason", "unknown")] += 1

    return {
        "gaps": {"passed": not gaps, "sites_with_gaps": gaps},
        "late_arrivals": {"passed": not late, "count": len(late),
                          "examples": late[:3]},
        "quarantined": {"passed": not quarantine,
                        "count": len(quarantine), "by_reason": by_reason},
        "unknown_sites": {"passed": by_reason.get("unknown site_id", 0) == 0,
                          "count": by_reason.get("unknown site_id", 0)},
    }
