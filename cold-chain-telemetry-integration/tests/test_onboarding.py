"""Tests for partner onboarding: spec validation, dry run, launch readiness."""

import pytest

from cold_chain.onboarding import (dry_run_sample, launch_readiness,
                                  validate_partner_spec)

TELEMETRY_SPEC = {
    "name": "device",
    "temp_unit": "C",
    "field_map": {
        "id": "reading_id", "shipment": "shipment_id", "dev": "device_id",
        "ts": "recorded_at", "tempC": "temperature_c", "hum": "humidity_pct",
    },
}

GOOD_ROWS = [
    {"id": "r-1", "shipment": "S-100", "dev": "D-1",
     "ts": "2026-11-20T10:00:00Z", "tempC": "4.2", "hum": "55"},
    {"id": "r-2", "shipment": "S-100", "dev": "D-1",
     "ts": "2026-11-20T10:05:00Z", "tempC": "4.5", "hum": "54"},
]


def test_valid_spec_has_no_problems():
    assert validate_partner_spec(TELEMETRY_SPEC, "device_telemetry") == []


def test_spec_missing_required_target_is_rejected():
    spec = dict(TELEMETRY_SPEC)
    spec["field_map"] = {k: v for k, v in TELEMETRY_SPEC["field_map"].items()
                         if v != "temperature_c"}
    problems = validate_partner_spec(spec, "device_telemetry")
    assert any("temperature_c" in p for p in problems)


def test_spec_with_bad_temp_unit_is_rejected():
    spec = dict(TELEMETRY_SPEC, temp_unit="K")
    problems = validate_partner_spec(spec, "device_telemetry")
    assert any("temp_unit" in p for p in problems)


def test_spec_without_name_is_rejected():
    spec = {k: v for k, v in TELEMETRY_SPEC.items() if k != "name"}
    assert any("name" in p
               for p in validate_partner_spec(spec, "device_telemetry"))


def test_unknown_feed_kind_is_rejected():
    problems = validate_partner_spec(TELEMETRY_SPEC, "satellite_feed")
    assert problems and "unknown feed kind" in problems[0]


def test_dry_run_maps_good_sample():
    result = dry_run_sample(TELEMETRY_SPEC, "device_telemetry", GOOD_ROWS)
    assert result["mapped"] == 2
    assert result["failed"] == 0
    assert result["unmapped_source_fields"] == []


def test_dry_run_reports_bad_timestamp_row():
    rows = GOOD_ROWS + [
        {"id": "r-3", "shipment": "S-100", "dev": "D-1",
         "ts": "not-a-date", "tempC": "4.0", "hum": "55"},
    ]
    result = dry_run_sample(TELEMETRY_SPEC, "device_telemetry", rows)
    assert result["mapped"] == 2
    assert result["failed"] == 1
    assert result["failures"][0]["row"] == 2


def test_dry_run_reports_unmapped_source_fields():
    rows = [dict(GOOD_ROWS[0], firmware="v2.3")]
    result = dry_run_sample(TELEMETRY_SPEC, "device_telemetry", rows)
    assert result["unmapped_source_fields"] == ["firmware"]


def test_dry_run_converts_fahrenheit_sample():
    spec = dict(TELEMETRY_SPEC, temp_unit="F")
    rows = [dict(GOOD_ROWS[0], tempC="39.2")]
    result = dry_run_sample(spec, "device_telemetry", rows)
    assert result["mapped"] == 1
    assert result["failed"] == 0


def test_launch_ready_for_clean_sample():
    result = launch_readiness(TELEMETRY_SPEC, "device_telemetry", GOOD_ROWS)
    assert result["ready"] is True
    assert result["reasons"] == []


def test_launch_blocked_when_failure_rate_too_high():
    bad_rows = [
        {"id": f"r-{i}", "shipment": "S-100", "dev": "D-1",
         "ts": "not-a-date", "tempC": "4.0", "hum": "55"}
        for i in range(3)
    ]
    result = launch_readiness(TELEMETRY_SPEC, "device_telemetry", bad_rows)
    assert result["ready"] is False
    assert any("failure rate" in r for r in result["reasons"])


def test_launch_blocked_when_spec_invalid():
    spec = dict(TELEMETRY_SPEC, field_map={})
    result = launch_readiness(spec, "device_telemetry", GOOD_ROWS)
    assert result["ready"] is False
    assert result["dry_run"] is None


def test_launch_blocked_when_sample_empty():
    result = launch_readiness(TELEMETRY_SPEC, "device_telemetry", [])
    assert result["ready"] is False
    assert any("empty" in r for r in result["reasons"])
