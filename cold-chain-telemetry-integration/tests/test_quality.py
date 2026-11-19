"""Tests for validation, quality checks, and excursion alerts."""

from datetime import datetime

from cold_chain.models import Shipment, TelemetryReading
from cold_chain.quality import (check_milestones, check_telemetry,
                                excursion_alerts)
from cold_chain.models import Milestone

SHIP = Shipment(shipment_id="ORD-10000", order_id="ORD-10000",
                customer="Customer 01", origin="Buffalo, NY",
                destination="Chicago, IL", product="Vaccines",
                min_temp_c=2.0, max_temp_c=8.0,
                ship_date="2026-11-10", carrier="NorthStar Freight")


def _reading(rid, temp, shipment_id="ORD-10000"):
    return TelemetryReading(reading_id=rid, shipment_id=shipment_id,
                            device_id="TempSense-101",
                            recorded_at=datetime(2026, 11, 10, 8, 30),
                            temperature_c=temp)


def test_in_range_reading_passes():
    report = check_telemetry([_reading("R1", 5.0)], {"ORD-10000": SHIP})
    assert report.passed == 1 and report.quarantined == []


def test_excursion_is_quarantined_and_alerted():
    readings = [_reading("R1", 5.0), _reading("R2", 12.5)]
    report = check_telemetry(readings, {"ORD-10000": SHIP})
    assert report.passed == 1
    assert len(report.quarantined) == 1
    assert "excursion" in report.quarantined[0]["reasons"][0]
    alerts = excursion_alerts(readings, {"ORD-10000": SHIP})
    assert len(alerts) == 1
    assert alerts[0]["temperature_c"] == 12.5


def test_duplicate_reading_id_quarantined():
    readings = [_reading("R1", 5.0), _reading("R1", 5.1)]
    report = check_telemetry(readings, {"ORD-10000": SHIP})
    assert report.passed == 1
    assert report.quarantined[0]["reasons"] == ["duplicate reading_id"]


def test_unknown_shipment_quarantined():
    report = check_telemetry([_reading("R1", 5.0, "ORD-99999")],
                             {"ORD-10000": SHIP})
    assert report.quarantined[0]["reasons"] == ["unknown shipment_id"]


def test_physically_impossible_temperature_quarantined_not_alerted():
    readings = [_reading("R1", 120.0)]
    report = check_telemetry(readings, {"ORD-10000": SHIP})
    assert len(report.quarantined) == 1
    assert "physical bounds" in report.quarantined[0]["reasons"][0]
    assert excursion_alerts(readings, {"ORD-10000": SHIP}) == []


def test_milestone_unknown_event_quarantined():
    item = Milestone(milestone_id="M1", shipment_id="ORD-10000",
                     carrier="NorthStar Freight", event="TELEPORTED",
                     event_at=datetime(2026, 11, 10, 9, 0),
                     location="Buffalo, NY")
    report = check_milestones([item], {"ORD-10000": SHIP})
    assert len(report.quarantined) == 1
    assert "unknown event" in report.quarantined[0]["reasons"][0]


def test_quarantine_rate():
    readings = [_reading("R1", 5.0), _reading("R2", 50.0)]
    report = check_telemetry(readings, {"ORD-10000": SHIP})
    assert report.quarantine_rate() == 0.5
