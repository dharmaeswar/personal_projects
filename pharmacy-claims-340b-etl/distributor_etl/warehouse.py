"""Distributor warehouse: dimensional model, staging -> fact load.

Star schema for distributor shipments: dim_product, dim_customer and
fact_shipments. The local warehouse is SQLite, standing in for the
enterprise data warehouse in the posting. Loads are full refresh or
incremental by ship-date watermark; every load writes a load_log row.
"""

import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS dim_product (
    product_id TEXT PRIMARY KEY,
    product_name TEXT NOT NULL,
    unit_price REAL NOT NULL,
    on_hand INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS dim_customer (
    customer_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    active TEXT NOT NULL CHECK (active IN ('Y', 'N')),
    contract_start TEXT NOT NULL,
    contract_end TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS fact_shipments (
    shipment_id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL,
    product_id TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    ship_date TEXT NOT NULL,
    warehouse_id TEXT NOT NULL,
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


def upsert_dimensions(conn, inventory, customers):
    for product_id, info in inventory.items():
        conn.execute(
            "INSERT OR REPLACE INTO dim_product VALUES (?,?,?,?)",
            (product_id, info["product_name"], info["unit_price"],
             info["on_hand"]))
    for customer in customers.values():
        conn.execute(
            "INSERT OR REPLACE INTO dim_customer VALUES (?,?,?,?,?)",
            (customer["customer_id"], customer["name"], customer["active"],
             customer["contract_start"], customer["contract_end"]))
    conn.commit()


def load_full(conn, shipments, load_id):
    """Full refresh: replace the fact table with this batch."""
    conn.execute("DELETE FROM fact_shipments")
    for shipment in shipments:
        _insert_shipment(conn, shipment, load_id)
    conn.commit()
    return len(shipments)


def load_incremental(conn, shipments, watermark, load_id):
    """Insert only shipments with ship_date after the watermark.

    Returns (inserted_count, new_watermark, skipped_count). Re-running
    the same batch inserts 0 rows and skips all of them, which the
    reconciliation report proves.
    """
    inserted = 0
    skipped = 0
    new_watermark = watermark
    for shipment in shipments:
        if watermark is not None and shipment["ship_date"] <= watermark:
            skipped += 1
            continue
        cur = conn.execute(
            "INSERT OR IGNORE INTO fact_shipments VALUES (?,?,?,?,?,?,?,?)",
            _shipment_row(shipment, load_id))
        inserted += cur.rowcount
        if new_watermark is None or shipment["ship_date"] > new_watermark:
            new_watermark = shipment["ship_date"]
    conn.commit()
    return inserted, new_watermark, skipped


def _shipment_row(shipment, load_id):
    return (shipment["shipment_id"], shipment["customer_id"],
            shipment["product_id"], shipment["quantity"],
            shipment["ship_date"], shipment["warehouse_id"],
            shipment["amount"], load_id)


def _insert_shipment(conn, shipment, load_id):
    conn.execute("INSERT INTO fact_shipments VALUES (?,?,?,?,?,?,?,?)",
                 _shipment_row(shipment, load_id))


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
    return conn.execute("SELECT COUNT(*) FROM fact_shipments").fetchone()[0]


def total_shipped_by_product(conn):
    """Reporting query over the dimensional model: units and revenue."""
    return conn.execute(
        "SELECT p.product_name, SUM(f.quantity), ROUND(SUM(f.amount), 2)"
        " FROM fact_shipments f JOIN dim_product p"
        " ON f.product_id = p.product_id"
        " GROUP BY p.product_name ORDER BY p.product_name").fetchall()
