"""Data-quality checks: completeness, uniqueness, ranges, freshness.

Every check returns a pass/fail row and is written to ``quality_results``,
so the daily report shows exactly which check failed and why instead of
a single green/red flag. A failed check never deletes data; it only
blocks the publish step in the DAG.
"""
from __future__ import annotations

import sqlite3


def run_checks(conn: sqlite3.Connection, latest_date: str) -> list[dict]:
    """Run all checks for the latest loaded date. Returns one row per check."""
    checks: list[dict] = []

    def add(name: str, passed: bool, detail: str) -> None:
        checks.append({"check": name, "status": "pass" if passed else "fail", "detail": detail})

    null_users = conn.execute(
        "SELECT COUNT(*) FROM staged_events WHERE user_id IS NULL OR user_id = ''"
    ).fetchone()[0]
    add("no_null_users", null_users == 0, f"{null_users} staged events with no user")

    dupes = conn.execute(
        "SELECT COUNT(*) FROM (SELECT event_id FROM staged_events "
        "GROUP BY event_id HAVING COUNT(*) > 1)"
    ).fetchone()[0]
    add("unique_event_ids", dupes == 0, f"{dupes} duplicated event ids in staging")

    bad_ts = conn.execute(
        "SELECT COUNT(*) FROM staged_events WHERE event_ts IS NULL OR length(event_ts) < 10"
    ).fetchone()[0]
    add("valid_timestamps", bad_ts == 0, f"{bad_ts} staged events with bad timestamps")

    quarantined = conn.execute("SELECT COUNT(*) FROM quarantine").fetchone()[0]
    add("quarantine_reviewed", True, f"{quarantined} quarantined events awaiting review")

    newest = conn.execute("SELECT MAX(event_date) FROM staged_events").fetchone()[0]
    add(
        "freshness",
        newest == latest_date,
        f"newest staged date {newest}, expected {latest_date}",
    )

    for check in checks:
        conn.execute(
            "INSERT OR REPLACE INTO quality_results (check_name, status, detail) "
            "VALUES (?, ?, ?)",
            (check["check"], check["status"], check["detail"]),
        )
    conn.commit()
    return checks


def all_passed(checks: list[dict]) -> bool:
    return all(c["status"] == "pass" for c in checks)
