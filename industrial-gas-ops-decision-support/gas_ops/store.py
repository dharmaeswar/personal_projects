"""Relational store (SQLite) for plants, customers, demand and deliveries.

Schema is a small star around demand history: plants and customers are
dimensions, demand_history and deliveries are facts, inventory is a
snapshot per plant. Indexes exist on every join / filter column used by
the API, and `explain_history_lookup` proves the planner uses them.
"""

import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS plants (
    plant_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    product TEXT NOT NULL,
    daily_capacity_t REAL NOT NULL,
    x_km REAL NOT NULL,
    y_km REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS customers (
    customer_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    product TEXT NOT NULL,
    base_demand_t REAL NOT NULL,
    x_km REAL NOT NULL,
    y_km REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS demand_history (
    customer_id TEXT NOT NULL REFERENCES customers(customer_id),
    day INTEGER NOT NULL,
    demand_t REAL NOT NULL,
    PRIMARY KEY (customer_id, day)
);
CREATE INDEX IF NOT EXISTS idx_demand_customer_day
    ON demand_history(customer_id, day);
CREATE TABLE IF NOT EXISTS inventory (
    plant_id TEXT PRIMARY KEY REFERENCES plants(plant_id),
    on_hand_t REAL NOT NULL,
    safety_stock_t REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS deliveries (
    delivery_id INTEGER PRIMARY KEY AUTOINCREMENT,
    plant_id TEXT NOT NULL REFERENCES plants(plant_id),
    customer_id TEXT NOT NULL REFERENCES customers(customer_id),
    tonnes REAL NOT NULL,
    distance_km REAL NOT NULL,
    planned_day INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_deliveries_plant_day
    ON deliveries(plant_id, planned_day);
"""


def init_db(path=":memory:"):
    """Create the schema and return an open connection."""
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    return conn


def seed(conn, plants, customers, history):
    """Load plants, customers, demand history and opening inventory."""
    conn.executemany("INSERT INTO plants VALUES (?,?,?,?,?,?)", plants)
    conn.executemany("INSERT INTO customers VALUES (?,?,?,?,?,?)", customers)
    rows = [
        (cust_id, day, value)
        for cust_id, series in history.items()
        for day, value in enumerate(series)
    ]
    conn.executemany("INSERT INTO demand_history VALUES (?,?,?)", rows)
    opening = []
    for plant_id, _name, _product, capacity, _x, _y in plants:
        # Opening stock is 60% of one day of capacity; safety stock 25%.
        opening.append((plant_id, round(capacity * 0.60, 2), round(capacity * 0.25, 2)))
    conn.executemany("INSERT INTO inventory VALUES (?,?,?)", opening)
    conn.commit()


def get_customer_history(conn, customer_id):
    """Demand series for one customer, oldest first (uses the index)."""
    cur = conn.execute(
        "SELECT day, demand_t FROM demand_history"
        " WHERE customer_id = ? ORDER BY day",
        (customer_id,),
    )
    return [row[1] for row in cur.fetchall()]


def explain_history_lookup(conn, customer_id):
    """EXPLAIN QUERY PLAN for the history lookup; used to prove index use."""
    cur = conn.execute(
        "EXPLAIN QUERY PLAN SELECT day, demand_t FROM demand_history"
        " WHERE customer_id = ? ORDER BY day",
        (customer_id,),
    )
    return " | ".join(row[3] for row in cur.fetchall())


def get_inventory(conn):
    cur = conn.execute(
        "SELECT p.plant_id, p.name, p.product, i.on_hand_t, i.safety_stock_t"
        " FROM inventory i JOIN plants p ON p.plant_id = i.plant_id"
        " ORDER BY p.plant_id"
    )
    return [
        {
            "plant_id": r[0],
            "name": r[1],
            "product": r[2],
            "on_hand_t": r[3],
            "safety_stock_t": r[4],
        }
        for r in cur.fetchall()
    ]


def record_delivery(conn, plant_id, customer_id, tonnes, distance_km, planned_day):
    cur = conn.execute(
        "INSERT INTO deliveries (plant_id, customer_id, tonnes, distance_km,"
        " planned_day) VALUES (?,?,?,?,?)",
        (plant_id, customer_id, tonnes, distance_km, planned_day),
    )
    conn.commit()
    return cur.lastrowid


def list_deliveries(conn, plant_id=None):
    sql = (
        "SELECT delivery_id, plant_id, customer_id, tonnes, distance_km,"
        " planned_day FROM deliveries"
    )
    args = []
    if plant_id is not None:
        sql += " WHERE plant_id = ?"
        args.append(plant_id)
    sql += " ORDER BY planned_day, delivery_id"
    cur = conn.execute(sql, args)
    return [
        {
            "delivery_id": r[0],
            "plant_id": r[1],
            "customer_id": r[2],
            "tonnes": r[3],
            "distance_km": r[4],
            "planned_day": r[5],
        }
        for r in cur.fetchall()
    ]
