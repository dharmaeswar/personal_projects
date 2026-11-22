import sqlite3

import pandas as pd
import pytest

from trade_reg_analytics.data import WarehouseConfig, build_positions, build_warehouse, generate_orders_trades, load_table


@pytest.fixture(scope="module")
def db(tmp_path_factory):
    path = str(tmp_path_factory.mktemp("wh") / "warehouse.db")
    counts = build_warehouse(path, WarehouseConfig(seed=42, days=5))
    return path, counts


def test_warehouse_counts(db):
    _, counts = db
    assert counts["orders"] > counts["trades"] > 0
    assert counts["positions"] > 0
    assert counts["trades"] > 1000


def test_warehouse_tables_exist(db):
    path, _ = db
    conn = sqlite3.connect(path)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    assert {"orders", "trades", "positions"} <= tables


def test_generation_is_deterministic():
    o1, t1 = generate_orders_trades(WarehouseConfig(seed=7, days=3))
    o2, t2 = generate_orders_trades(WarehouseConfig(seed=7, days=3))
    pd.testing.assert_frame_equal(o1, o2)
    pd.testing.assert_frame_equal(t1, t2)


def test_positions_net_from_trades():
    trades = pd.DataFrame(
        {
            "trade_id": ["T1", "T2", "T3"],
            "account": ["A", "A", "A"],
            "instrument": ["ES", "ES", "ES"],
            "trade_date": ["2026-01-05"] * 3,
            "side": ["BUY", "BUY", "SELL"],
            "quantity": [10, 5, 4],
            "price": [100.0, 101.0, 102.0],
        }
    )
    pos = build_positions(trades)
    assert len(pos) == 1
    assert pos.iloc[0]["net_quantity"] == 11


def test_load_table_roundtrip(db):
    path, counts = db
    orders = load_table(path, "orders")
    assert len(orders) == counts["orders"]
    assert set(orders.columns) >= {"order_id", "account", "instrument", "status"}
