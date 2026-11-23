"""Tests for the risk-technology ETL and the agentic quality triage.

Every count below is deterministic (seeded data): 165 raw rows, 3 duplicates,
12 invalid rows, 150 cleansed rows.
"""
from pathlib import Path

import pandas as pd
import pytest

from spark_pipeline.agentic_quality import auto_fix_exposure, triage_quarantine, triage_summary
from spark_pipeline.risk_data import INSTRUMENT_FACTOR, generate_risk_raw
from spark_pipeline.risk_pipeline import run_risk_pipeline
from spark_pipeline.risk_transforms import (
    aggregate_risk_daily,
    dedupe_latest_risk,
    filter_valid_risk,
    join_book_dim,
    reconcile_risk,
    with_derived_risk_columns,
)


def test_raw_has_165_rows_with_15_planted_defects():
    raw = generate_risk_raw()
    assert len(raw) == 165
    assert raw["trade_id"].duplicated().sum() == 3
    assert raw["counterparty"].isna().sum() == 4
    assert (raw["notional"] < 0).sum() == 3


def test_dedup_keeps_latest_ingested_copy():
    raw = generate_risk_raw()
    deduped, n_dup = dedupe_latest_risk(raw)
    assert n_dup == 3
    assert len(deduped) == 162
    assert deduped["trade_id"].is_unique
    assert deduped.loc[deduped["trade_id"] == "TRD-000001", "ingested_at"].iloc[0] == "2026-11-17T09:00:00"


def test_filter_quarantines_12_invalid_rows_by_rule():
    raw = generate_risk_raw()
    deduped, _ = dedupe_latest_risk(raw)
    valid, invalid = filter_valid_risk(deduped)
    assert len(invalid) == 12
    assert len(valid) == 150
    counts = invalid["violation"].str.split("+", regex=False).str[0].value_counts().to_dict()
    assert counts == {
        "null_counterparty": 4,
        "negative_notional": 3,
        "unknown_book": 2,
        "date_out_of_range": 2,
        "exposure_mismatch": 1,
    }


def test_cleansed_exposure_equals_notional_times_factor():
    raw = generate_risk_raw()
    deduped, _ = dedupe_latest_risk(raw)
    valid, _ = filter_valid_risk(deduped)
    expected = valid["notional"] * valid["instrument_type"].map(INSTRUMENT_FACTOR)
    assert ((valid["exposure"] - expected).abs() <= 0.01).all()


def test_join_book_dim_adds_desk_for_known_books():
    raw = generate_risk_raw()
    deduped, _ = dedupe_latest_risk(raw)
    valid, _ = filter_valid_risk(deduped)
    joined = join_book_dim(valid)
    assert joined["desk"].notna().all()
    assert set(joined["desk"].unique()) == {
        "Rates Trading", "Credit Trading", "FX Trading", "Equity Derivatives",
    }


def test_derived_columns_flag_high_exposure():
    raw = generate_risk_raw()
    deduped, _ = dedupe_latest_risk(raw)
    valid, _ = filter_valid_risk(deduped)
    derived = with_derived_risk_columns(valid)
    assert set(derived["exposure_band"].unique()) <= {"low", "medium", "high"}
    assert (derived["is_high_exposure"] == (derived["exposure"] >= 500_000)).all()


def test_gold_reconciles_to_cleansed():
    raw = generate_risk_raw()
    deduped, _ = dedupe_latest_risk(raw)
    valid, _ = filter_valid_risk(deduped)
    cleansed = with_derived_risk_columns(join_book_dim(valid))
    gold = aggregate_risk_daily(cleansed)
    result = reconcile_risk(cleansed, gold)
    assert result["passed"]
    assert result["max_exposure_diff"] <= 0.01
    assert gold["total_exposure"].sum() == pytest.approx(cleansed["exposure"].sum(), abs=0.01)


def test_auto_fix_recomputes_mismatched_exposure():
    raw = generate_risk_raw()
    bad = raw[raw["trade_id"] == "TRD-BAD-E1"].iloc[0]
    fixed = auto_fix_exposure(bad)
    assert fixed == pytest.approx(float(bad["notional"]) * INSTRUMENT_FACTOR[bad["instrument_type"]], abs=0.01)
    assert fixed != bad["exposure"]


def test_triage_dispositions_match_policy():
    raw = generate_risk_raw()
    deduped, _ = dedupe_latest_risk(raw)
    _, invalid = filter_valid_risk(deduped)
    findings = triage_quarantine(invalid)
    assert len(findings) == 12
    by_trade = {f["trade_id"]: f for f in findings}
    assert by_trade["TRD-BAD-E1"]["disposition"] == "AUTO_FIX"
    assert by_trade["TRD-BAD-E1"]["corrected_exposure"] is not None
    for i in range(1, 5):
        assert by_trade[f"TRD-BAD-C{i}"]["disposition"] == "ESCALATE"
    for i in range(1, 4):
        assert by_trade[f"TRD-BAD-N{i}"]["disposition"] == "ESCALATE"
    for i in range(1, 3):
        assert by_trade[f"TRD-BAD-B{i}"]["disposition"] == "ESCALATE"
        assert by_trade[f"TRD-BAD-D{i}"]["disposition"] == "DROP"


def test_triage_summary_counts():
    raw = generate_risk_raw()
    deduped, _ = dedupe_latest_risk(raw)
    _, invalid = filter_valid_risk(deduped)
    summary = triage_summary(triage_quarantine(invalid))
    assert summary == {"AUTO_FIX": 1, "ESCALATE": 9, "DROP": 2}


def test_full_risk_pipeline_end_to_end(tmp_path):
    summary, findings, invalid = run_risk_pipeline(tmp_path)
    assert summary == {
        "raw_rows": 165,
        "duplicates_removed": 3,
        "quarantined_rows": 12,
        "cleansed_rows": 150,
        "gold_rows": summary["gold_rows"],
        "partitions": summary["partitions"],
        "total_notional": summary["total_notional"],
        "total_exposure": summary["total_exposure"],
        "reconciliation_passed": True,
        "violation_counts": {
            "null_counterparty": 4,
            "negative_notional": 3,
            "unknown_book": 2,
            "date_out_of_range": 2,
            "exposure_mismatch": 1,
        },
        "triage": {"AUTO_FIX": 1, "ESCALATE": 9, "DROP": 2},
    }
    assert len(findings) == 12
    assert len(invalid) == 12
    tables = tmp_path / "risk_tables"
    assert (tables / "raw.parquet").exists()
    assert (tables / "cleansed.parquet").exists()
    assert (tables / "quarantine.parquet").exists()
    assert (tables / "gold.parquet").exists()
    assert len(list((tables / "curated").glob("trade_date=*"))) == 48
    gold = pd.read_parquet(tables / "gold.parquet")
    assert gold["total_exposure"].sum() == pytest.approx(summary["total_exposure"], abs=0.01)
