"""Silver stage: dedupe, dimensions, referential integrity."""
from __future__ import annotations

import pandas as pd


def test_silver_dedupe_keeps_latest(lakehouse):
    report = lakehouse["silver_report"]
    assert report["duplicates_removed"]["orders"] == 5
    assert report["duplicates_removed"]["executions"] == 2
    assert report["duplicates_removed"]["trades"] == 0
    orders = pd.read_parquet(lakehouse["silver"] / "fact_order.parquet")
    assert len(orders) == 2040
    assert orders["order_id"].is_unique


def test_silver_dimensions(lakehouse):
    instruments = pd.read_parquet(lakehouse["silver"] / "dim_instrument.parquet")
    accounts = pd.read_parquet(lakehouse["silver"] / "dim_account.parquet")
    assert len(instruments) == 6
    assert len(accounts) == 10
    assert instruments["symbol"].is_unique
    assert accounts["account_id"].is_unique


def test_silver_referential_integrity(lakehouse):
    checks = lakehouse["silver_report"]["referential_integrity_violations"]
    assert all(v == 0 for v in checks.values()), checks


def test_silver_late_arrivals_counted(lakehouse):
    report = lakehouse["silver_report"]
    assert report["late_arrivals"]["executions"] == 2
    assert report["late_arrivals"]["orders"] == 0
