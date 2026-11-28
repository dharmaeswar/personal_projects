"""Bronze stage: schema enforcement, partitioning, quarantine."""
from __future__ import annotations

import pandas as pd
import pytest

from surveillance_lakehouse import ingest as ingest_mod


def test_ingest_schema_violation_raises(lakehouse):
    bad = lakehouse["feeds"]["orders"].drop(columns=["qty"])
    with pytest.raises(ValueError, match="schema"):
        ingest_mod.ingest("orders", bad, lakehouse["root"] / "bad_bronze")


def test_ingest_partitions_and_counts(lakehouse):
    report = lakehouse["bronze_report"]["orders"]
    assert report["rows_in"] == 2052
    assert report["rows_quarantined"] == 7  # 3 missing acct, 2 bad qty, 2 date
    assert report["rows_written"] == 2045
    assert report["quarantine_reasons"] == {
        "missing_account": 3, "bad_qty": 2, "date_mismatch": 2}
    assert len(report["partitions"]) == 5  # one per trade_date
    assert report["partitions"][0].startswith("trade_date=2026-11-16")


def test_ingest_trades_clean(lakehouse):
    report = lakehouse["bronze_report"]["trades"]
    assert report["rows_in"] == 1500
    assert report["rows_quarantined"] == 0
    assert report["rows_written"] == 1500


def test_read_bronze_round_trip(lakehouse):
    orders = ingest_mod.read_bronze("orders", lakehouse["bronze"])
    assert len(orders) == 2045
    assert set(orders["trade_date"].unique()) == {
        f"2026-11-{d}" for d in (16, 17, 18, 19, 20)}
