"""Warehouse models: durable, keyed, historical.

- dim_zone: SCD Type 2 — a zone keeps its history; a renamed zone
  closes the old row (valid_to set, current=0) and opens a new one.
- dim_competitor: one row per competitor + service.
- fact_market_snapshot: grain is one row per (zone, snapshot_date,
  source, competitor, service). The natural key is unique, so a load
  is idempotent: re-running the same batch inserts nothing twice.
  Spark equivalent: Delta tables with MERGE on the natural key and a
  watermark on snapshot_date for incremental loads.

Loads are incremental: only rows with snapshot_date newer than the
stored watermark are loaded (or an explicit backfill range).
"""

from __future__ import annotations

import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS dim_zone (
    zone_key INTEGER PRIMARY KEY AUTOINCREMENT,
    zone TEXT NOT NULL,
    city TEXT,
    valid_from TEXT NOT NULL,
    valid_to TEXT,
    current INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS dim_competitor (
    competitor_key INTEGER PRIMARY KEY AUTOINCREMENT,
    competitor TEXT NOT NULL,
    service TEXT NOT NULL,
    UNIQUE (competitor, service)
);
CREATE TABLE IF NOT EXISTS fact_market_snapshot (
    snapshot_key INTEGER PRIMARY KEY AUTOINCREMENT,
    zone_key INTEGER NOT NULL REFERENCES dim_zone(zone_key),
    competitor_key INTEGER NOT NULL REFERENCES dim_competitor(competitor_key),
    zone TEXT NOT NULL,
    competitor TEXT NOT NULL,
    service TEXT NOT NULL,
    snapshot_date TEXT NOT NULL,
    source TEXT NOT NULL,
    price_usd REAL NOT NULL,
    demand_index REAL,
    surge_multiplier REAL,
    ingested_at TEXT,
    UNIQUE (zone, competitor, service, snapshot_date, source)
);
CREATE TABLE IF NOT EXISTS run_state (
    run_id TEXT NOT NULL,
    task TEXT NOT NULL,
    status TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (run_id, task)
);
CREATE TABLE IF NOT EXISTS watermark (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    last_snapshot_date TEXT
);
"""


def connect(db_path):
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def upsert_zone(conn, zone, city, valid_from):
    """SCD2 upsert: if the current row for this zone has a different
    city, close it and open a new current row. Returns the zone_key."""
    cur = conn.execute(
        "SELECT zone_key, city FROM dim_zone WHERE zone = ? AND current = 1",
        (zone,),
    )
    row = cur.fetchone()
    if row and row[1] == city:
        return row[0]
    if row:
        conn.execute(
            "UPDATE dim_zone SET current = 0, valid_to = ? WHERE zone_key = ?",
            (valid_from, row[0]),
        )
    cur = conn.execute(
        "INSERT INTO dim_zone (zone, city, valid_from, current) VALUES (?, ?, ?, 1)",
        (zone, city, valid_from),
    )
    return cur.lastrowid


def get_or_create_competitor(conn, competitor, service):
    conn.execute(
        "INSERT OR IGNORE INTO dim_competitor (competitor, service) VALUES (?, ?)",
        (competitor, service or "ride"),
    )
    row = conn.execute(
        "SELECT competitor_key FROM dim_competitor WHERE competitor = ? AND service = ?",
        (competitor, service or "ride"),
    ).fetchone()
    return row[0]


def get_watermark(conn):
    row = conn.execute("SELECT last_snapshot_date FROM watermark WHERE id = 1").fetchone()
    return row[0] if row else None


def set_watermark(conn, snapshot_date):
    conn.execute(
        "INSERT INTO watermark (id, last_snapshot_date) VALUES (1, ?) "
        "ON CONFLICT(id) DO UPDATE SET last_snapshot_date = "
        "MAX(last_snapshot_date, excluded.last_snapshot_date)",
        (snapshot_date,),
    )


def load_rows(conn, rows, backfill=False):
    """Incremental load. Skips rows at or before the watermark unless
    `backfill` is set. Idempotent via the fact table's UNIQUE key:
    re-loading the same batch inserts 0 new rows. Returns
    (inserted, skipped_as_duplicate_or_old)."""
    watermark = None if backfill else get_watermark(conn)
    inserted = skipped = 0
    max_date = watermark
    for row in rows:
        date = row.get("snapshot_date", "")
        if watermark and date <= watermark:
            skipped += 1
            continue
        zone_key = upsert_zone(
            conn, row["zone"], row.get("city", ""), date
        )
        comp_key = get_or_create_competitor(
            conn, row["competitor"], row.get("service") or "ride"
        )
        cur = conn.execute(
            "INSERT OR IGNORE INTO fact_market_snapshot "
            "(zone_key, competitor_key, zone, competitor, service, "
            " snapshot_date, source, price_usd, demand_index, "
            " surge_multiplier, ingested_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                zone_key,
                comp_key,
                row["zone"],
                row["competitor"],
                row.get("service") or "ride",
                date,
                row.get("source", "unknown"),
                row["price_usd"],
                row.get("demand_index"),
                row.get("surge_multiplier"),
                row.get("ingested_at", ""),
            ),
        )
        if cur.rowcount:
            inserted += 1
            if max_date is None or date > max_date:
                max_date = date
        else:
            skipped += 1
    if max_date:
        set_watermark(conn, max_date)
    conn.commit()
    return inserted, skipped


def fact_count(conn):
    return conn.execute("SELECT COUNT(*) FROM fact_market_snapshot").fetchone()[0]


def fact_price_total(conn):
    row = conn.execute(
        "SELECT COALESCE(SUM(price_usd), 0) FROM fact_market_snapshot"
    ).fetchone()
    return row[0]


def daily_average_price(conn):
    """Analyst-facing aggregate: average competitor price by zone/day."""
    return conn.execute(
        "SELECT zone, snapshot_date, ROUND(AVG(price_usd), 2) AS avg_price, "
        "COUNT(*) AS n FROM fact_market_snapshot "
        "GROUP BY zone, snapshot_date ORDER BY zone, snapshot_date"
    ).fetchall()
