"""Anomaly detection over the normalized security events.

Detectors are simple, explainable rules over the synthetic data:
impossible travel, dormant privileged accounts, overdue findings, and
failed-login bursts. Each returns the offending rows with the reason.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta

from .data import AS_OF

IMPOSSIBLE_TRAVEL_MINUTES = 60
BRUTE_FORCE_WINDOW_MINUTES = 10
BRUTE_FORCE_MIN_FAILURES = 5
DORMANT_DAYS = 90


def find_impossible_travel(conn: sqlite3.Connection) -> list[dict]:
    """Same identity, successful logins from two countries within an hour."""
    rows = conn.execute(
        "SELECT event_id, identity_id, ts, country, city FROM events "
        "WHERE event_type = 'login' AND success = 1 "
        "ORDER BY identity_id, ts"
    ).fetchall()
    by_identity: dict[str, list] = {}
    for r in rows:
        by_identity.setdefault(r["identity_id"], []).append(r)
    anomalies = []
    for identity_id, events in by_identity.items():
        for i, first in enumerate(events):
            first_ts = datetime.fromisoformat(first["ts"])
            for second in events[i + 1:]:
                second_ts = datetime.fromisoformat(second["ts"])
                gap = (second_ts - first_ts).total_seconds() / 60
                if gap > IMPOSSIBLE_TRAVEL_MINUTES:
                    break
                if second["country"] != first["country"]:
                    anomalies.append(
                        {
                            "identity_id": identity_id,
                            "first_event_id": first["event_id"],
                            "second_event_id": second["event_id"],
                            "first_country": first["country"],
                            "first_city": first["city"],
                            "second_country": second["country"],
                            "second_city": second["city"],
                            "gap_minutes": round(gap, 1),
                        }
                    )
    return anomalies


def find_dormant_privileged(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT identity_id, name, email, last_login_days_ago FROM identities "
        "WHERE privileged = 1 AND last_login_days_ago > ?",
        (DORMANT_DAYS,),
    ).fetchall()
    return [dict(r) for r in rows]


def find_overdue_findings(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT finding_id, asset_id, severity, title, due_date FROM findings "
        "WHERE status = 'open' AND due_date < ? ORDER BY due_date",
        (AS_OF.isoformat(),),
    ).fetchall()
    return [dict(r) for r in rows]


def find_brute_force(conn: sqlite3.Connection) -> list[dict]:
    """5+ failed logins for one identity inside a 10-minute window."""
    rows = conn.execute(
        "SELECT event_id, identity_id, ts, ip FROM events "
        "WHERE event_type = 'login' AND success = 0 ORDER BY identity_id, ts"
    ).fetchall()
    by_identity: dict[str, list] = {}
    for r in rows:
        by_identity.setdefault(r["identity_id"], []).append(r)
    bursts = []
    for identity_id, events in by_identity.items():
        # Largest number of failures inside any 10-minute window.
        start = 0
        best: list = []
        for end in range(len(events)):
            while (
                datetime.fromisoformat(events[end]["ts"])
                - datetime.fromisoformat(events[start]["ts"])
            ) > timedelta(minutes=BRUTE_FORCE_WINDOW_MINUTES):
                start += 1
            window = events[start : end + 1]
            if len(window) > len(best):
                best = window
        if len(best) >= BRUTE_FORCE_MIN_FAILURES:
            bursts.append(
                {
                    "identity_id": identity_id,
                    "failed_logins": len(best),
                    "first_ts": best[0]["ts"],
                    "last_ts": best[-1]["ts"],
                    "ip": best[-1]["ip"],
                    "event_ids": [e["event_id"] for e in best],
                }
            )
    return bursts


def find_all_anomalies(conn: sqlite3.Connection) -> dict[str, list[dict]]:
    return {
        "impossible_travel": find_impossible_travel(conn),
        "dormant_privileged": find_dormant_privileged(conn),
        "overdue_findings": find_overdue_findings(conn),
        "brute_force": find_brute_force(conn),
    }
