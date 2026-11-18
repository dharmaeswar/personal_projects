"""Release history store (SQLite).

Two tables: ``releases`` records each release's gate outcome, and
``rollout_events`` records what happened during its rollout
(stage promotions, rollbacks). The store is queryable by service
and version, so a team can answer "what happened the last time we
shipped this service?" without digging through CI logs.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS releases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    service TEXT NOT NULL,
    version TEXT NOT NULL,
    gates_passed INTEGER NOT NULL,
    gates_total INTEGER NOT NULL,
    blocking_reasons TEXT NOT NULL DEFAULT '',
    recorded_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(service, version)
);

CREATE TABLE IF NOT EXISTS rollout_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    service TEXT NOT NULL,
    version TEXT NOT NULL,
    stage_percent INTEGER NOT NULL,
    event TEXT NOT NULL,
    recorded_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def connect(db_path: str | Path) -> sqlite3.Connection:
    """Open (and create, if needed) the history database."""
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def record_release(
    conn: sqlite3.Connection,
    service: str,
    version: str,
    gates_passed: int,
    gates_total: int,
    blocking_reasons: list[str] | None = None,
) -> None:
    """Insert or replace the gate outcome for one release."""
    conn.execute(
        """
        INSERT INTO releases
            (service, version, gates_passed, gates_total, blocking_reasons)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(service, version) DO UPDATE SET
            gates_passed = excluded.gates_passed,
            gates_total = excluded.gates_total,
            blocking_reasons = excluded.blocking_reasons,
            recorded_at = datetime('now')
        """,
        (
            service,
            version,
            gates_passed,
            gates_total,
            "; ".join(blocking_reasons or []),
        ),
    )
    conn.commit()


def record_rollout_event(
    conn: sqlite3.Connection,
    service: str,
    version: str,
    stage_percent: int,
    event: str,
) -> None:
    conn.execute(
        """
        INSERT INTO rollout_events (service, version, stage_percent, event)
        VALUES (?, ?, ?, ?)
        """,
        (service, version, stage_percent, event),
    )
    conn.commit()


def releases_for_service(conn: sqlite3.Connection, service: str) -> list[dict]:
    """All releases for a service, newest first."""
    rows = conn.execute(
        """
        SELECT service, version, gates_passed, gates_total,
               blocking_reasons, recorded_at
        FROM releases WHERE service = ?
        ORDER BY recorded_at DESC, id DESC
        """,
        (service,),
    ).fetchall()
    return [
        {
            "service": r[0],
            "version": r[1],
            "gates_passed": r[2],
            "gates_total": r[3],
            "blocking_reasons": r[4],
            "recorded_at": r[5],
        }
        for r in rows
    ]


def release_by_version(
    conn: sqlite3.Connection, service: str, version: str
) -> dict | None:
    row = conn.execute(
        """
        SELECT service, version, gates_passed, gates_total,
               blocking_reasons, recorded_at
        FROM releases WHERE service = ? AND version = ?
        """,
        (service, version),
    ).fetchone()
    if row is None:
        return None
    return {
        "service": row[0],
        "version": row[1],
        "gates_passed": row[2],
        "gates_total": row[3],
        "blocking_reasons": row[4],
        "recorded_at": row[5],
    }


def rollout_events_for_release(
    conn: sqlite3.Connection, service: str, version: str
) -> list[dict]:
    rows = conn.execute(
        """
        SELECT stage_percent, event, recorded_at
        FROM rollout_events
        WHERE service = ? AND version = ?
        ORDER BY id
        """,
        (service, version),
    ).fetchall()
    return [
        {"stage_percent": r[0], "event": r[1], "recorded_at": r[2]}
        for r in rows
    ]


def rollback_count(conn: sqlite3.Connection, service: str) -> int:
    """How many recorded rollout events for a service were rollbacks."""
    row = conn.execute(
        """
        SELECT COUNT(*) FROM rollout_events
        WHERE service = ? AND event LIKE '%rolled back%'
        """,
        (service,),
    ).fetchone()
    return row[0]
