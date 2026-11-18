"""Control-effectiveness KPIs, computed from the normalized model
with real SQL where the data lives.

KPIs are descriptive measures of the synthetic data (coverage, stale
access, remediation speed, overdue work). They are not claims about any
real security posture.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime

from .data import AS_OF

DORMANT_DAYS = 90


def _pct(numerator: int, denominator: int) -> float:
    return round(100.0 * numerator / denominator, 1) if denominator else 0.0


def compute_kpis(conn: sqlite3.Connection) -> dict:
    cur = conn.cursor()

    total_identities = cur.execute(
        "SELECT COUNT(*) FROM identities"
    ).fetchone()[0]
    privileged = cur.execute(
        "SELECT COUNT(*) FROM identities WHERE privileged = 1"
    ).fetchone()[0]
    privileged_mfa = cur.execute(
        "SELECT COUNT(*) FROM identities WHERE privileged = 1 AND mfa_enabled = 1"
    ).fetchone()[0]
    mfa_coverage_priv = _pct(privileged_mfa, privileged)
    mfa_coverage_all = _pct(
        cur.execute(
            "SELECT COUNT(*) FROM identities WHERE mfa_enabled = 1"
        ).fetchone()[0],
        total_identities,
    )

    dormant_priv = cur.execute(
        "SELECT COUNT(*) FROM identities "
        "WHERE privileged = 1 AND last_login_days_ago > ?",
        (DORMANT_DAYS,),
    ).fetchone()[0]
    stale_access_pct = _pct(dormant_priv, privileged)

    successful_logins = cur.execute(
        "SELECT COUNT(*) FROM events WHERE event_type = 'login' AND success = 1"
    ).fetchone()[0]
    mfa_logins = cur.execute(
        "SELECT COUNT(*) FROM events WHERE event_type = 'login' "
        "AND success = 1 AND mfa_used = 1"
    ).fetchone()[0]
    mfa_login_usage = _pct(mfa_logins, successful_logins)

    remediated = cur.execute(
        "SELECT discovered_date, remediated_date FROM findings "
        "WHERE status = 'remediated' AND remediated_date IS NOT NULL"
    ).fetchall()
    mttr_days = None
    if remediated:
        days = [
            (
                datetime.fromisoformat(r["remediated_date"])
                - datetime.fromisoformat(r["discovered_date"])
            ).days
            for r in remediated
        ]
        mttr_days = round(sum(days) / len(days), 1)

    total_findings = cur.execute("SELECT COUNT(*) FROM findings").fetchone()[0]
    overdue = cur.execute(
        "SELECT COUNT(*) FROM findings "
        "WHERE status = 'open' AND due_date < ?",
        (AS_OF.isoformat(),),
    ).fetchone()[0]
    open_findings = cur.execute(
        "SELECT COUNT(*) FROM findings WHERE status = 'open'"
    ).fetchone()[0]
    overdue_pct = _pct(overdue, total_findings)

    by_severity = {
        row["severity"]: row["n"]
        for row in cur.execute(
            "SELECT severity, COUNT(*) AS n FROM findings GROUP BY severity"
        ).fetchall()
    }
    open_by_severity = {
        row["severity"]: row["n"]
        for row in cur.execute(
            "SELECT severity, COUNT(*) AS n FROM findings "
            "WHERE status = 'open' GROUP BY severity"
        ).fetchall()
    }

    total_events = cur.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    late_events = cur.execute(
        "SELECT COUNT(*) FROM events WHERE late_arriving = 1"
    ).fetchone()[0]
    quarantined = cur.execute("SELECT COUNT(*) FROM quarantine").fetchone()[0]
    # Staged rows = normalized events + normalized findings + quarantined.
    staged_rows = total_events + quarantined + total_findings

    return {
        "total_identities": total_identities,
        "privileged_identities": privileged,
        "privileged_with_mfa": privileged_mfa,
        "mfa_coverage_privileged_pct": mfa_coverage_priv,
        "mfa_coverage_all_pct": mfa_coverage_all,
        "dormant_privileged": dormant_priv,
        "stale_access_pct": stale_access_pct,
        "successful_logins": successful_logins,
        "successful_logins_with_mfa": mfa_logins,
        "mfa_login_usage_pct": mfa_login_usage,
        "remediated_findings": len(remediated),
        "mttr_days": mttr_days,
        "total_findings": total_findings,
        "open_findings": open_findings,
        "overdue_findings": overdue,
        "overdue_findings_pct": overdue_pct,
        "findings_by_severity": by_severity,
        "open_findings_by_severity": open_by_severity,
        "total_events": total_events,
        "late_events": late_events,
        "quarantined_rows": quarantined,
        "staged_rows": staged_rows,
    }
