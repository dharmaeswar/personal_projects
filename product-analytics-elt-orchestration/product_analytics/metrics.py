"""Metric definitions as code: one YAML file is the source of truth.

Analysts and product teams read the same definition for every metric, so
"7-day retention" means the same number in every dashboard and ad-hoc
query. ``compute`` runs a definition against the warehouse and stores the
result in ``metric_results``; nothing else in the codebase hard-codes a
metric's SQL.
"""
from __future__ import annotations

import sqlite3

from . import transforms

# Definitions live in configs/metrics.yaml; this is the in-code mirror used
# when the YAML file is not on the path (tests). Each entry maps a metric
# name to a callable and a plain-language definition.
DEFINITIONS = {
    "dau": {
        "definition": "Distinct users with at least one event on the day.",
        "kind": "daily",
    },
    "sessions_per_user": {
        "definition": "Sessions started on the day divided by distinct users that day.",
        "kind": "daily",
    },
    "avg_session_seconds": {
        "definition": "Mean session duration in seconds for sessions starting that day.",
        "kind": "daily",
    },
    "retention_7d": {
        "definition": "Share of a cohort's users active again exactly 7 days after first use.",
        "kind": "cohort",
    },
    "funnel_view_save_click": {
        "definition": "Users who viewed, then saved, then clicked, in order, on the day.",
        "kind": "daily",
    },
}


def compute(conn: sqlite3.Connection, metric: str, date: str) -> dict:
    """Compute one metric for one date and store it. Returns the stored rows."""
    if metric == "dau":
        value = transforms.dau(conn, date)
        rows = [{"dimension": "", "value": float(value)}]
    elif metric == "sessions_per_user":
        sessions = conn.execute(
            "SELECT COUNT(*) FROM sessions WHERE session_date = ?", (date,)
        ).fetchone()[0]
        users = transforms.dau(conn, date)
        rows = [{"dimension": "", "value": (sessions / users if users else 0.0)}]
    elif metric == "avg_session_seconds":
        avg = conn.execute(
            "SELECT AVG(duration_sec) FROM sessions WHERE session_date = ?",
            (date,),
        ).fetchone()[0]
        rows = [{"dimension": "", "value": float(avg or 0.0)}]
    elif metric == "retention_7d":
        cohorts = transforms.retention(conn, cohort_days=7)
        rows = []
        for cohort in cohorts:
            if cohort["day_n"] != 7:
                continue
            size = conn.execute(
                "SELECT COUNT(*) FROM (SELECT user_id FROM staged_events "
                "WHERE event_date = ? GROUP BY user_id)",
                (cohort["cohort_date"],),
            ).fetchone()[0]
            rows.append(
                {
                    "dimension": cohort["cohort_date"],
                    "value": (cohort["users"] / size if size else 0.0),
                }
            )
    elif metric == "funnel_view_save_click":
        f = transforms.funnel(conn, date)
        rows = [
            {"dimension": "viewed", "value": float(f["viewers"])},
            {"dimension": "saved", "value": float(f["savers"])},
            {"dimension": "clicked", "value": float(f["clickers"])},
        ]
    else:
        raise ValueError(f"unknown metric: {metric}")
    for row in rows:
        conn.execute(
            "INSERT OR REPLACE INTO metric_results (metric_name, metric_date, dimension, value)"
            " VALUES (?, ?, ?, ?)",
            (metric, date, row["dimension"], row["value"]),
        )
    conn.commit()
    return {"metric": metric, "date": date, "rows": rows}


def compute_all(conn: sqlite3.Connection, date: str) -> list[dict]:
    """Compute every defined metric for one date."""
    return [compute(conn, name, date) for name in DEFINITIONS]
