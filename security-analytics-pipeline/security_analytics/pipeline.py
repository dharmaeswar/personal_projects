"""Staging and normalization: raw security telemetry -> SQLite model.

Raw rows land in staging tables exactly as received. Normalization then
builds the small security data model (identities, assets, unified
events, findings). Rows that fail a quality rule go to quarantine with
the reason, instead of being dropped silently. Every normalized row
keeps its source event id, so lineage is a plain lookup.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime

from .data import WATERMARK
from .schema import NORMALIZED_SCHEMAS, STAGED_SCHEMAS


def connect(db_path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def create_tables(conn: sqlite3.Connection) -> None:
    for table, columns in {**STAGED_SCHEMAS, **NORMALIZED_SCHEMAS}.items():
        cols = ", ".join(
            f"{name} {dtype}{' NOT NULL' if not nullable else ''}"
            for name, (dtype, nullable) in columns.items()
        )
        conn.execute(f"CREATE TABLE IF NOT EXISTS {table} ({cols})")
    conn.commit()


def _iso(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def load_raw(conn: sqlite3.Connection, data: dict) -> dict[str, int]:
    """Load staged raw tables. Returns row counts per table."""
    counts = {}
    login_rows = [
        (
            e["event_id"],
            e["identity_id"],
            _iso(e["ts"]),
            e["ip"],
            e["country"],
            e["city"],
            int(e["success"]),
            int(e["mfa_used"]),
        )
        for e in data["login_events"]
    ]
    conn.executemany(
        "INSERT INTO raw_login_events VALUES (?,?,?,?,?,?,?,?)", login_rows
    )
    counts["raw_login_events"] = len(login_rows)

    audit_rows = [
        (
            e["event_id"],
            e["identity_id"],
            e["asset_id"],
            e["action"],
            _iso(e["ts"]),
            e["result"],
        )
        for e in data["audit_events"]
    ]
    conn.executemany(
        "INSERT INTO raw_audit_events VALUES (?,?,?,?,?,?)", audit_rows
    )
    counts["raw_audit_events"] = len(audit_rows)

    finding_rows = [
        (
            f["finding_id"],
            f["asset_id"],
            f["severity"],
            f["title"],
            _iso(f["discovered_date"]),
            _iso(f["due_date"]),
            f["status"],
            _iso(f["remediated_date"]),
        )
        for f in data["findings"]
    ]
    conn.executemany("INSERT INTO raw_findings VALUES (?,?,?,?,?,?,?,?)", finding_rows)
    counts["raw_findings"] = len(finding_rows)
    conn.commit()
    return counts


def load_dimensions(conn: sqlite3.Connection, data: dict) -> dict[str, int]:
    conn.executemany(
        "INSERT INTO identities VALUES (?,?,?,?,?,?,?,?)",
        [
            (
                i["identity_id"],
                i["name"],
                i["email"],
                i["department"],
                int(i["privileged"]),
                int(i["mfa_enabled"]),
                i["last_login_days_ago"],
                i["status"],
            )
            for i in data["identities"]
        ],
    )
    conn.executemany(
        "INSERT INTO assets VALUES (?,?,?,?,?,?)",
        [
            (
                a["asset_id"],
                a["hostname"],
                a["asset_type"],
                a["owner_identity_id"],
                a["criticality"],
                a["last_seen_days_ago"],
            )
            for a in data["assets"]
        ],
    )
    conn.commit()
    return {"identities": len(data["identities"]), "assets": len(data["assets"])}


def _is_late(ts: str) -> bool:
    return datetime.fromisoformat(ts) < WATERMARK


def normalize(conn: sqlite3.Connection, data: dict) -> dict:
    """Build normalized events/findings; quarantine bad rows.

    A row is quarantined (not normalized) when its event/finding id is a
    duplicate, a required reference is missing or unknown, or its dates
    are invalid. Late-arriving rows are valid data: they are normalized
    and flagged late_arriving = 1.
    """
    identity_ids = {i["identity_id"] for i in data["identities"]}
    asset_ids = {a["asset_id"] for a in data["assets"]}
    quarantine: list[tuple[str, str, str]] = []
    lineage: dict[str, str] = {}
    events: list[tuple] = []
    seen_event_ids: set[str] = set()

    for e in data["login_events"]:
        event_id = e["event_id"]
        if event_id in seen_event_ids:
            quarantine.append(("raw_login_events", event_id, "duplicate event_id"))
            continue
        seen_event_ids.add(event_id)
        if e["identity_id"] is None:
            quarantine.append(("raw_login_events", event_id, "null identity_id"))
            continue
        if e["identity_id"] not in identity_ids:
            quarantine.append(
                ("raw_login_events", event_id, "unknown identity_id")
            )
            continue
        ts = _iso(e["ts"])
        events.append(
            (
                event_id,
                "login",
                e["identity_id"],
                None,
                ts,
                e["country"],
                e["city"],
                e["ip"],
                int(e["success"]),
                int(e["mfa_used"]),
                None,
                None,
                int(_is_late(ts)),
                event_id,
            )
        )
        lineage[event_id] = "raw_login_events"

    for e in data["audit_events"]:
        event_id = e["event_id"]
        if event_id in seen_event_ids:
            quarantine.append(("raw_audit_events", event_id, "duplicate event_id"))
            continue
        seen_event_ids.add(event_id)
        if e["identity_id"] not in identity_ids:
            quarantine.append(
                ("raw_audit_events", event_id, "unknown identity_id")
            )
            continue
        if e["asset_id"] not in asset_ids:
            quarantine.append(("raw_audit_events", event_id, "unknown asset_id"))
            continue
        ts = _iso(e["ts"])
        events.append(
            (
                event_id,
                "audit",
                e["identity_id"],
                e["asset_id"],
                ts,
                None,
                None,
                None,
                None,
                None,
                e["action"],
                e["result"],
                int(_is_late(ts)),
                event_id,
            )
        )
        lineage[event_id] = "raw_audit_events"

    findings: list[tuple] = []
    seen_finding_ids: set[str] = set()
    for f in data["findings"]:
        finding_id = f["finding_id"]
        if finding_id in seen_finding_ids:
            quarantine.append(("raw_findings", finding_id, "duplicate finding_id"))
            continue
        seen_finding_ids.add(finding_id)
        if f["asset_id"] not in asset_ids:
            quarantine.append(("raw_findings", finding_id, "unknown asset_id"))
            continue
        if f["due_date"] < f["discovered_date"]:
            quarantine.append(
                ("raw_findings", finding_id, "due_date before discovered_date")
            )
            continue
        findings.append(
            (
                finding_id,
                f["asset_id"],
                f["severity"],
                f["title"],
                _iso(f["discovered_date"]),
                _iso(f["due_date"]),
                f["status"],
                _iso(f["remediated_date"]),
            )
        )
        lineage[finding_id] = "raw_findings"

    conn.executemany(
        "INSERT INTO events VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", events
    )
    conn.executemany(
        "INSERT INTO findings VALUES (?,?,?,?,?,?,?,?)", findings
    )
    conn.executemany(
        "INSERT INTO quarantine VALUES (?,?,?)", quarantine
    )
    conn.commit()
    return {
        "events": len(events),
        "findings": len(findings),
        "quarantine": len(quarantine),
        "lineage": lineage,
    }


def table_counts(conn: sqlite3.Connection) -> dict[str, int]:
    counts = {}
    for table in list(STAGED_SCHEMAS) + list(NORMALIZED_SCHEMAS):
        counts[table] = conn.execute(
            f"SELECT COUNT(*) FROM {table}"
        ).fetchone()[0]
    return counts
