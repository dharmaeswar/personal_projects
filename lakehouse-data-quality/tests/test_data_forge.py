"""Tests for the Data Forge extension: extraction, contracts, triage,
and Iceberg-style compaction. All data is synthetic."""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from lakehouse.compaction import (
    TableFile,
    expire_snapshots,
    partition_value,
    plan_compaction,
    table_health_summary,
)
from lakehouse.contracts import (
    DataContract,
    contract_is_compatible,
    detect_breaking_change,
    validate_contract,
)
from lakehouse.extract import (
    ShardCheckpoint,
    consume_shard,
    detect_schema_drift,
    extract_from_replica,
    ingest_lambda_events,
    plan_backfill,
)
from lakehouse.triage import Alert, TriageMemory, classify_alert

NOW = pd.Timestamp("2026-11-25 18:00", tz="UTC")


def _replica(n: int = 10) -> pd.DataFrame:
    base = pd.Timestamp("2026-11-25 08:00", tz="UTC")
    return pd.DataFrame(
        {
            "event_id": [f"evt-{i:03d}" for i in range(n)],
            "updated_at": [base + pd.Timedelta(minutes=10 * i) for i in range(n)],
            "value": range(n),
        }
    )


def _contract() -> DataContract:
    return DataContract(
        dataset="curated_listings",
        owner="data-forge",
        team="Data Forge",
        schema={"event_id": "object", "price": "float64"},
        freshness_sla_minutes=60,
        min_rows_per_day=2,
    )


# --- extraction -----------------------------------------------------

def test_replica_extract_reads_only_newer_rows():
    result = extract_from_replica(
        _replica(10), pd.Timestamp("2026-11-25 08:30", tz="UTC")
    )
    assert result.rows_read == 6
    assert result.new_watermark == pd.Timestamp("2026-11-25 09:30", tz="UTC")
    assert not result.truncated


def test_replica_extract_truncates_at_run_cap():
    result = extract_from_replica(_replica(10), None, max_rows_per_run=4)
    assert result.rows_read == 4
    assert result.truncated
    assert result.batches == 1


def test_replica_extract_empty_when_watermark_is_latest():
    result = extract_from_replica(
        _replica(5), pd.Timestamp("2026-11-25 09:00", tz="UTC")
    )
    assert result.rows_read == 0
    assert result.batches == 0


def test_kafka_consume_dedups_reprocessed_records():
    records = pd.DataFrame(
        {
            "event_id": ["a", "b", "c"],
            "sequence_number": [0, 1, 2],
        }
    )
    first = consume_shard(records, ShardCheckpoint(shard="s0"))
    assert len(first.new_records) == 3
    # A crashed consumer re-reads from a stale checkpoint: the offset
    # did not advance, but the ids were already processed. The re-read
    # must be a no-op, not a duplicate.
    stale = ShardCheckpoint(
        shard="s0", sequence_number=-1, processed_ids=set(first.checkpoint.processed_ids)
    )
    replay = consume_shard(records, stale)
    assert len(replay.new_records) == 0
    assert replay.duplicates_skipped == 3
    # A healthy re-consume after a committed checkpoint reads nothing.
    second = consume_shard(records, first.checkpoint)
    assert len(second.new_records) == 0
    assert second.duplicates_skipped == 0


def test_lambda_ingest_retries_only_failed_records():
    events = pd.DataFrame({"event_id": ["e1", "e2", "e3"]})
    result = ingest_lambda_events(events, fail_on={"e2"})
    assert list(result.committed["event_id"]) == ["e1", "e3"]
    assert list(result.failed["event_id"]) == ["e2"]
    assert len(result.failed_reasons) == 1


def test_schema_drift_detects_added_removed_and_changed():
    observed = pd.DataFrame({"a": [1], "b": ["x"], "c": [1.5]})
    drift = detect_schema_drift({"a": "int64", "b": "int64"}, observed)
    assert drift.added_columns == ["c"]
    assert drift.removed_columns == []
    assert len(drift.type_changes) == 1  # b: int64 -> object
    assert drift.has_drift


def test_backfill_plan_chunks_evenly():
    windows = plan_backfill(date(2026, 11, 18), date(2026, 11, 24), chunk_days=7)
    assert windows == [
        (date(2026, 11, 18), date(2026, 11, 24)),
    ]
    windows = plan_backfill(date(2026, 11, 1), date(2026, 11, 20), chunk_days=7)
    assert len(windows) == 3
    assert windows[0] == (date(2026, 11, 1), date(2026, 11, 7))
    assert windows[-1] == (date(2026, 11, 15), date(2026, 11, 20))


