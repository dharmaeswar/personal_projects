"""Tests for the SQL query-tuning module."""

import sqlite3

import pytest

from trade_reg_analytics.data import WarehouseConfig, build_warehouse
from trade_reg_analytics.tuning import (
    ANALYTICS_QUERIES,
    RECOMMENDED_INDEXES,
    apply_indexes,
    existing_indexes,
    explain_plan,
    plan_summary,
    run_tuning,
    time_query,
    tune_query,
    uses_full_scan,
)


@pytest.fixture()
def warehouse(tmp_path):
    db = tmp_path / "warehouse.db"
    build_warehouse(str(db), WarehouseConfig(seed=42, days=5))
    conn = sqlite3.connect(str(db))
    yield conn
    conn.close()


def test_recommended_indexes_cover_each_table():
    ddls = " ".join(ddl for _, ddl in RECOMMENDED_INDEXES)
    assert "ON orders" in ddls
    assert "ON trades" in ddls
    assert "ON positions" in ddls
    names = [name for name, _ in RECOMMENDED_INDEXES]
    assert len(names) == len(set(names))


def test_apply_indexes_is_idempotent(warehouse):
    created_first = apply_indexes(warehouse)
    assert len(created_first) == len(RECOMMENDED_INDEXES)
    assert set(created_first) == {name for name, _ in RECOMMENDED_INDEXES}
    assert apply_indexes(warehouse) == []
    assert {name for name, _ in RECOMMENDED_INDEXES} <= existing_indexes(warehouse)


def test_explain_plan_returns_details(warehouse):
    spec = ANALYTICS_QUERIES["account_volume_share"]
    plan = explain_plan(warehouse, spec["sql"], spec["params"])
    assert plan
    assert all("detail" in step for step in plan)
    assert plan_summary(plan)


def test_account_query_scans_before_and_seeks_after(warehouse):
    spec = ANALYTICS_QUERIES["account_volume_share"]
    plan_before = explain_plan(warehouse, spec["sql"], spec["params"])
    assert uses_full_scan(plan_before), "expected a full scan before indexing"
    apply_indexes(warehouse)
    plan_after = explain_plan(warehouse, spec["sql"], spec["params"])
    assert not uses_full_scan(plan_after), "expected an index seek after indexing"
    assert "USING INDEX" in plan_summary(plan_after) or "USING COVERING INDEX" in plan_summary(
        plan_after
    )


def test_time_query_returns_positive_median(warehouse):
    spec = ANALYTICS_QUERIES["daily_volume_by_instrument"]
    ms = time_query(warehouse, spec["sql"], spec["params"], repeats=3)
    assert ms > 0


def test_tune_query_reports_before_and_after(warehouse):
    spec = ANALYTICS_QUERIES["position_concentration"]
    result = tune_query(warehouse, "position_concentration", spec)
    assert result["name"] == "position_concentration"
    assert result["median_ms_before"] > 0
    assert result["median_ms_after"] > 0
    assert result["speedup"] is not None
    assert result["plan_before"]
    assert result["plan_after"]
    # The indexed plan must not be worse than the unindexed plan.
    assert not result["full_scan_after"]


def test_run_tuning_writes_report_files(warehouse, tmp_path):
    out = tmp_path / "tuning"
    summary = run_tuning(warehouse, out)
    assert summary["queries_tuned"] == len(ANALYTICS_QUERIES)
    assert summary["full_scans_removed"] >= 1
    assert (out / "tuning_report.md").exists()
    assert (out / "tuning_summary.json").exists()
    report = (out / "tuning_report.md").read_text(encoding="utf-8")
    for name in ANALYTICS_QUERIES:
        assert name in report
    assert "Speedup" in report


def test_every_analytics_query_runs(warehouse):
    for name, spec in ANALYTICS_QUERIES.items():
        rows = warehouse.execute(spec["sql"], spec["params"]).fetchall()
        assert isinstance(rows, list), name
