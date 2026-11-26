"""PHI governance for the home-health warehouse.

Rules enforced here (the pattern a Snowflake deployment would enforce with
masking policies and role-based access):

- Patient names never reach reporting tables in plain text: they are
  SHA-256 hashed (salted) before a reporting view is built.
- Every load and every quarantine decision is written to an audit log.
- Identifiable fields are readable only by the ``care_team`` role; other
  roles (``analyst``, ``auditor``) see hashed values only.
"""

from __future__ import annotations

import hashlib
import sqlite3

SALT = "home-health-demo-salt"

AUDIT_SCHEMA = """
CREATE TABLE IF NOT EXISTS audit_log (
    audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    action TEXT NOT NULL,
    detail TEXT NOT NULL,
    logged_at TEXT NOT NULL
);
"""

READABLE_ROLES = {"care_team"}
HASHED_ROLES = {"analyst", "auditor"}


def hash_patient_name(patient_key: str, patient_name: str) -> str:
    """One-way hash of a patient name for reporting tables."""
    digest = hashlib.sha256(
        f"{SALT}:{patient_key}:{patient_name}".encode("utf-8")
    ).hexdigest()
    return f"sha256:{digest[:16]}"


def ensure_audit_table(conn: sqlite3.Connection) -> None:
    conn.executescript(AUDIT_SCHEMA)
    conn.commit()


def audit(
    conn: sqlite3.Connection, run_id: str, action: str, detail: str,
    logged_at: str,
) -> None:
    ensure_audit_table(conn)
    conn.execute(
        "INSERT INTO audit_log (run_id, action, detail, logged_at) "
        "VALUES (?, ?, ?, ?)",
        (run_id, action, detail, logged_at),
    )
    conn.commit()


def can_read_identifiable(role: str) -> bool:
    """Only the care team may read identifiable patient fields."""
    return role in READABLE_ROLES


def reporting_patient_name(
    role: str, patient_key: str, patient_name: str
) -> str:
    """Name as a role is allowed to see it: plain for care_team, hashed
    for everyone else. Unknown roles get hashed values too."""
    if can_read_identifiable(role):
        return patient_name
    return hash_patient_name(patient_key, patient_name)
