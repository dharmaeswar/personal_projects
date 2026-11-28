"""Gold stage: wash flags, reconciliation, CAT export, snapshots, tuning."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from surveillance_lakehouse import snapshots as snap


def test_gold_wash_pattern_flagged_every_day(lakehouse):
    feats = pd.read_parquet(lakehouse["gold"] / "account_day_features.parquet")
    flagged = feats[feats["wash_candidate"]]
    acc007 = flagged[flagged["account_id"] == "ACC-007"]
    assert len(acc007) == 5  # one per day, AAPL, 2000 bought = 2000 sold
    assert set(acc007["symbol"]) == {"AAPL"}
    assert (acc007["buy_qty"] == acc007["sell_qty"]).all()
    assert lakehouse["dq"]["wash_candidates"] >= 5


def test_gold_reconciliation_matches(lakehouse):
    rec = lakehouse["dq"]["reconciliation"]
    assert rec["matches"] is True
    assert rec["difference"] == 0.0


def test_gold_data_quality_clean(lakehouse):
    dq = lakehouse["dq"]
    assert all(v == 0 for v in dq["completeness"].values())
    assert all(v == 0 for v in dq["uniqueness"].values())


def test_cat_export_format(lakehouse):
    lines = (lakehouse["root"] / "cat_report.txt").read_text().splitlines()
    header = lines[0].split("|")
    assert header == ["event_date", "firm_order_id", "event_type", "symbol",
                      "side", "quantity", "price", "event_timestamp",
                      "account_id"]
    assert len(lines) - 1 == lakehouse["cat"]["rows"]
    assert lakehouse["cat"]["rows"] == lakehouse["dq"]["gold_rows"]["cat_events"]
    assert set(lakehouse["cat"]["event_types"]) <= {"MEOA", "MEOC"}
    for line in lines[1:]:
        fields = line.split("|")
        assert len(fields) == 9 and all(f != "" for f in fields)


def test_snapshots_chain_parents(lakehouse):
    entries = snap.read_snapshots(lakehouse["bronze"] / "orders")
    assert len(entries) == 1
    assert entries[0]["version"] == 1
    assert entries[0]["parent_snapshot_id"] is None
    assert entries[0]["rows_added"] == 2045
    # A second write chains to the first as its parent.
    second = snap.record_snapshot(lakehouse["bronze"] / "orders", "append", 10)
    assert second["version"] == 2
    assert second["parent_snapshot_id"] == entries[0]["snapshot_id"]


def test_tuning_report(lakehouse):
    result = lakehouse["tuning"]
    assert result["partitioned_rows"] == result["full_scan_rows"]
    assert result["partitioned_rows"] > 0
    assert result["total_rows"] == 1500
    report = (lakehouse["root"] / "tuning_report.md").read_text()
    assert "Partitioned scan" in report and "Full scan" in report
