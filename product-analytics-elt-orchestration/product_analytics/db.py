"""SQLite schema for every layer of the pipeline.

Raw events land untouched in ``raw_events``. ``staged_events`` holds the
cleaned, deduplicated copy. Analytics tables are partitioned by event
date (one ``events_YYYYMMDD`` table per day plus a union view), so a
query for one day reads one partition instead of scanning everything.
``sessions`` and ``metric_results`` hold window-function outputs, and
``run_state`` / ``quality_results`` record what the orchestrator did.
"""
from __future__ import annotations

import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS raw_events (
    event_id   TEXT PRIMARY KEY,
    user_id    TEXT NOT NULL,
    event_type TEXT NOT NULL,
    event_ts   TEXT NOT NULL,
    payload    TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS quarantine (
    event_id TEXT,
    reason   TEXT NOT NULL,
    raw_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS staged_events (
    event_id   TEXT PRIMARY KEY,
    user_id    TEXT NOT NULL,
    event_type TEXT NOT NULL,
    event_ts   TEXT NOT NULL,
    event_date TEXT NOT NULL,
    payload    TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS sessions (
    session_id   TEXT PRIMARY KEY,
    user_id      TEXT NOT NULL,
    session_date TEXT NOT NULL,
    started_at   TEXT NOT NULL,
    ended_at     TEXT NOT NULL,
    event_count  INTEGER NOT NULL,
    duration_sec INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS metric_results (
    metric_name TEXT NOT NULL,
    metric_date TEXT NOT NULL,
    dimension   TEXT NOT NULL DEFAULT '',
    value       REAL NOT NULL,
    PRIMARY KEY (metric_name, metric_date, dimension)
);
CREATE TABLE IF NOT EXISTS run_state (
    task_name  TEXT PRIMARY KEY,
    status     TEXT NOT NULL,
    started_at TEXT NOT NULL,
    ended_at   TEXT,
    detail     TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS quality_results (
    check_name TEXT PRIMARY KEY,
    status     TEXT NOT NULL,
    detail     TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS model_test_results (
    model_name TEXT NOT NULL,
    test_name  TEXT NOT NULL,
    status     TEXT NOT NULL,
    detail     TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (model_name, test_name)
);
"""


def connect(path: str = ":memory:") -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def partition_table(date: str) -> str:
    """Partition table name for one event date (YYYY-MM-DD -> events_YYYYMMDD)."""
    return "events_" + date.replace("-", "")


def create_partition(conn: sqlite3.Connection, date: str) -> str:
    """Create (if needed) the partition table for one date, indexed for queries."""
    table = partition_table(date)
    conn.execute(
        f"""CREATE TABLE IF NOT EXISTS {table} (
            event_id   TEXT PRIMARY KEY,
            user_id    TEXT NOT NULL,
            event_type TEXT NOT NULL,
            event_ts   TEXT NOT NULL,
            payload    TEXT NOT NULL DEFAULT '{{}}'
        )"""
    )
    conn.execute(
        f"CREATE INDEX IF NOT EXISTS idx_{table}_user ON {table} (user_id, event_ts)"
    )
    conn.execute(
        f"CREATE INDEX IF NOT EXISTS idx_{table}_type ON {table} (event_type, event_ts)"
    )
    return table


def rebuild_partition_view(conn: sqlite3.Connection) -> None:
    """Rebuild the union view over every partition table that exists."""
    tables = [
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'events_%'"
        )
    ]
    if not tables:
        conn.execute("DROP VIEW IF EXISTS events_all")
        return
    union = " UNION ALL ".join(
        f"SELECT event_id, user_id, event_type, event_ts, payload FROM {t}"
        for t in sorted(tables)
    )
    conn.execute("DROP VIEW IF EXISTS events_all")
    conn.execute(f"CREATE VIEW events_all AS {union}")
