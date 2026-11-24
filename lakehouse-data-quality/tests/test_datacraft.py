"""Tests for the DataCraft-style streaming ingestion module."""

import pandas as pd
import pytest

from lakehouse.datacraft import (
    SOURCES,
    build_catalog,
    generate_pipeline_registry,
    generate_source_events,
    ingest_source,
    monitor_pipelines,
    route_to_sinks,
    run_datacraft,
    search_catalog,
)


def test_registry_covers_all_sources_and_sinks():
    reg = generate_pipeline_registry()
    assert len(reg) == 60
    assert set(reg["source"]) == set(SOURCES)
    assert set(reg["sink"]) <= {"S3", "Andes", "EDX"}
    assert reg["pipeline_id"].is_unique
    assert set(reg["micro_batch_minutes"]) <= {1, 5, 15}


def test_registry_deterministic():
    pd.testing.assert_frame_equal(generate_pipeline_registry(), generate_pipeline_registry())


def test_source_events_shape_and_planted_cases():
    for source in SOURCES:
        stream = generate_source_events(source)
        assert len(stream) == 125  # 120 base + 3 dupes + 2 late
        assert stream["source"].eq(source).all()
        assert stream["event_id"].duplicated().sum() == 3


def test_source_events_deterministic():
    for source in SOURCES:
        pd.testing.assert_frame_equal(generate_source_events(source), generate_source_events(source))


def test_ingest_exactly_once_per_source():
    for source in SOURCES:
        result = ingest_source(source)
        assert result["total_arrived"] == 125
        assert len(result["accepted"]) == 120
        assert len(result["duplicates"]) == 3
        assert len(result["late"]) == 2
        assert result["accepted"]["event_id"].is_unique


def test_ingest_replay_is_noop():
    from lakehouse.streaming import StreamCheckpoint, process_micro_batch, split_micro_batches

    stream = generate_source_events("orders")
    checkpoint = StreamCheckpoint()
    for batch in split_micro_batches(stream):
        _, _, _, checkpoint = process_micro_batch(batch, checkpoint)
    # Re-processing the same stream from the saved checkpoint accepts nothing.
    accepted_total = 0
    for batch in split_micro_batches(stream):
        accepted, _, _, checkpoint = process_micro_batch(batch, checkpoint)
        accepted_total += len(accepted)
    assert accepted_total == 0


def test_sink_routing_lands_all_accepted_rows():
    out = run_datacraft()
    assert out["manifest"]["rows_landed"].sum() == out["total_accepted"]
    assert set(out["manifest"]["sink"]) <= {"S3", "Andes", "EDX"}
    assert set(out["sink_rows"]) == set(out["manifest"]["sink"])
    assert out["total_accepted"] == 5 * 120


def test_health_counts_and_statuses():
    out = run_datacraft()
    health = out["health"]
    assert len(health) == 60
    assert set(health["status"]) <= {"HEALTHY", "DEGRADED", "STALLED"}
    # Duplicate + late rates are 3/125 and 2/125, under the 5% degraded bar.
    assert (health["duplicate_rate"] <= 0.05).all()
    assert (health["late_rate"] <= 0.05).all()
    # Lag is measured 10 min past the newest event, so 1- and 5-minute
    # pipelines read STALLED and 15-minute pipelines read HEALTHY.
    assert set(health[health["micro_batch_minutes"] == 15]["status"]) == {"HEALTHY"}


def test_health_empty_source_is_stalled():
    reg = generate_pipeline_registry(n=5)
    empty = {"catalog": {"accepted": pd.DataFrame({"event_time": []}), "total_arrived": 0,
                         "duplicates": pd.DataFrame(), "late": pd.DataFrame()}}
    results = {s: empty["catalog"] for s in SOURCES}
    health = monitor_pipelines(reg, results)
    assert (health["status"] == "STALLED").all()


def test_catalog_registers_every_sink_source_pair():
    out = run_datacraft()
    catalog = out["catalog"]
    assert len(catalog) == len(out["manifest"].groupby(["sink", "source"]))
    assert catalog["table"].is_unique
    assert (catalog["row_count"] > 0).all()


def test_catalog_search():
    out = run_datacraft()
    hits = search_catalog(out["catalog"], "orders")
    assert len(hits) >= 1
    assert hits["source"].eq("orders").all()
    assert search_catalog(out["catalog"], "zzz-no-such-table").empty
    assert len(search_catalog(out["catalog"], "bdt-orders")) >= 1


def test_run_deterministic():
    a = run_datacraft()
    b = run_datacraft()
    assert a["total_accepted"] == b["total_accepted"] == 600
    assert a["total_duplicates"] == b["total_duplicates"] == 15
    assert a["total_late"] == b["total_late"] == 10
    pd.testing.assert_frame_equal(a["health"], b["health"])
    pd.testing.assert_frame_equal(a["catalog"], b["catalog"])