def test_backfill_plan_rejects_reversed_range():
    with pytest.raises(ValueError):
        plan_backfill(date(2026, 11, 24), date(2026, 11, 18))


# --- contracts ------------------------------------------------------

def test_contract_passes_on_clean_table():
    df = pd.DataFrame(
        {"event_id": ["e1", "e2"], "price": [10.0, 20.0]}
    )
    violations = validate_contract(
        _contract(), df, pd.Timestamp("2026-11-25 17:30", tz="UTC"), NOW
    )
    assert violations == []


def test_contract_flags_missing_column_type_and_freshness():
    df = pd.DataFrame({"event_id": ["e1"], "price": ["10"]})
    violations = validate_contract(
        _contract(), df, pd.Timestamp("2026-11-25 10:00", tz="UTC"), NOW
    )
    rules = {v.rule for v in violations}
    assert "schema.type_mismatch" in rules
    assert "volume.min_rows" in rules
    assert "freshness.sla_breach" in rules


def test_breaking_change_removal_and_type_change():
    changes = detect_breaking_change(
        {"a": "int64", "b": "string"}, {"a": "float64", "c": "string?"}
    )
    breaking = [c.change for c in changes if c.breaking]
    assert any("removed column 'b'" in c for c in breaking)
    assert any("type of 'a'" in c for c in breaking)
    assert not contract_is_compatible(changes)


def test_breaking_change_nullable_add_is_safe():
    changes = detect_breaking_change({"a": "int64"}, {"a": "int64", "b": "string?"})
    assert contract_is_compatible(changes)
    assert all(not c.breaking for c in changes)


# --- triage ---------------------------------------------------------

def _alert(**overrides) -> Alert:
    payload = {
        "alert_id": "AL-1",
        "source": "freshness-monitor",
        "message": "dataset is stale",
        "metric": "latest_event_age_minutes",
        "observed": 95.0,
        "threshold": 60.0,
        "timestamp": NOW,
        "dataset": "curated_listings",
    }
    payload.update(overrides)
    return Alert(**payload)


def test_triage_classifies_freshness_and_suggests_steps():
    result = classify_alert(_alert())
    assert result.category == "freshness breach"
    assert result.severity == "p3"
    assert result.suggested_steps


def test_triage_escalates_to_p2_when_twice_threshold():
    result = classify_alert(_alert(observed=130.0))
    assert result.severity == "p2"


def test_triage_learns_from_past_resolution():
    memory = TriageMemory()
    alert = _alert()
    memory.record_resolution(
        alert, "replica stalled", "restart extractor from watermark"
    )
    result = classify_alert(_alert(), memory)
    assert result.learned
    assert result.likely_cause == "replica stalled"
    assert "restart extractor from watermark" in result.suggested_steps[0]


def test_triage_unknown_category_routes_to_owner():
    result = classify_alert(
        _alert(source="mystery-monitor", metric="weird_gauge", message="huh?")
    )
    assert result.category == "unknown"


# --- compaction -----------------------------------------------------

def test_partition_value_day_and_bucket():
    assert partition_value("day", "2026-11-25 08:00") == "2026-11-25"
    assert partition_value("identity", "us-west") == "us-west"
    bucket = partition_value("bucket[16]", "listing-123")
    assert 0 <= int(bucket) < 16
    with pytest.raises(ValueError):
        partition_value("week", "2026-11-25")


def test_compaction_skips_when_too_few_small_files():
    files = [TableFile(f"f{i}.parquet", 10, 1024, "2026-11-25") for i in range(2)]
    plan = plan_compaction(files)
    assert plan.strategy == "none"
    assert plan.files_to_compact == []


def test_compaction_merge_on_read_for_small_files():
    files = [
        TableFile(f"f{i}.parquet", 1000, 2 * 1024 * 1024, "2026-11-25")
        for i in range(9)
    ]
    plan = plan_compaction(files)
    assert plan.strategy == "merge-on-read"
    assert len(plan.files_to_compact) == 9
    assert plan.estimated_new_files >= 1


def test_snapshot_expiry_keeps_newest():
    snapshots = [{"snapshot_id": i} for i in range(1, 8)]
    kept, expired = expire_snapshots(snapshots, retain=5)
    assert [s["snapshot_id"] for s in kept] == [3, 4, 5, 6, 7]
    assert len(expired) == 2


def test_table_health_summary_counts_small_files():
    files = [
        TableFile("a.parquet", 10, 1024, "2026-11-25"),
        TableFile("b.parquet", 10, 100 * 1024 * 1024, "2026-11-25"),
    ]
    summary = table_health_summary(files)
    assert summary["files"] == 2
    assert summary["small_files"] == 1
    assert summary["small_file_share"] == 0.5
