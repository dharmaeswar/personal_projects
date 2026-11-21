"""Query optimization: partition pruning vs full scan, measured.

``compare`` runs the same one-day user-activity query twice — once
against the unpartitioned ``staged_events`` table and once against that
day's partition table — and returns both EXPLAIN QUERY PLAN outputs plus
the rows each plan touches. Partitioning plus the per-partition index
means the day query reads one small table instead of scanning the whole
history, which is the optimization the analytics tables are built for.
"""
from __future__ import annotations

import sqlite3

from .db import partition_table


def _plan(conn: sqlite3.Connection, sql: str) -> list[str]:
    return [" ".join(str(c) for c in row) for row in conn.execute(f"EXPLAIN QUERY PLAN {sql}")]


def compare(conn: sqlite3.Connection, date: str) -> dict:
    """Compare the one-day query on the full table vs the day partition."""
    table = partition_table(date)
    full_sql = (
        "SELECT COUNT(DISTINCT user_id) FROM staged_events "
        f"WHERE event_date = '{date}'"
    )
    part_sql = f"SELECT COUNT(DISTINCT user_id) FROM {table}"
    full_rows = conn.execute(full_sql).fetchone()[0]
    part_rows = conn.execute(part_sql).fetchone()[0]
    assert full_rows == part_rows, "partition and full-table counts must agree"
    return {
        "date": date,
        "distinct_users": full_rows,
        "full_table_plan": _plan(conn, full_sql),
        "partition_plan": _plan(conn, part_sql),
        "partition_scans_table": any(table in line for line in _plan(conn, part_sql)),
    }
