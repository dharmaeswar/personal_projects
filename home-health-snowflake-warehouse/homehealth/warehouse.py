"""Warehouse model for the home-health data warehouse.

Star schema (SQLite here as a stand-in for Snowflake; the production DDL
lives in ``homehealth/sql/01_create_tables.sql``):

- ``dim_patient`` — SCD Type 2 on care plan: a plan change closes the old
  row (``valid_to`` set, ``is_current = 0``) and opens a new current row.
- ``dim_clinician`` — one row per clinician id.
- ``dim_date`` — one row per visit date.
- ``fact_home_visit`` — grain: one visit per patient per clinician per day.
  UNIQUE natural key (visit_id) makes loads idempotent.
- ``load_log`` — one row per load (source rows, loaded, quarantined).
- ``quarantine`` — every rejected row with its reasons.
- ``run_state`` — DAG run state + the incremental-load watermark.

Medallion mapping (Databricks-style): bronze = raw ingested rows as
received, silver = validated + modeled rows, gold = the reporting view
``v_visit_summary`` built only from silver.
"""

from __future__ import annotations

import sqlite3
from datetime import date

SCHEMA = """
CREATE TABLE IF NOT EXISTS dim_patient (
    patient_sk INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_key TEXT NOT NULL,
    patient_name TEXT NOT NULL,
    care_plan TEXT NOT NULL,
    valid_from TEXT NOT NULL,
    valid_to TEXT,
    is_current INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS dim_clinician (
    clinician_sk INTEGER PRIMARY KEY AUTOINCREMENT,
    clinician_id TEXT NOT NULL UNIQUE,
    clinician_name TEXT NOT NULL DEFAULT 'Unknown'
);
CREATE TABLE IF NOT EXISTS dim_date (
    date_sk TEXT PRIMARY KEY,
    visit_date TEXT NOT NULL,
    year INTEGER NOT NULL,
    month INTEGER NOT NULL,
    day INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS fact_home_visit (
    visit_id TEXT PRIMARY KEY,
    patient_sk INTEGER NOT NULL REFERENCES dim_patient(patient_sk),
    clinician_sk INTEGER NOT NULL REFERENCES dim_clinician(clinician_sk),
    date_sk TEXT NOT NULL REFERENCES dim_date(date_sk),
    duration_min INTEGER NOT NULL,
    assessment_score INTEGER NOT NULL,
    source TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    loaded_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS load_log (
    load_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    source_rows INTEGER NOT NULL,
    loaded INTEGER NOT NULL,
    quarantined INTEGER NOT NULL,
    loaded_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS quarantine (
    quarantine_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    visit_id TEXT,
    reasons TEXT NOT NULL,
    loaded_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS run_state (
    run_id TEXT NOT NULL,
    task TEXT NOT NULL,
    status TEXT NOT NULL,
    PRIMARY KEY (run_id, task)
);
CREATE TABLE IF NOT EXISTS watermark (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    last_visit_date TEXT
);
INSERT OR IGNORE INTO watermark (id, last_visit_date) VALUES (1, NULL);
CREATE VIEW IF NOT EXISTS v_visit_summary AS
SELECT d.visit_date,
       COUNT(*) AS visits,
       SUM(f.duration_min) AS total_minutes,
       ROUND(AVG(f.assessment_score), 1) AS avg_assessment_score
FROM fact_home_visit f
JOIN dim_date d ON d.date_sk = f.date_sk
GROUP BY d.visit_date
ORDER BY d.visit_date;
"""


def connect(db_path: str = ":memory:") -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def get_watermark(conn: sqlite3.Connection) -> str | None:
    row = conn.execute(
        "SELECT last_visit_date FROM watermark WHERE id = 1"
    ).fetchone()
    return row[0] if row else None


