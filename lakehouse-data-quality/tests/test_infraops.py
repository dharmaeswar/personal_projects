"""Tests for the InfraOps analytics module (lakehouse/infraops.py)."""

from __future__ import annotations

import pandas as pd
import pytest

from lakehouse.infraops import (
    build_analytics_view,
    build_operational_view,
    build_unified_model,
    check_unified_reconciliation,
    generate_infraops,
    generate_infraops_events,
    load_incident_batch,
    quarantine_capacity,
    quarantine_equipment,
    quarantine_incidents,
    quarantine_telemetry,
    run_infraops_stream,
    tune_query_demo,
    validate_capacity,
    validate_equipment,
    validate_incidents,
    validate_telemetry,
)


@pytest.fixture(scope="module")
def data():
    return generate_infraops()


def test_domain_shapes(data):
    assert len(data["data_centers"]) == 8
    assert data["data_centers"]["dc_id"].is_unique
    assert len(data["equipment"]) == 60
    assert len(data["capacity"]) == 240
    # 240 base telemetry rows + 2 planted duplicate deliveries.
    assert len(data["telemetry"]) == 242
    assert len(data["incidents"]) == 24


def test_every_violation_type_is_caught(data):
    tele_checks = validate_telemetry(
        data["telemetry"], data["equipment"], data["data_centers"]
    )
    assert any(
        c.name == "uniqueness:reading_id" and not c.passed for c in tele_checks
    )
    assert any(c.name == "completeness" and not c.passed for c in tele_checks)
    assert any(c.name == "metric_ranges" and not c.passed for c in tele_checks)
    assert any(
        c.name == "fk:equip_id->equip_id" and not c.passed for c in tele_checks
    )
    inc_checks = validate_incidents(data["incidents"], data["data_centers"])
    assert any(
        c.name == "incident_after_open" and not c.passed for c in inc_checks
    )
    eq_checks = validate_equipment(data["equipment"], data["data_centers"])
    assert any(
        c.name == "decommission_after_install" and not c.passed
        for c in eq_checks
    )
    # Capacity is clean by construction.
    assert all(c.passed for c in validate_capacity(data["capacity"], data["data_centers"]))


def test_quarantine_counts(data):
    silver_t, quar_t = quarantine_telemetry(
        data["telemetry"], data["equipment"], data["data_centers"]
    )
    # 2 duplicate deliveries + 1 null dc + 1 unknown equip + 1 temp + 1 util = 6.
    assert len(quar_t) == 6
    assert len(silver_t) == 236
    assert silver_t["reading_id"].is_unique
    _, quar_i = quarantine_incidents(data["incidents"], data["data_centers"])
    assert len(quar_i) == 1
    _, quar_e = quarantine_equipment(data["equipment"], data["data_centers"])
    assert len(quar_e) == 1
    silver_c, quar_c = quarantine_capacity(data["capacity"], data["data_centers"])
    assert len(quar_c) == 0
    assert len(silver_c) == 240


def test_quarantine_reasons_named(data):
    _, quar_t = quarantine_telemetry(
        data["telemetry"], data["equipment"], data["data_centers"]
    )
    reasons = "; ".join(quar_t["quarantine_reason"])
    assert "metric_ranges" in reasons
    assert "uniqueness:reading_id" in reasons
    _, quar_i = quarantine_incidents(data["incidents"], data["data_centers"])
    assert "incident_after_open" in quar_i["quarantine_reason"].iloc[0]


def test_unified_model_contents(data):
    silver_t, _ = quarantine_telemetry(
        data["telemetry"], data["equipment"], data["data_centers"]
    )
    silver_i, _ = quarantine_incidents(data["incidents"], data["data_centers"])
    silver_c, _ = quarantine_capacity(data["capacity"], data["data_centers"])
    unified = build_unified_model(
        data["data_centers"], silver_t, silver_i, silver_c
    )
    assert len(unified) == 8
    assert unified["incidents"].sum() == len(silver_i)
    assert (unified["avg_temp_c"] >= 10).all() and (unified["avg_temp_c"] <= 45).all()
    assert (unified["max_utilization_pct"] <= 100).all()
    assert (unified["capacity_utilization_pct"] >= 0).all()
    assert (unified["capacity_utilization_pct"] <= 100).all()


def test_view_reconciliation(data):
    silver_t, _ = quarantine_telemetry(
        data["telemetry"], data["equipment"], data["data_centers"]
    )
    silver_i, _ = quarantine_incidents(data["incidents"], data["data_centers"])
    silver_c, _ = quarantine_capacity(data["capacity"], data["data_centers"])
    unified = build_unified_model(
        data["data_centers"], silver_t, silver_i, silver_c
    )
    analytics = build_analytics_view(unified)
    operational = build_operational_view(unified)
    assert len(operational) == 8
    assert analytics["data_centers"].sum() == 8
    recon = check_unified_reconciliation(unified, silver_t, silver_i, analytics)
    assert recon.passed


def test_streaming_exactly_once():
    events = generate_infraops_events()
    result = run_infraops_stream(events)
    assert result["total_arrived"] == 125
    assert len(result["accepted"]) == 120
    assert len(result["late"]) == 2
    assert len(result["duplicates"]) == 3


def test_batch_dedup(data):
    loaded, dupes = load_incident_batch(data["incidents"])
    assert len(loaded) + len(dupes) == len(data["incidents"])
    assert loaded["incident_id"].is_unique


def test_tuning_results_match(data):
    silver_t, _ = quarantine_telemetry(
        data["telemetry"], data["equipment"], data["data_centers"]
    )
    tuning = tune_query_demo(silver_t, data["data_centers"])
    assert tuning["rows"] >= 50000
    assert tuning["results_match"] is True
    assert tuning["speedup"] > 1


def test_determinism():
    first = generate_infraops()
    second = generate_infraops()
    for key in first:
        pd.testing.assert_frame_equal(first[key], second[key])
