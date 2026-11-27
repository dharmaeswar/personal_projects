"""SQLite storage for the integrated IT / IS / TP / DM risk datasets, with a
Python-vs-SQL reconciliation check (the same aggregation in both places
must agree exactly).
"""

from __future__ import annotations

import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS risks (
    risk_id TEXT PRIMARY KEY, name TEXT, category TEXT, source TEXT,
    likelihood INTEGER, impact INTEGER);
CREATE TABLE IF NOT EXISTS controls (
    control_id TEXT PRIMARY KEY, risk_id TEXT, name TEXT, design TEXT,
    sample_size INTEGER, exceptions INTEGER);
CREATE TABLE IF NOT EXISTS loss_events (
    event_id TEXT PRIMARY KEY, category TEXT, source TEXT,
    amount REAL, event_date TEXT);
CREATE TABLE IF NOT EXISTS kri_readings (
    kri_id TEXT, quarter INTEGER, value REAL,
    PRIMARY KEY (kri_id, quarter));
"""


def connect(path):
    conn = sqlite3.connect(str(path))
    conn.executescript(SCHEMA)
    return conn


def load_data(conn, data):
    conn.execute("DELETE FROM risks")
    conn.execute("DELETE FROM controls")
    conn.execute("DELETE FROM loss_events")
    conn.execute("DELETE FROM kri_readings")
    for r in data["risks"]:
        conn.execute("INSERT INTO risks VALUES (?,?,?,?,?,?)",
                     (r.risk_id, r.name, r.category, r.source, r.likelihood, r.impact))
    for c in data["controls"]:
        conn.execute("INSERT INTO controls VALUES (?,?,?,?,?,?)",
                     (c.control_id, c.risk_id, c.name, c.design, c.sample_size, c.exceptions))
    for e in data["loss_events"]:
        conn.execute("INSERT INTO loss_events VALUES (?,?,?,?,?)",
                     (e.event_id, e.category, e.source, e.amount, e.event_date))
    for k in data["kris"]:
        for q, v in enumerate(k.history, start=1):
            conn.execute("INSERT INTO kri_readings VALUES (?,?,?)", (k.kri_id, q, v))
    conn.commit()


def python_loss_totals(events):
    totals = {}
    for e in events:
        if e.amount < 0:
            raise ValueError(f"negative loss amount in {e.event_id}")
        totals[e.category] = round(totals.get(e.category, 0.0) + e.amount, 2)
    return totals


def sql_loss_totals(conn):
    rows = conn.execute(
        "SELECT category, ROUND(SUM(amount), 2) FROM loss_events GROUP BY category"
    ).fetchall()
    return {cat: total for cat, total in rows}


def reconcile(events, conn):
    """Python and SQL totals per loss category must match exactly."""
    py = python_loss_totals(events)
    sql = sql_loss_totals(conn)
    mismatches = {c: (py.get(c), sql.get(c)) for c in set(py) | set(sql)
                  if py.get(c) != sql.get(c)}
    return {"python": py, "sql": sql, "mismatches": mismatches, "ok": not mismatches}


def top_loss_event(conn):
    row = conn.execute(
        "SELECT event_id, category, source, amount FROM loss_events "
        "ORDER BY amount DESC LIMIT 1"
    ).fetchone()
    return {"event_id": row[0], "category": row[1], "source": row[2], "amount": row[3]}