def _upsert_patient(
    conn: sqlite3.Connection, patient_key: str, care_plan: str, visit_date: str
) -> int:
    """Return the current patient surrogate key, opening a new SCD2 row
    when the care plan changed."""
    row = conn.execute(
        "SELECT patient_sk, care_plan FROM dim_patient "
        "WHERE patient_key = ? AND is_current = 1",
        (patient_key,),
    ).fetchone()
    if row is None:
        cur = conn.execute(
            "INSERT INTO dim_patient "
            "(patient_key, patient_name, care_plan, valid_from, is_current) "
            "VALUES (?, ?, ?, ?, 1)",
            (patient_key, f"Patient {patient_key}", care_plan, visit_date),
        )
        return cur.lastrowid
    if row["care_plan"] != care_plan:
        conn.execute(
            "UPDATE dim_patient SET valid_to = ?, is_current = 0 "
            "WHERE patient_sk = ?",
            (visit_date, row["patient_sk"]),
        )
        cur = conn.execute(
            "INSERT INTO dim_patient "
            "(patient_key, patient_name, care_plan, valid_from, is_current) "
            "VALUES (?, ?, ?, ?, 1)",
            (patient_key, f"Patient {patient_key}", care_plan, visit_date),
        )
        return cur.lastrowid
    return row["patient_sk"]


def _upsert_clinician(conn: sqlite3.Connection, clinician_id: str) -> int:
    # Select first: INSERT OR IGNORE leaves lastrowid stale when the row
    # already exists, which would return a wrong surrogate key.
    row = conn.execute(
        "SELECT clinician_sk FROM dim_clinician WHERE clinician_id = ?",
        (clinician_id,),
    ).fetchone()
    if row is not None:
        return row["clinician_sk"]
    cur = conn.execute(
        "INSERT INTO dim_clinician (clinician_id) VALUES (?)",
        (clinician_id,),
    )
    return cur.lastrowid


def _upsert_date(conn: sqlite3.Connection, visit_date: str) -> str:
    year, month, day = (int(part) for part in visit_date.split("-"))
    conn.execute(
        "INSERT OR IGNORE INTO dim_date "
        "(date_sk, visit_date, year, month, day) VALUES (?, ?, ?, ?, ?)",
        (visit_date, visit_date, year, month, day),
    )
    return visit_date


def load_visits(
    conn: sqlite3.Connection,
    valid: list[dict],
    quarantined: list[dict],
    run_id: str,
    source_rows: int,
    incremental: bool = True,
) -> dict:
    """Load validated visits. Returns load counts + reconciliation.

    Incremental loads skip rows at or before the watermark; a full refresh
    ignores it. Inserts are idempotent on visit_id, so a re-run loads 0.
    """
    watermark = get_watermark(conn) if incremental else None
    loaded = 0
    skipped = 0
    max_date: str | None = watermark
    today = date.today().isoformat()
    for record in valid:
        visit_date = record["visit_date"]
        if watermark is not None and visit_date <= watermark:
            skipped += 1
            continue
        patient_sk = _upsert_patient(
            conn, record["patient_key"], record["care_plan"], visit_date
        )
        clinician_sk = _upsert_clinician(conn, record["clinician_id"])
        date_sk = _upsert_date(conn, visit_date)
        cur = conn.execute(
            "INSERT OR IGNORE INTO fact_home_visit "
            "(visit_id, patient_sk, clinician_sk, date_sk, duration_min, "
            " assessment_score, source, schema_version, loaded_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                record["visit_id"],
                patient_sk,
                clinician_sk,
                date_sk,
                record["duration_min"],
                record["assessment_score"],
                record["source"],
                record["schema_version"],
                today,
            ),
        )
        if cur.rowcount == 1:
            loaded += 1
            if max_date is None or visit_date > max_date:
                max_date = visit_date
        else:
            skipped += 1
    for bad in quarantined:
        conn.execute(
            "INSERT INTO quarantine (run_id, visit_id, reasons, loaded_at) "
            "VALUES (?, ?, ?, ?)",
            (
                run_id,
                bad.get("visit_id"),
                "; ".join(bad["_quarantine_reasons"]),
                today,
            ),
        )
    if max_date is not None:
        conn.execute(
            "UPDATE watermark SET last_visit_date = ? WHERE id = 1",
            (max_date,),
        )
    conn.execute(
        "INSERT INTO load_log "
        "(run_id, source_rows, loaded, quarantined, loaded_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (run_id, source_rows, loaded, len(quarantined), today),
    )
    conn.commit()
    fact_count = conn.execute(
        "SELECT COUNT(*) FROM fact_home_visit"
    ).fetchone()[0]
    return {
        "loaded": loaded,
        "skipped": skipped,
        "quarantined": len(quarantined),
        "fact_rows": fact_count,
        "reconciled": source_rows == loaded + skipped + len(quarantined),
    }
