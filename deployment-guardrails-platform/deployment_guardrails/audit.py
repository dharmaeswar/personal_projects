"""Audit log: every deployment decision, queryable by service/date.

Each policy evaluation is recorded in a local SQLite database with
who asked, what was decided, when, and which guardrails failed.
The log is append-only in spirit: decisions are inserted, never
updated, so a later query shows the full history of a service.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from deployment_guardrails.policies import PolicyDecision

SCHEMA = """
CREATE TABLE IF NOT EXISTS deployment_decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    decided_at TEXT NOT NULL,
    service TEXT NOT NULL,
    version TEXT NOT NULL,
    requested_by TEXT NOT NULL,
    approved INTEGER NOT NULL,
    passed_count INTEGER NOT NULL,
    total_count INTEGER NOT NULL,
    violations TEXT NOT NULL
);
"""


@dataclass
class AuditEntry:
    """One recorded deployment decision."""

    id: int
    decided_at: str
    service: str
    version: str
    requested_by: str
    approved: bool
    passed_count: int
    total_count: int
    violations: str


def connect(db_path: str | Path) -> sqlite3.Connection:
    """Open (and create, if needed) the audit database."""
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def record_decision(
    conn: sqlite3.Connection,
    decision: PolicyDecision,
    requested_by: str,
    decided_at: str,
) -> int:
    """Insert one decision; return its row id."""
    cur = conn.execute(
        "INSERT INTO deployment_decisions "
        "(decided_at, service, version, requested_by, approved, "
        " passed_count, total_count, violations) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            decided_at,
            decision.service,
            decision.version,
            requested_by,
            1 if decision.approved else 0,
            decision.passed_count,
            decision.total_count,
            "; ".join(decision.violations),
        ),
    )
    conn.commit()
    return cur.lastrowid


def _row_to_entry(row: tuple) -> AuditEntry:
    return AuditEntry(
        id=row[0],
        decided_at=row[1],
        service=row[2],
        version=row[3],
        requested_by=row[4],
        approved=bool(row[5]),
        passed_count=row[6],
        total_count=row[7],
        violations=row[8],
    )


def decisions_for_service(
    conn: sqlite3.Connection, service: str
) -> list[AuditEntry]:
    """All decisions for one service, newest first."""
    rows = conn.execute(
        "SELECT id, decided_at, service, version, requested_by, approved,"
        " passed_count, total_count, violations "
        "FROM deployment_decisions WHERE service = ? "
        "ORDER BY decided_at DESC, id DESC",
        (service,),
    ).fetchall()
    return [_row_to_entry(r) for r in rows]


def decisions_on_date(conn: sqlite3.Connection, date: str) -> list[AuditEntry]:
    """All decisions made on one calendar date (YYYY-MM-DD)."""
    rows = conn.execute(
        "SELECT id, decided_at, service, version, requested_by, approved,"
        " passed_count, total_count, violations "
        "FROM deployment_decisions WHERE substr(decided_at, 1, 10) = ? "
        "ORDER BY decided_at, id",
        (date,),
    ).fetchall()
    return [_row_to_entry(r) for r in rows]


def rejection_count(conn: sqlite3.Connection, service: str | None = None) -> int:
    """How many decisions were rejections (optionally for one service)."""
    if service is None:
        row = conn.execute(
            "SELECT COUNT(*) FROM deployment_decisions WHERE approved = 0"
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT COUNT(*) FROM deployment_decisions "
            "WHERE approved = 0 AND service = ?",
            (service,),
        ).fetchone()
    return row[0]
