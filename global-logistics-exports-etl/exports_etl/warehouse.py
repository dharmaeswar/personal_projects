"""Star-schema warehouse for export shipments (SQLite).

Schema:
- dim_date (date_key, date, year, month, day)
- dim_country (country_key, country_code)
- dim_product (product_key, hs_code)
- fact_exports (shipment_id PK, date_key, country_key, product_key,
  origin, value_usd, weight_kg, customs_status)
- load_watermark (id, last_ship_date) — one row, drives incremental loads.

Loads are idempotent: fact rows use INSERT OR IGNORE on shipment_id, so
re-running a manifest loads nothing twice. The watermark advances only to
the latest ship date actually loaded.
"""

import sqlite3

DDL = """
CREATE TABLE IF NOT EXISTS dim_date (
    date_key INTEGER PRIMARY KEY,
    date TEXT NOT NULL UNIQUE,
    year INTEGER NOT NULL,
    month INTEGER NOT NULL,
    day INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS dim_country (
    country_key INTEGER PRIMARY KEY,
    country_code TEXT NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS dim_product (
    product_key INTEGER PRIMARY KEY,
    hs_code TEXT NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS fact_exports (
    shipment_id TEXT PRIMARY KEY,
    date_key INTEGER NOT NULL REFERENCES dim_date (date_key),
    country_key INTEGER NOT NULL REFERENCES dim_country (country_key),
    product_key INTEGER NOT NULL REFERENCES dim_product (product_key),
    origin TEXT NOT NULL,
    value_usd TEXT NOT NULL,
    weight_kg TEXT NOT NULL,
    customs_status TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS load_watermark (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    last_ship_date TEXT
);
"""


def connect(db_path):
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(DDL)
    conn.commit()
    return conn


def _date_key(conn, ship_date):
    key = ship_date.year * 10000 + ship_date.month * 100 + ship_date.day
    conn.execute(
        "INSERT OR IGNORE INTO dim_date (date_key, date, year, month, day)"
        " VALUES (?, ?, ?, ?, ?)",
        (key, ship_date.isoformat(), ship_date.year, ship_date.month, ship_date.day),
    )
    return key


def _country_key(conn, code):
    conn.execute(
        "INSERT OR IGNORE INTO dim_country (country_code) VALUES (?)", (code,)
    )
    return conn.execute(
        "SELECT country_key FROM dim_country WHERE country_code = ?", (code,)
    ).fetchone()[0]


def _product_key(conn, hs_code):
    conn.execute(
        "INSERT OR IGNORE INTO dim_product (hs_code) VALUES (?)", (hs_code,)
    )
    return conn.execute(
        "SELECT product_key FROM dim_product WHERE hs_code = ?", (hs_code,)
    ).fetchone()[0]


def load_rows(conn, rows):
    """Load validated, USD-converted rows. Returns the count actually inserted."""
    inserted = 0
    latest = None
    for row in rows:
        date_key = _date_key(conn, row["ship_date"])
        country_key = _country_key(conn, row["dest_country"])
        product_key = _product_key(conn, row["hs_code"])
        cursor = conn.execute(
            "INSERT OR IGNORE INTO fact_exports"
            " (shipment_id, date_key, country_key, product_key, origin,"
            "  value_usd, weight_kg, customs_status)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                row["shipment_id"],
                date_key,
                country_key,
                product_key,
                row["origin"],
                str(row["value_usd"]),
                str(row["weight_kg"]),
                row["customs_status"],
            ),
        )
        if cursor.rowcount:
            inserted += 1
            if latest is None or row["ship_date"] > latest:
                latest = row["ship_date"]
    if latest is not None:
        conn.execute(
            "INSERT INTO load_watermark (id, last_ship_date) VALUES (1, ?)"
            " ON CONFLICT(id) DO UPDATE SET last_ship_date ="
            " MAX(last_ship_date, excluded.last_ship_date)",
            (latest.isoformat(),),
        )
    conn.commit()
    return inserted


def get_watermark(conn):
    row = conn.execute(
        "SELECT last_ship_date FROM load_watermark WHERE id = 1"
    ).fetchone()
    return row[0] if row else None


def total_value_usd(conn):
    row = conn.execute("SELECT SUM(CAST(value_usd AS REAL)) FROM fact_exports").fetchone()
    return row[0] or 0.0


def monthly_value_by_country(conn, year, month):
    """USD export value per destination country for one month."""
    return conn.execute(
        "SELECT c.country_code, SUM(CAST(f.value_usd AS REAL)) AS total"
        " FROM fact_exports f"
        " JOIN dim_date d ON f.date_key = d.date_key"
        " JOIN dim_country c ON f.country_key = c.country_key"
        " WHERE d.year = ? AND d.month = ?"
        " GROUP BY c.country_code ORDER BY total DESC",
        (year, month),
    ).fetchall()


def top_products(conn, limit=5):
    """Top HS codes by USD export value."""
    return conn.execute(
        "SELECT p.hs_code, SUM(CAST(f.value_usd AS REAL)) AS total"
        " FROM fact_exports f"
        " JOIN dim_product p ON f.product_key = p.product_key"
        " GROUP BY p.hs_code ORDER BY total DESC LIMIT ?",
        (limit,),
    ).fetchall()
