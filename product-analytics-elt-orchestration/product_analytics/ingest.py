"""Ingest and staging: raw events in, clean partitioned tables out.

``load_raw`` validates every event against the instrumentation contract,
inserts the valid ones, and quarantines the rest with the reason. Staging
deduplicates on ``event_id`` (first occurrence wins, so a re-delivered
batch cannot double-count) and fans events out into per-day partition
tables, which is what makes later queries fast.
"""
from __future__ import annotations

import json
import sqlite3

from . import db as dbmod
from .contracts import validate_batch


def load_raw(conn: sqlite3.Connection, events: list[dict]) -> dict:
    """Validate and load a batch. Returns counts of loaded/quarantined rows."""
    good, violations = validate_batch(events)
    for event in good:
        conn.execute(
            "INSERT OR IGNORE INTO raw_events "
            "(event_id, user_id, event_type, event_ts, payload) VALUES (?, ?, ?, ?, ?)",
            (
                event["event_id"],
                event["user_id"],
                event["event_type"],
                event["event_ts"],
                json.dumps(event.get("payload") or {}),
            ),
        )
    bad_by_id: dict[str, list[str]] = {}
    for v in violations:
        bad_by_id.setdefault(str(v.event_id), []).append(v.reason)
    for event in events:
        reasons = bad_by_id.get(str(event.get("event_id")))
        if reasons:
            conn.execute(
                "INSERT INTO quarantine (event_id, reason, raw_json) VALUES (?, ?, ?)",
                (event.get("event_id"), "; ".join(reasons), json.dumps(event, default=str)),
            )
    conn.commit()
    return {"loaded": len(good), "quarantined": len(bad_by_id)}


def build_staging(conn: sqlite3.Connection) -> dict:
    """Dedupe raw events into staged_events and per-day partitions."""
    rows = conn.execute(
        "SELECT event_id, user_id, event_type, event_ts, payload FROM raw_events "
        "ORDER BY event_ts"
    ).fetchall()
    seen: set[str] = set()
    staged = 0
    partitions: set[str] = set()
    for row in rows:
        if row["event_id"] in seen:
            continue
        seen.add(row["event_id"])
        event_date = row["event_ts"][:10]
        conn.execute(
            "INSERT OR IGNORE INTO staged_events "
            "(event_id, user_id, event_type, event_ts, event_date, payload) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                row["event_id"],
                row["user_id"],
                row["event_type"],
                row["event_ts"],
                event_date,
                row["payload"],
            ),
        )
        table = dbmod.create_partition(conn, event_date)
        conn.execute(
            f"INSERT OR IGNORE INTO {table} "
            "(event_id, user_id, event_type, event_ts, payload) VALUES (?, ?, ?, ?, ?)",
            (row["event_id"], row["user_id"], row["event_type"], row["event_ts"], row["payload"]),
        )
        partitions.add(table)
        staged += 1
    dbmod.rebuild_partition_view(conn)
    conn.commit()
    return {"staged": staged, "partitions": len(partitions)}
