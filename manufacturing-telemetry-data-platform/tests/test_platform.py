"""Tests for the manufacturing telemetry data platform."""

import pytest

from telemetry_platform import DataPlatform, TelemetryReading, Topic
from telemetry_platform.analytics import find_anomalies, machine_summary
from telemetry_platform.api import (get_daily_report, latest_reading,
                                    list_anomalies)
from run_demo import MACHINES, seed_readings

START = 1_793_000_000
END = START + 2 * 86_400


def _reading(**over):
    base = dict(machine_id="WAAM-01", ts=START, temp_c=820.0,
                vibration_mm_s=4.5, weld_current_a=250.0, layer=1,
                status="printing")
    base.update(over)
    return TelemetryReading(**base)


def _platform_with(readings):
    platform = DataPlatform()
    for reading in readings:
        platform.ingest(reading)
    return platform


def test_stream_partitions_by_machine_and_tracks_offsets():
    topic = Topic("t", partitions=4)
    first = topic.publish("WAAM-01", {"n": 1})
    second = topic.publish("WAAM-01", {"n": 2})
    assert first.partition == second.partition
    assert second.offset == first.offset + 1
    assert topic.lag("g1") == 2
    records = topic.poll("g1")
    assert [r.value["n"] for r in records] == [1, 2]
    topic.commit("g1", records)
    assert topic.lag("g1") == 0
    assert topic.poll("g1") == []


def test_stream_groups_consume_independently():
    topic = Topic("t", partitions=2)
    topic.publish("A", {"n": 1})
    assert topic.lag("g1") == 1
    assert topic.lag("g2") == 1
    topic.commit("g1", topic.poll("g1"))
    assert topic.lag("g1") == 0
    assert topic.lag("g2") == 1


def test_ingest_writes_timeseries_and_cache():
    platform = _platform_with([_reading()])
    assert platform.timeseries.count() == 1
    cached = latest_reading(platform, "WAAM-01")
    assert cached is not None and cached["temp_c"] == 820.0
    assert latest_reading(platform, "UNKNOWN") is None
    platform.close()


def test_timeseries_range_is_ordered_and_bounded():
    platform = _platform_with([
        _reading(ts=START + 30), _reading(ts=START + 10),
        _reading(ts=START + 20),
    ])
    rows = platform.timeseries.range("WAAM-01", START, START + 25)
    assert [r.ts for r in rows] == [START + 10, START + 20]
    platform.close()


def test_document_store_round_trips_and_filters_by_type():
    platform = DataPlatform()
    platform.register_machine("WAAM-01", {"type": "waam_printer"})
    platform.register_machine("WELD-01", {"type": "weld_repair_robot"})
    assert platform.documents.get("WAAM-01") == {"type": "waam_printer"}
    assert platform.documents.find_by_type("waam_printer") == ["WAAM-01"]
    assert platform.documents.get("NOPE") is None
    platform.close()


def test_relational_store_tracks_runs():
    platform = DataPlatform()
    platform.relational.start_run("R1", "WAAM-01", START, "bracket", 12)
    runs = platform.relational.runs_for_machine("WAAM-01")
    assert len(runs) == 1 and runs[0]["part"] == "bracket"
    assert platform.relational.runs_for_machine("OTHER") == []
    platform.close()


def test_anomalies_flag_limits_with_plain_reasons():
    readings = [_reading(temp_c=985.0, ts=START + 1),
                _reading(vibration_mm_s=14.8, ts=START + 2),
                _reading(weld_current_a=150.0, ts=START + 3),
                _reading()]
    found = find_anomalies(readings)
    kinds = {a.kind for a in found}
    assert {"over_temperature", "vibration_spike",
            "weld_current_out_of_band"} <= kinds
    assert all(a.reason for a in found)
    assert find_anomalies([_reading()]) == []


def test_machine_summary_reports_counts_and_means():
    platform = _platform_with([_reading(temp_c=800.0),
                               _reading(ts=START + 1, temp_c=840.0)])
    summary = machine_summary(platform, "WAAM-01", START, END)
    assert summary["readings"] == 2
    assert summary["mean_temp_c"] == 820.0
    assert summary["max_temp_c"] == 840.0
    assert machine_summary(platform, "UNKNOWN", START, END)["readings"] == 0
    platform.close()


def test_seeded_demo_finds_the_two_planted_events():
    platform = DataPlatform()
    for machine_id in MACHINES:
        platform.register_machine(machine_id, {"type": "demo"})
    for reading in seed_readings():
        platform.ingest(reading)
    assert platform.timeseries.count() == 720
    report = get_daily_report(platform, list(MACHINES), START, END)
    assert report["anomaly_count"] >= 2
    kinds = report["anomalies_by_kind"]
    assert kinds.get("over_temperature", 0) >= 1
    assert kinds.get("vibration_spike", 0) >= 1
    assert len(report["machines"]) == 3
    platform.close()


def test_api_anomalies_match_analytics():
    platform = _platform_with([_reading(temp_c=990.0)])
    via_api = list_anomalies(platform, "WAAM-01", START, END)
    assert any(a["kind"] == "over_temperature" for a in via_api)
    platform.close()
