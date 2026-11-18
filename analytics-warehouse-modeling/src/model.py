"""Star-schema DDL for the analytics warehouse (SQLite).

Grain: one row of fact_service_usage = one service's usage by one
account in one region on one day, for one source event.

    dim_date (date_key) ─┐
    dim_service (SCD2) ─┼─► fact_service_usage ◄─┐
    dim_account ─────────┤                         │ load_state
    dim_region ──────────┘                         │ (watermark)

dim_service is Slowly Changing Dimension Type 2: a change in tier or
pricing_model closes the current row (effective_to, is_current=0)
and opens a new row, so history is preserved. dim_account and
dim_region are Type 1 (current value only) — documented in README.
"""
from __future__ import annotations

import sqlite3

DDL = """
CREATE TABLE IF NOT EXISTS dim_date (
    date_key     INTEGER PRIMARY KEY,  -- YYYYMMDD
    date_value   TEXT NOT NULL UNIQUE, -- YYYY-MM-DD
    year         INTEGER NOT NULL,
    month        INTEGER NOT NULL,
    day          INTEGER NOT NULL,
    quarter      INTEGER NOT NULL,
    weekday      INTEGER NOT NULL,     -- Mon=0 .. Sun=6
    is_weekend   INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS dim_service (
    service_key   INTEGER PRIMARY KEY AUTOINCREMENT,
    service_code  TEXT NOT NULL,
    service_name  TEXT NOT NULL,
    tier          TEXT NOT NULL,
    pricing_model TEXT NOT NULL,
    effective_from TEXT NOT NULL,      -- YYYY-MM-DD
    effective_to   TEXT,               -- NULL = open-ended / current
    is_current    INTEGER NOT NULL DEFAULT 1,
    UNIQUE (service_code, effective_from)
);

CREATE TABLE IF NOT EXISTS dim_account (
    account_key  INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id   TEXT NOT NULL UNIQUE,
    account_name TEXT NOT NULL,
    account_type TEXT NOT NULL,
    owner_team   TEXT NOT NULL,
    created_date TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS dim_region (
    region_key   INTEGER PRIMARY KEY AUTOINCREMENT,
    region_code  TEXT NOT NULL UNIQUE,
    region_name  TEXT NOT NULL,
    country      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS fact_service_usage (
    fact_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id      TEXT NOT NULL UNIQUE,
    date_key      INTEGER NOT NULL REFERENCES dim_date(date_key),
    service_key   INTEGER NOT NULL REFERENCES dim_service(service_key),
    account_key   INTEGER NOT NULL REFERENCES dim_account(account_key),
    region_key    INTEGER NOT NULL REFERENCES dim_region(region_key),
    usage_qty     REAL NOT NULL CHECK (usage_qty >= 0),
    cost_usd      REAL NOT NULL CHECK (cost_usd >= 0),
    unit          TEXT NOT NULL,
    load_batch_id TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS load_state (
    state_key     TEXT PRIMARY KEY,
    value         TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_fact_date    ON fact_service_usage(date_key);
CREATE INDEX IF NOT EXISTS idx_fact_service ON fact_service_usage(service_key);
CREATE INDEX IF NOT EXISTS idx_fact_account ON fact_service_usage(account_key);
CREATE INDEX IF NOT EXISTS idx_fact_region  ON fact_service_usage(region_key);
"""


def connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn


def init_warehouse(db_path: str) -> sqlite3.Connection:
    conn = connect(db_path)
    conn.executescript(DDL)
    conn.commit()
    return conn
