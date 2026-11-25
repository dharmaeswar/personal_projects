"""Warehouse: staging -> fact load, incremental (watermark) and full.

The local warehouse is SQLite, standing in for the SQL Server warehouse
in the posting; the same load logic is expressed as T-SQL stored
procedures in claims_etl/sql/. Every load writes a load_log row so the
reconciliation in loads.py can prove what happened.
"""

import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS dim_patient (
    patient_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    eligible TEXT NOT NULL CHECK (eligible IN ('Y', 'N')),
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS dim_drug (
    ndc TEXT PRIMARY KEY,
    drug_name TEXT NOT NULL,
    unit_price REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS fact_claims (
    claim_id TEXT PRIMARY KEY,
    patient_id TEXT NOT NULL,
    ndc TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    days_supply INTEGER NOT NULL,
    fill_date TEXT NOT NULL,
    pharmacy_id TEXT NOT NULL,
    prescriber_id TEXT NOT NULL,
    amount REAL NOT NULL,
    load_id INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS load_log (
    load_id INTEGER PRIMARY KEY AUTOINCREMENT,
    mode TEXT NOT NULL,
    source_rows INTEGER NOT NULL,
    loaded_rows INTEGER NOT NULL,
    quarantined_rows INTEGER NOT NULL,
    watermark TEXT,
    loaded_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def connect(db_path):
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA)
    return conn


def upsert_dimensions(conn, eligibility, pricing):
    for patient in eligibility.values():
        conn.execute(
            "INSERT OR REPLACE INTO dim_patient VALUES (?,?,?,?,?)",
            (patient["patient_id"], patient["name"], patient["eligible"],
             patient["start_date"], patient["end_date"]))
    for ndc, info in pricing.items():
        conn.execute(
            "INSERT OR REPLACE INTO dim_drug VALUES (?,?,?)",
            (ndc, info["drug"], info["unit_price"]))
    conn.commit()


def load_full(conn, claims, load_id):
    """Full refresh: replace the fact table with this batch."""
    conn.execute("DELETE FROM fact_claims")
    for claim in claims:
        _insert_claim(conn, claim, load_id)
    conn.commit()
    return len(claims)


def load_incremental(conn, claims, watermark, load_id):
    """Insert only claims with fill_date after the watermark.

    Returns (inserted_count, new_watermark). Re-running the same batch
    inserts 0 rows, which the reconciliation report proves.
    """
    inserted = 0
    new_watermark = watermark
    for claim in claims:
        if watermark is not None and claim["fill_date"] <= watermark:
            continue
        cur = conn.execute(
            "INSERT OR IGNORE INTO fact_claims VALUES (?,?,?,?,?,?,?,?,?,?)",
            _claim_row(claim, load_id))
        inserted += cur.rowcount
        if new_watermark is None or claim["fill_date"] > new_watermark:
            new_watermark = claim["fill_date"]
    conn.commit()
    return inserted, new_watermark


def _claim_row(claim, load_id):
    return (claim["claim_id"], claim["patient_id"], claim["ndc"],
            claim["quantity"], claim["days_supply"], claim["fill_date"],
            claim["pharmacy_id"], claim["prescriber_id"], claim["amount"],
            load_id)


def _insert_claim(conn, claim, load_id):
    conn.execute("INSERT INTO fact_claims VALUES (?,?,?,?,?,?,?,?,?,?)",
                 _claim_row(claim, load_id))


def log_load(conn, mode, source_rows, loaded_rows, quarantined_rows,
             watermark):
    cur = conn.execute(
        "INSERT INTO load_log (mode, source_rows, loaded_rows,"
        " quarantined_rows, watermark) VALUES (?,?,?,?,?)",
        (mode, source_rows, loaded_rows, quarantined_rows, watermark))
    conn.commit()
    return cur.lastrowid


def latest_watermark(conn):
    row = conn.execute(
        "SELECT watermark FROM load_log WHERE watermark IS NOT NULL"
        " ORDER BY load_id DESC LIMIT 1").fetchone()
    return row[0] if row else None


def fact_count(conn):
    return conn.execute("SELECT COUNT(*) FROM fact_claims").fetchone()[0]
