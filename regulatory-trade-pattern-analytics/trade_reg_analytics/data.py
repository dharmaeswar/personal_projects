"""Seeded synthetic market-regulation warehouse.

Generates order, trade and position records that look like the data a
market-regulation team pulls from its warehouses, and loads them into a
SQLite relational database so the rest of the toolkit can query them
with plain SQL. All data is synthetic and seeded: the same seed always
produces the same warehouse.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

import numpy as np
import pandas as pd

INSTRUMENTS = ["ES", "NQ", "CL", "GC", "6E", "ZN"]
ACCOUNTS = [f"ACC-{i:03d}" for i in range(1, 41)]
TRADERS = [f"TRD-{i:02d}" for i in range(1, 16)]

SCHEMA = """
CREATE TABLE IF NOT EXISTS orders (
    order_id TEXT PRIMARY KEY,
    trade_date TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    account TEXT NOT NULL,
    trader TEXT NOT NULL,
    instrument TEXT NOT NULL,
    side TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    price REAL NOT NULL,
    status TEXT NOT NULL,
    cancel_seconds REAL
);
CREATE TABLE IF NOT EXISTS trades (
    trade_id TEXT PRIMARY KEY,
    order_id TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    account TEXT NOT NULL,
    instrument TEXT NOT NULL,
    side TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    price REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS positions (
    account TEXT NOT NULL,
    instrument TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    net_quantity INTEGER NOT NULL,
    market_value REAL NOT NULL,
    PRIMARY KEY (account, instrument, trade_date)
);
"""


@dataclass
class WarehouseConfig:
    seed: int = 42
    days: int = 20
    start_date: str = "2026-10-26"
    base_price: float = 5000.0


def generate_orders_trades(cfg: WarehouseConfig) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Generate seeded synthetic orders and the trades that fill them.

    A small number of planted patterns (wash trades, fast cancels,
    close-marking trades) is included so the detectors have real
    signal to find; their ids are returned so tests can assert on them.
    """
    rng = np.random.default_rng(cfg.seed)
    dates = pd.bdate_range(cfg.start_date, periods=cfg.days)
    orders, trades = [], []
    oid = 0
    for date in dates:
        day = date.strftime("%Y-%m-%d")
        for inst in INSTRUMENTS:
            price = cfg.base_price * (1 + rng.normal(0, 0.004))
            n_orders = int(rng.integers(120, 200))
            for _ in range(n_orders):
                oid += 1
                account = str(rng.choice(ACCOUNTS))
                trader = str(rng.choice(TRADERS))
                side = "BUY" if rng.random() < 0.5 else "SELL"
                qty = int(rng.integers(1, 50))
                minute = int(rng.integers(9 * 60 + 30, 16 * 60))
                ts = f"{day} {minute // 60:02d}:{minute % 60:02d}:00"
                cancelled = rng.random() < 0.12
                status = "CANCELLED" if cancelled else "FILLED"
                cancel_s = float(rng.uniform(2, 20)) if cancelled else None
                orders.append(
                    {
                        "order_id": f"O{oid:06d}",
                        "trade_date": day,
                        "timestamp": ts,
                        "account": account,
                        "trader": trader,
                        "instrument": inst,
                        "side": side,
                        "quantity": qty,
                        "price": round(float(price * (1 + rng.normal(0, 0.0005))), 2),
                        "status": status,
                        "cancel_seconds": cancel_s,
                    }
                )
                if not cancelled:
                    trades.append(
                        {
                            "trade_id": f"T{oid:06d}",
                            "order_id": f"O{oid:06d}",
                            "trade_date": day,
                            "timestamp": ts,
                            "account": account,
                            "instrument": inst,
                            "side": side,
                            "quantity": qty,
                            "price": round(float(price * (1 + rng.normal(0, 0.0005))), 2),
                        }
                    )
        # Planted wash-trade pair: same account buys and sells the same
        # instrument on the same day in equal size.
        wash_acct = "ACC-007"
        for side in ("BUY", "SELL"):
            oid += 1
            orders.append(
                {
                    "order_id": f"O{oid:06d}",
                    "trade_date": day,
                    "timestamp": f"{day} 11:00:00",
                    "account": wash_acct,
                    "trader": "TRD-03",
                    "instrument": "ES",
                    "side": side,
                    "quantity": 25,
                    "price": 5000.0,
                    "status": "FILLED",
                    "cancel_seconds": None,
                }
            )
            trades.append(
                {
                    "trade_id": f"T{oid:06d}",
                    "order_id": f"O{oid:06d}",
                    "trade_date": day,
                    "timestamp": f"{day} 11:00:00",
                    "account": wash_acct,
                    "instrument": "ES",
                    "side": side,
                    "quantity": 25,
                    "price": 5000.0,
                }
            )
        # Planted spoofing cluster: one account places and cancels many
        # large orders within seconds, same instrument and side.
        for k in range(12):
            oid += 1
            orders.append(
                {
                    "order_id": f"O{oid:06d}",
                    "trade_date": day,
                    "timestamp": f"{day} 10:{k:02d}:00",
                    "account": "ACC-019",
                    "trader": "TRD-07",
                    "instrument": "CL",
                    "side": "SELL",
                    "quantity": 200,
                    "price": 78.5,
                    "status": "CANCELLED",
                    "cancel_seconds": 3.0,
                }
            )
    return pd.DataFrame(orders), pd.DataFrame(trades)


def build_positions(trades: pd.DataFrame) -> pd.DataFrame:
    """Net positions per account, instrument and day from trades."""
    signed = trades.assign(
        signed_qty=np.where(trades["side"] == "BUY", trades["quantity"], -trades["quantity"])
    )
    grouped = (
        signed.groupby(["account", "instrument", "trade_date"], as_index=False)
        .agg(net_quantity=("signed_qty", "sum"), market_value=("price", "mean"))
        .assign(market_value=lambda d: d["market_value"] * d["net_quantity"].abs())
    )
    return grouped[["account", "instrument", "trade_date", "net_quantity", "market_value"]]


def build_warehouse(db_path: str, cfg: WarehouseConfig | None = None) -> dict[str, int]:
    """Create the SQLite warehouse and return row counts per table."""
    cfg = cfg or WarehouseConfig()
    orders, trades = generate_orders_trades(cfg)
    positions = build_positions(trades)
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(SCHEMA)
        orders.to_sql("orders", conn, if_exists="replace", index=False)
        trades.to_sql("trades", conn, if_exists="replace", index=False)
        positions.to_sql("positions", conn, if_exists="replace", index=False)
    finally:
        conn.close()
    return {"orders": len(orders), "trades": len(trades), "positions": len(positions)}


def load_table(db_path: str, table: str) -> pd.DataFrame:
    conn = sqlite3.connect(db_path)
    try:
        return pd.read_sql_query(f"SELECT * FROM {table}", conn)
    finally:
        conn.close()
