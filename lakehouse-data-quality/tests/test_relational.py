"""Tests for the PostgreSQL/Aurora-style relational layer and query tuning."""

from __future__ import annotations

import pandas as pd
import pytest

from lakehouse.pipeline import build_gold, build_silver
from lakehouse.data import generate_customers, generate_orders, generate_products
from lakehouse.relational import (
    ForeignKey,
    RelationalStore,
    aurora_mysql_ddl,
    postgres_ddl,
    table_def_from_frame,
    tune_query,
)


def _gold_frame():
    silver, _ = build_silver(generate_orders(seed=11), generate_customers(), generate_products())
    return build_gold(silver, generate_products())


def test_table_def_from_frame_infers_columns():
    df = pd.DataFrame({"order_id": ["O1"], "total_revenue": [10.5]})
    table = table_def_from_frame("fact_x", df, primary_key=["order_id"])
    assert [c.name for c in table.columns] == ["order_id", "total_revenue"]
    assert table.primary_key == ["order_id"]


def test_postgres_ddl_has_keys_and_index():
    df = pd.DataFrame({"order_id": ["O1"], "customer_id": ["C1"]})
    table = table_def_from_frame(
        "orders",
        df,
        primary_key=["order_id"],
        foreign_keys=[ForeignKey("customer_id", "customers", "customer_id")],
        indexes=[["customer_id"]],
    )
    ddl = postgres_ddl(table)
    assert "CREATE TABLE orders" in ddl
    assert "PRIMARY KEY (order_id)" in ddl
    assert "FOREIGN KEY (customer_id) REFERENCES customers (customer_id)" in ddl
    assert "CREATE INDEX idx_orders_customer_id ON orders (customer_id);" in ddl
    assert "DOUBLE PRECISION" not in ddl  # no float columns in this frame


def test_aurora_mysql_ddl_uses_innodb_and_varchar():
    df = pd.DataFrame({"order_id": ["O1"], "total_revenue": [10.5]})
    table = table_def_from_frame("fact_x", df, primary_key=["order_id"])
    ddl = aurora_mysql_ddl(table)
    assert "ENGINE=InnoDB" in ddl
    assert "VARCHAR(255)" in ddl
    assert "DOUBLE" in ddl


def test_store_loads_and_counts_rows(tmp_path):
    gold = _gold_frame()
    store = RelationalStore(tmp_path / "test.db")
    try:
        table = table_def_from_frame(
            "fact_daily_revenue", gold, primary_key=["order_date", "category", "region"]
        )
        loaded = store.load_table(table, gold)
        assert loaded == len(gold)
        assert store.row_count("fact_daily_revenue") == len(gold)
    finally:
        store.close()


def test_store_rejects_orphan_foreign_key(tmp_path):
    gold = _gold_frame()
    store = RelationalStore(tmp_path / "test.db")
    try:
        table = table_def_from_frame(
            "fact_daily_revenue",
            gold,
            primary_key=["order_date", "category", "region"],
            foreign_keys=[ForeignKey("region", "dim_region", "region")],
        )
        with pytest.raises(Exception):
            store.load_table(table, gold)
    finally:
        store.close()


def test_tune_query_turns_scan_into_index_search(tmp_path):
    gold = _gold_frame()
    store = RelationalStore(tmp_path / "test.db")
    try:
        table = table_def_from_frame(
            "fact_daily_revenue", gold, primary_key=["order_date", "category", "region"]
        )
        store.load_table(table, gold)
        sql = (
            "SELECT order_date, SUM(total_revenue) FROM fact_daily_revenue "
            "WHERE region = ? GROUP BY order_date ORDER BY order_date"
        )
        report = tune_query(store, sql, ("Midwest",), "fact_daily_revenue", ["region", "order_date"])
        assert report.scanned_before, report.plan_before
        assert report.uses_index_after, report.plan_after
        assert report.rows > 0
        assert report.index_name == "idx_fact_daily_revenue_region_order_date"
    finally:
        store.close()


def test_explain_returns_plan_lines(tmp_path):
    store = RelationalStore(tmp_path / "test.db")
    try:
        store.conn.execute("CREATE TABLE t (a TEXT, b INTEGER)")
        store.conn.execute("INSERT INTO t VALUES ('x', 1)")
        plan = store.explain("SELECT * FROM t WHERE a = ?", ("x",))
        assert plan, "plan should have at least one line"
        assert any("SCAN" in line for line in plan)
    finally:
        store.close()
