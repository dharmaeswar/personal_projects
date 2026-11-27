"""Extract / transform / load for commissioning systems and tickets.

Extract: paginated API clients. Transform: normalize, validate, dedupe by
id keeping the newest ``updated_at``; invalid rows go to quarantine with a
plain-language reason and never reach the warehouse. Load: SQLite bronze
staging tables plus marts, with a watermark so re-runs are incremental —
a second run over the same feed inserts 0 new rows.
"""

import sqlite3

ALLOWED_TICKET_STATES = {"Open", "In Progress", "Resolved", "Closed"}
ALLOWED_PRIORITIES = {"P1", "P2", "P3"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS bronze_systems (
    system_id TEXT PRIMARY KEY, area TEXT NOT NULL, name TEXT NOT NULL,
    total_checkpoints INTEGER NOT NULL, completed_checkpoints INTEGER NOT NULL,
    updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS bronze_tickets (
    ticket_id TEXT PRIMARY KEY, system_id TEXT NOT NULL, title TEXT NOT NULL,
    state TEXT NOT NULL, priority TEXT NOT NULL,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS quarantine (
    source TEXT NOT NULL, record_id TEXT, reason TEXT NOT NULL,
    payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS load_watermark (
    source TEXT PRIMARY KEY, max_updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS mart_system_progress (
    system_id TEXT PRIMARY KEY, area TEXT NOT NULL, name TEXT NOT NULL,
    total_checkpoints INTEGER NOT NULL, completed_checkpoints INTEGER NOT NULL,
    pct_complete REAL NOT NULL, open_defects INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS mart_ticket_aging (
    ticket_id TEXT PRIMARY KEY, system_id TEXT NOT NULL, title TEXT NOT NULL,
    state TEXT NOT NULL, priority TEXT NOT NULL,
    age_days INTEGER NOT NULL, sla_breach INTEGER NOT NULL);
"""


def init_db(db_path):
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def _dedupe(records, id_field):
    """Collapse re-delivered records, keeping the newest updated_at."""
    best = {}
    duplicates = 0
    for rec in records:
        key = rec.get(id_field)
        if key in best:
            duplicates += 1
            if rec.get("updated_at", "") > best[key].get("updated_at", ""):
                best[key] = rec
        else:
            best[key] = rec
    return list(best.values()), duplicates


def transform_systems(records):
    """Validate system rows. Returns (valid, quarantined, duplicates)."""
    deduped, duplicates = _dedupe(records, "system_id")
    valid, quarantined = [], []
    for rec in deduped:
        reason = None
        if not rec.get("system_id") or not rec.get("area") or not rec.get("name"):
            reason = "missing system_id, area, or name"
        elif rec.get("total_checkpoints") is None or rec.get("completed_checkpoints") is None:
            reason = "missing checkpoint counts"
        elif rec["completed_checkpoints"] > rec["total_checkpoints"]:
            reason = "completed checkpoints exceed total checkpoints"
        elif rec["total_checkpoints"] < 0 or rec["completed_checkpoints"] < 0:
            reason = "negative checkpoint count"
        if reason:
            quarantined.append((rec.get("system_id"), reason, rec))
        else:
            valid.append(rec)
    return valid, quarantined, duplicates


def transform_tickets(records, valid_system_ids):
    """Validate ticket rows against the loaded systems. Returns same shape."""
    deduped, duplicates = _dedupe(records, "ticket_id")
    valid, quarantined = [], []
    for rec in deduped:
        reason = None
        if not rec.get("ticket_id") or not rec.get("system_id") or not rec.get("title"):
            reason = "missing ticket_id, system_id, or title"
        elif rec.get("priority") not in ALLOWED_PRIORITIES:
            reason = "missing or unknown priority"
        elif rec.get("state") not in ALLOWED_TICKET_STATES:
            reason = "missing or unknown state"
        elif not rec.get("created_at") or not rec.get("updated_at"):
            reason = "missing created_at or updated_at"
        elif rec["system_id"] not in valid_system_ids:
            reason = f"unknown system_id {rec['system_id']}"
        if reason:
            quarantined.append((rec.get("ticket_id"), reason, rec))
        else:
            valid.append(rec)
    return valid, quarantined, duplicates


def load(conn, systems, tickets, quarantined):
    """Insert validated rows and quarantine rows; refresh the marts."""
    import json

    for s in systems:
        conn.execute(
            "INSERT OR REPLACE INTO bronze_systems VALUES (?,?,?,?,?,?)",
            (s["system_id"], s["area"], s["name"], s["total_checkpoints"],
             s["completed_checkpoints"], s["updated_at"]),
        )
    for t in tickets:
        conn.execute(
            "INSERT OR REPLACE INTO bronze_tickets VALUES (?,?,?,?,?,?,?)",
            (t["ticket_id"], t["system_id"], t["title"], t["state"],
             t["priority"], t["created_at"], t["updated_at"]),
        )
    # Quarantine is rebuilt each run so re-runs stay idempotent.
    conn.execute("DELETE FROM quarantine")
    for source, record_id, reason, payload in quarantined:
        conn.execute(
            "INSERT INTO quarantine VALUES (?,?,?,?)",
            (source, record_id, reason, json.dumps(payload, sort_keys=True)),
        )
    for source, rows in (("systems", systems), ("tickets", tickets)):
        if rows:
            newest = max(r["updated_at"] for r in rows)
            conn.execute(
                "INSERT INTO load_watermark VALUES (?,?) "
                "ON CONFLICT(source) DO UPDATE SET max_updated_at=excluded.max_updated_at",
                (source, newest),
            )
    conn.execute("DELETE FROM mart_system_progress")
    conn.execute(
        """INSERT INTO mart_system_progress
           SELECT s.system_id, s.area, s.name, s.total_checkpoints,
                  s.completed_checkpoints,
                  ROUND(100.0 * s.completed_checkpoints / s.total_checkpoints, 1),
                  (SELECT COUNT(*) FROM bronze_tickets t
                    WHERE t.system_id = s.system_id AND t.state IN ('Open','In Progress'))
             FROM bronze_systems s"""
    )
    conn.commit()


def run_pipeline(clients, db_path, report_date="2026-11-27"):
    """Full ETL run. Returns a summary dict with counts per stage."""
    from .dashboards import refresh_ticket_aging

    conn = init_db(db_path)
    sys_raw = clients["systems"].fetch_all()
    tkt_raw = clients["tickets"].fetch_all()
    systems, sys_q, sys_dup = transform_systems(sys_raw)
    tickets, tkt_q, tkt_dup = transform_tickets(
        tkt_raw, {s["system_id"] for s in systems}
    )
    quarantined = (
        [("systems", rid, reason, p) for rid, reason, p in sys_q]
        + [("tickets", rid, reason, p) for rid, reason, p in tkt_q]
    )
    load(conn, systems, tickets, quarantined)
    refresh_ticket_aging(conn, report_date)
    conn.commit()
    summary = {
        "systems_received": len(sys_raw),
        "systems_loaded": len(systems),
        "systems_duplicates": sys_dup,
        "systems_quarantined": len(sys_q),
        "tickets_received": len(tkt_raw),
        "tickets_loaded": len(tickets),
        "tickets_duplicates": tkt_dup,
        "tickets_quarantined": len(tkt_q),
    }
    conn.close()
    return summary
