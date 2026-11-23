"""Tests for the battery-telemetry module (lakehouse.battery)."""

import pandas as pd
import pytest

from lakehouse.battery import (
    BATTERY_TELEMETRY_SCHEMA,
    GOLD_BATTERY_SCHEMA,
    build_battery_gold,
    build_battery_silver,
    check_battery_reconciliation,
    check_sample_gaps,
    check_telemetry_completeness,
    check_telemetry_ranges,
    check_telemetry_uniqueness,
    check_timestamp_monotonic,
    generate_clean_telemetry,
    generate_telemetry,
    run_battery_checks,
    run_battery_telemetry,
)
from lakehouse.schema import enforce_schema

N_CELLS = 6 * 4
N_SAMPLES = 288
DROPPED = 4  # 3 in B002-C2, 1 in B004-C1
DUPLICATES = 3


def test_generated_telemetry_shape_and_columns():
    telemetry = generate_telemetry()
    assert len(telemetry) == N_CELLS * N_SAMPLES - DROPPED + DUPLICATES  # 6911
    assert list(telemetry.columns) == BATTERY_TELEMETRY_SCHEMA.column_names()
    assert telemetry["battery_id"].nunique() == 6
    assert telemetry["cell_id"].nunique() == 24
    assert set(telemetry["test_lab"]) == {"Boston", "Irvine", "Sunnyvale", "Seattle"}


def test_generation_is_deterministic():
    first = generate_telemetry()
    second = generate_telemetry()
    pd.testing.assert_frame_equal(first, second)


def test_clean_telemetry_passes_schema_and_checks():
    clean = generate_clean_telemetry()
    assert enforce_schema(clean, BATTERY_TELEMETRY_SCHEMA) == []
    assert check_telemetry_completeness(clean).passed
    assert check_telemetry_uniqueness(clean).passed
    assert all(r.passed for r in check_telemetry_ranges(clean))
    assert check_timestamp_monotonic(clean).passed


def test_clean_telemetry_still_has_the_dropped_sample_gaps():
    clean = generate_clean_telemetry()
    result = check_sample_gaps(clean)
    assert not result.passed
    assert result.detail == "2 gaps, 4 samples missing from the feed"


def test_uniqueness_flags_the_three_duplicate_samples():
    result = check_telemetry_uniqueness(generate_telemetry())
    assert not result.passed
    assert len(result.failing_rows) == 3
    assert result.detail == "3 duplicate (cell_id, timestamp) samples"


def test_completeness_flags_the_four_null_temperatures():
    result = check_telemetry_completeness(generate_telemetry())
    assert not result.passed
    assert result.detail == "temperature_c: 4 nulls"
    assert len(result.failing_rows) == 4


def test_ranges_flag_each_out_of_range_reading():
    results = {r.name: r for r in check_telemetry_ranges(generate_telemetry())}
    assert not results["telemetry range:voltage_v"].passed
    assert len(results["telemetry range:voltage_v"].failing_rows) == 2
    assert results["telemetry range:current_a"].passed
    assert not results["telemetry range:temperature_c"].passed
    assert len(results["telemetry range:temperature_c"].failing_rows) == 2
    assert not results["telemetry range:state_of_charge"].passed
    assert len(results["telemetry range:state_of_charge"].failing_rows) == 1


def test_monotonic_flags_only_the_late_sample():
    telemetry = generate_telemetry()
    deduped = telemetry.drop_duplicates(
        subset=["cell_id", "timestamp"], keep="first"
    )
    result = check_timestamp_monotonic(deduped)
    assert not result.passed
    assert len(result.failing_rows) == 1
    assert result.detail == "1 samples out of time order"


def test_full_check_suite_counts():
    results = run_battery_checks(generate_telemetry())
    assert len(results) == 8  # completeness, uniqueness, 4 ranges, monotonic, gaps
    assert sum(1 for r in results if not r.passed) == 7
    assert results[-1].name == "telemetry sample gaps"
    assert not results[-1].passed


def test_silver_and_quarantine_counts():
    silver, quarantine = build_battery_silver(generate_telemetry())
    assert len(quarantine) == 13  # 3 dup + 4 null + 5 out of range + 1 late
    assert len(silver) == 6911 - 13  # 6898
    assert enforce_schema(silver, BATTERY_TELEMETRY_SCHEMA) == []
    assert set(quarantine["quarantine_reason"].str.split("; ").explode()) == {
        "duplicate sample",
        "null reading",
        "voltage_v out of range",
        "temperature_c out of range",
        "state_of_charge out of range",
        "out of time order",
    }


def test_gold_groups_and_reconciliation():
    silver, _ = build_battery_silver(generate_telemetry())
    gold = build_battery_gold(silver)
    assert len(gold) == 12  # 6 batteries x 2 days
    assert enforce_schema(gold, GOLD_BATTERY_SCHEMA) == []
    assert int(gold["sample_count"].sum()) == len(silver)
    assert check_battery_reconciliation(silver, gold).passed


def test_run_writes_tables_logs_and_summary(tmp_path):
    summary = run_battery_telemetry(tmp_path)
    assert summary["bronze_rows"] == 6911
    assert summary["silver_rows"] == 6898
    assert summary["quarantine_rows"] == 13
    assert summary["gold_groups"] == 12
    assert summary["checks_failed"] == 7
    assert summary["reconciliation"].passed
    assert summary["silver_schema_violations"] == []
    assert summary["gold_schema_violations"] == []
    assert summary["log_versions"] == {
        "bronze": 1,
        "silver": 1,
        "quarantine": 1,
        "gold": 1,
    }
    for table in (
        "bronze/battery_telemetry",
        "silver/battery_telemetry",
        "silver/quarantine",
        "gold/daily_battery_summary",
    ):
        assert (tmp_path / table / "data.parquet").exists()
        assert (tmp_path / table / "_delta_log.json").exists()


def test_run_is_repeatable_in_counts(tmp_path):
    first = run_battery_telemetry(tmp_path)
    second = run_battery_telemetry(tmp_path)
    assert first["bronze_rows"] == second["bronze_rows"] == 6911
    assert first["silver_rows"] == second["silver_rows"] == 6898
    assert first["gold_groups"] == second["gold_groups"] == 12
    assert first["reconciliation"].passed and second["reconciliation"].passed
