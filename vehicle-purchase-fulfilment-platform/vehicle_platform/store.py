"""Persistence: orders and payments in SQLite (SQL), vehicle listings
in a JSON document store (NoSQL-style, one document per VIN).

Both stores are file-backed and local; no database server is needed.
The service layer in api.py writes the order row, the vehicle
document update, and the event-log record together so a failed step
leaves nothing half-written.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path

from .orders import Order

SCHEMA = """
CREATE TABLE IF NOT EXISTS orders (
    order_id TEXT PRIMARY KEY,
    vin TEXT NOT NULL,
    customer_id TEXT NOT NULL,
    list_price_cents INTEGER NOT NULL,
    state_code TEXT NOT NULL,
    delivery_zip TEXT NOT NULL,
    status TEXT NOT NULL,
    total_cents INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_orders_customer ON orders(customer_id);
CREATE INDEX IF NOT EXISTS idx_orders_vin ON orders(vin);
CREATE TABLE IF NOT EXISTS payments (
    payment_id TEXT PRIMARY KEY,
    order_id TEXT NOT NULL REFERENCES orders(order_id),
    amount_cents INTEGER NOT NULL,
    method TEXT NOT NULL
);
"""


class OrderStore:
    """SQLite-backed order and payment store."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        # The HTTP server serves on worker threads; one connection shared
        # across threads needs check_same_thread=False plus our own lock.
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._lock = threading.Lock()
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    def save_order(self, order: Order) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO orders VALUES (?,?,?,?,?,?,?,?)",
                (
                    order.order_id,
                    order.vin,
                    order.customer_id,
                    order.list_price_cents,
                    order.state_code,
                    order.delivery_zip,
                    order.status,
                    order.total_cents(),
                ),
            )
            self._conn.commit()

    def get_order(self, order_id: str) -> Order | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT order_id, vin, customer_id, list_price_cents,"
                " state_code, delivery_zip, status FROM orders WHERE order_id=?",
                (order_id,),
            ).fetchone()
        if row is None:
            return None
        return Order(*row)

    def list_orders(self, customer_id: str | None = None) -> list[Order]:
        with self._lock:
            if customer_id:
                rows = self._conn.execute(
                    "SELECT order_id, vin, customer_id, list_price_cents,"
                    " state_code, delivery_zip, status FROM orders"
                    " WHERE customer_id=? ORDER BY order_id",
                    (customer_id,),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT order_id, vin, customer_id, list_price_cents,"
                    " state_code, delivery_zip, status FROM orders ORDER BY order_id"
                ).fetchall()
        return [Order(*row) for row in rows]

    def save_payment(self, payment_id: str, order_id: str,
                     amount_cents: int, method: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO payments VALUES (?,?,?,?)",
                (payment_id, order_id, amount_cents, method),
            )
            self._conn.commit()

    def close(self) -> None:
        self._conn.close()


class VehicleDocStore:
    """JSON document store: one file per VIN, schemaless fields."""

    def __init__(self, docs_dir: str | Path):
        self.docs_dir = Path(docs_dir)
        self.docs_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, vin: str) -> Path:
        return self.docs_dir / f"{vin}.json"

    def put_vehicle(self, doc: dict) -> None:
        vin = doc["vin"]
        self._path(vin).write_text(json.dumps(doc, indent=2, sort_keys=True))

    def get_vehicle(self, vin: str) -> dict | None:
        path = self._path(vin)
        if not path.exists():
            return None
        return json.loads(path.read_text())

    def list_vehicles(self) -> list[dict]:
        docs = []
        for path in sorted(self.docs_dir.glob("*.json")):
            docs.append(json.loads(path.read_text()))
        return docs

    def mark_reserved(self, vin: str, order_id: str) -> dict | None:
        doc = self.get_vehicle(vin)
        if doc is None:
            return None
        doc["status"] = "RESERVED"
        doc["order_id"] = order_id
        self.put_vehicle(doc)
        return doc
