"""Tests for the PySpark-style batch pipeline.

Every count below is deterministic (seeded data): 240 raw rows, 4 duplicates,
14 invalid rows, 222 cleansed rows.
"""
from pathlib import Path

import pandas as pd
import pytest

from spark_pipeline.checks import run_quality_checks
from spark_pipeline.data import ALLOWED_END, ALLOWED_START, generate_raw
from spark_pipeline.pipeline import run_pipeline
from spark_pipeline.schema import check_schema, enforce_schema
from spark_pipeline.transforms import (
    aggregate_daily,
    dedupe_latest,
    filter_valid,
    join_product_dim,
    reconcile,
    with_derived_columns,
)


def test_raw_has_240_rows_with_18_planted_defects():
    raw = generate_raw()
    assert len(raw) == 240
    assert raw["event_id"].duplicated().sum() == 4


def test_dedup_keeps_latest_ingested_copy():
    raw = generate_raw()
    deduped, n_dup = dedupe_latest(raw)
    assert n_dup == 4
    assert len(deduped) == 236
    assert deduped["event_id"].is_unique
    assert deduped.loc[deduped["event_id"] == "EVT-000001", "ingested_at"].iloc[0] == "2026-11-17T09:00:00"


def test_filter_quarantines_14_invalid_rows_by_rule():
    raw = generate_raw()
    deduped, _ = dedupe_latest(raw)
    valid, invalid = filter_valid(deduped)
    assert len(valid) == 222
    assert len(invalid) == 14
    primary = invalid["violation"].str.split("+", regex=False).str[0].value_counts().to_dict()
    assert primary == {
        "null_user_id": 5,
        "negative_amount": 3,
        "unknown_product": 3,
        "date_out_of_range": 2,
        "amount_mismatch": 1,
    }


def test_valid_rows_pass_all_quality_rules():
    raw = generate_raw()
    deduped, _ = dedupe_latest(raw)
    valid, _ = filter_valid(deduped)
    assert valid["user_id"].notna().all()
    assert (valid["amount"] >= 0).all()
    assert ((valid["amount"] - valid["quantity"] * valid["unit_price"]).abs() <= 0.01).all()
    assert valid["event_date"].between(ALLOWED_START, ALLOWED_END).all()


def test_schema_enforced_on_cleansed_not_on_raw():
    raw = generate_raw()
    assert check_schema(raw, allow_nulls=True) == []
    deduped, _ = dedupe_latest(raw)
    valid, _ = filter_valid(deduped)
    cleansed = with_derived_columns(join_product_dim(valid))
    base = cleansed.drop(columns=["product_category", "amount_band", "is_high_value"])
    assert check_schema(base) == []
    enforce_schema(base)
    with pytest.raises(ValueError):
        enforce_schema(raw)  # nulls + bad values: raw must not pass strict checks


def test_derived_columns_match_spark_withcolumn_semantics():
    raw = generate_raw()
    deduped, _ = dedupe_latest(raw)
    valid, _ = filter_valid(deduped)
    out = with_derived_columns(valid)
    assert set(out["amount_band"].unique()) <= {"low", "medium", "high"}
    assert out.loc[out["amount"] >= 100, "is_high_value"].all()
    assert not out.loc[out["amount"] < 100, "is_high_value"].any()


def test_broadcast_join_adds_category_and_no_unknowns_remain():
    raw = generate_raw()
    deduped, _ = dedupe_latest(raw)
    valid, _ = filter_valid(deduped)
    joined = join_product_dim(valid)
    assert joined["product_category"].notna().all()
    assert set(joined["product_category"].unique()) == {"Electronics", "Apparel", "Home", "Sports"}


def test_gold_aggregates_reconcile_to_cleansed():
    raw = generate_raw()
    deduped, _ = dedupe_latest(raw)
    valid, _ = filter_valid(deduped)
    cleansed = with_derived_columns(join_product_dim(valid))
    gold = aggregate_daily(cleansed)
    assert gold["total_revenue"].sum() == pytest.approx(cleansed["amount"].sum(), abs=0.01)
    result = reconcile(cleansed, gold)
    assert result["passed"] is True
    assert result["max_revenue_diff"] == 0.0
    assert result["gold_rows"] == len(gold)


def test_full_pipeline_end_to_end(tmp_path):
    summary, checks, invalid = run_pipeline(tmp_path)
    assert summary == {
        "raw_rows": 240,
        "duplicates_removed": 4,
        "quarantined_rows": 14,
        "cleansed_rows": 222,
        "gold_rows": 48,
        "partitions": 48,
        "violation_counts": {
            "null_user_id": 5,
            "negative_amount": 3,
            "unknown_product": 3,
            "date_out_of_range": 2,
            "amount_mismatch": 1,
        },
        "checks_passed": 7,
        "checks_total": 7,
        "reconciliation_passed": True,
        "total_revenue": summary["total_revenue"],
    }
    assert all(status == "PASS" for _, status, _ in checks)
    assert len(invalid) == 14
    tables = tmp_path / "pipeline_tables"
    assert (tables / "raw.parquet").exists()
    assert (tables / "cleansed.parquet").exists()
    assert (tables / "quarantine.parquet").exists()
    assert (tables / "gold.parquet").exists()
    assert len(list((tables / "curated").glob("event_date=*"))) == 48
    gold = pd.read_parquet(tables / "gold.parquet")
    assert gold["total_revenue"].sum() == pytest.approx(summary["total_revenue"], abs=0.01)


def test_partitioned_curated_matches_cleansed(tmp_path):
    summary, _, _ = run_pipeline(tmp_path)
    tables = tmp_path / "pipeline_tables"
    curated = pd.read_parquet(tables / "curated")
    cleansed = pd.read_parquet(tables / "cleansed.parquet")
    assert len(curated) == len(cleansed) == 222
    assert curated["amount"].sum() == pytest.approx(cleansed["amount"].sum(), abs=0.01)
