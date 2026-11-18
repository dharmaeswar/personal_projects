"""Data-quality checks + freshness / SLA check.

Every check returns {"name", "passed", "details"} so the run report
can list pass/fail per check instead of a single opaque boolean.
SLA: usage data must be loaded within SLA_DAYS of the usage date.
The check compares the run date against the newest usage date in
the warehouse; a lag over SLA_DAYS flags the dataset as stale.
"""
from __future__ import annotations

import sqlite3
from datetime import date

SLA_DAYS = 2


def check_referential_integrity(conn: sqlite3.Connection) -> dict:
    orphan = conn.execute(
        """SELECT COUNT(*) AS n FROM fact_service_usage f
           LEFT JOIN dim_date d ON d.date_key = f.date_key
           LEFT JOIN dim_service s ON s.service_key = f.service_key
           LEFT JOIN dim_account a ON a.account_key = f.account_key
           LEFT JOIN dim_region r ON r.region_key = f.region_key
           WHERE d.date_key IS NULL OR s.service_key IS NULL
              OR a.account_key IS NULL OR r.region_key IS NULL"""
    ).fetchone()["n"]
    return {
        "name": "referential_integrity_fact_to_dims",
        "passed": orphan == 0,
        "details": f"{orphan} fact row(s) with a missing dimension",
    }


def check_null_or_negative_usage(conn: sqlite3.Connection) -> dict:
    bad = conn.execute(
        """SELECT COUNT(*) AS n FROM fact_service_usage
           WHERE usage_qty IS NULL OR cost_usd IS NULL
              OR usage_qty < 0 OR cost_usd < 0
              OR event_id IS NULL OR event_id = ''"""
    ).fetchone()["n"]
    return {
        "name": "no_null_or_negative_usage",
        "passed": bad == 0,
        "details": f"{bad} fact row(s) null or negative",
    }


def check_duplicates(conn: sqlite3.Connection) -> dict:
    dupes = conn.execute(
        """SELECT COUNT(*) AS n FROM (
               SELECT event_id FROM fact_service_usage
               GROUP BY event_id HAVING COUNT(*) > 1)"""
    ).fetchone()["n"]
    return {
        "name": "no_duplicate_events",
        "passed": dupes == 0,
        "details": f"{dupes} duplicated event_id(s)",
    }


def check_scd2_no_overlaps(conn: sqlite3.Connection) -> dict:
    """At most one current version per service, and no overlapping ranges."""
    multi_current = conn.execute(
        """SELECT COUNT(*) AS n FROM (
               SELECT service_code FROM dim_service
               WHERE is_current = 1 GROUP BY service_code HAVING COUNT(*) > 1)"""
    ).fetchone()["n"]
    overlap = conn.execute(
        """SELECT COUNT(*) AS n FROM dim_service a JOIN dim_service b
           ON a.service_code = b.service_code AND a.service_key < b.service_key
           WHERE a.effective_to IS NULL OR a.effective_to >= b.effective_from"""
    ).fetchone()["n"]
    passed = multi_current == 0 and overlap == 0
    return {
        "name": "scd2_single_current_no_overlap",
        "passed": passed,
        "details": f"{multi_current} service(s) with >1 current row; {overlap} overlapping version pair(s)",
    }


def check_freshness_sla(conn: sqlite3.Connection, run_date: str | None = None,
                        sla_days: int = SLA_DAYS) -> dict:
    """Flag the dataset if the newest usage date lags the run date by > SLA."""
    run = date.fromisoformat(run_date) if run_date else date.today()
    row = conn.execute("SELECT MAX(date_value) AS mx FROM dim_date").fetchone()
    newest = row["mx"] if row else None
    if newest is None:
        return {"name": "freshness_sla", "passed": False,
                "details": "warehouse has no dates loaded", "lag_days": None, "sla_days": sla_days}
    lag = (run - date.fromisoformat(newest)).days
    return {
        "name": "freshness_sla",
        "passed": lag <= sla_days,
        "details": f"newest usage date {newest}; run date {run.isoformat()}; lag {lag} day(s); SLA {sla_days} day(s)",
        "lag_days": lag,
        "sla_days": sla_days,
        "newest_usage_date": newest,
    }


def run_all_checks(conn: sqlite3.Connection, run_date: str | None = None) -> list[dict]:
    return [
        check_referential_integrity(conn),
        check_null_or_negative_usage(conn),
        check_duplicates(conn),
        check_scd2_no_overlaps(conn),
        check_freshness_sla(conn, run_date=run_date),
    ]
