"""Tests for monitoring, replay/backfill, and the end-to-end run."""

from datetime import datetime

from cold_chain.monitor import Warehouse, late_data_alerts, replay_window
from cold_chain.models import TelemetryReading
from cold_chain.sources import generate_synthetic_feeds
from run_pipeline import run


def test_warehouse_load_is_idempotent():
    wh = Warehouse()
    reading = TelemetryReading(reading_id="R1", shipment_id="ORD-10000",
                               device_id="TempSense-101",
                               recorded_at=datetime(2026, 11, 10, 8, 30),
                               temperature_c=5.0)
    assert wh.load_readings([reading]) == 1
    assert wh.load_readings([reading]) == 0  # replay adds nothing
    assert len(wh.readings) == 1


def test_late_data_alert_flags_old_readings():
    reading = TelemetryReading(reading_id="R1", shipment_id="ORD-10000",
                               device_id="TempSense-101",
                               recorded_at=datetime(2026, 11, 10, 8, 30),
                               temperature_c=5.0)
    alerts = late_data_alerts([reading], datetime(2026, 11, 19, 12, 0),
                              max_age_hours=24.0)
    assert len(alerts) == 1 and alerts[0]["age_hours"] > 24.0


def test_replay_window_filters_to_ship_dates():
    feeds = generate_synthetic_feeds(seed=7)
    out = replay_window(feeds, {"2026-11-10"})
    assert out["orders"] and all(o["ship_dt"] == "2026-11-10"
                                 for o in out["orders"])
    assert all(r["shipment"] in out["shipment_ids"]
               for r in out["telemetry"])


def test_synthetic_feeds_are_deterministic():
    a = generate_synthetic_feeds(seed=42)
    b = generate_synthetic_feeds(seed=42)
    assert a == b


def test_end_to_end_run_loads_expected_volumes():
    summary = run(seed=42)
    assert summary["counts"]["shipments"] == 240
    assert summary["counts"]["telemetry_raw"] == 1200
    assert summary["counts"]["milestones"] == 960
    assert summary["counts"]["telemetry_loaded"] > 1000
    assert summary["quarantine_rate"] < 0.10
    assert summary["warehouse"]["shipments"] == 240
