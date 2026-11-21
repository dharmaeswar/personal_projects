"""Tests for ETA estimates."""

import pytest

from freight_ops.eta import estimate_eta, estimate_eta_hours


def _shipment(status="in_transit", remaining=560.0):
    return {
        "id": 1,
        "reference": "BNSF-1001",
        "status": status,
        "distance_remaining_miles": remaining,
    }


def test_eta_divides_remaining_by_speed():
    # 560 miles at 28 mph = 20 hours.
    assert estimate_eta_hours(_shipment(), speed_mph=28.0) == 20.0


def test_eta_zero_when_nothing_remaining():
    assert estimate_eta_hours(_shipment(remaining=0.0)) == 0.0


def test_delayed_shipment_gets_buffer():
    # 560 / 28 = 20 hours, x1.25 delay buffer = 25 hours.
    assert estimate_eta_hours(_shipment(status="delayed")) == 25.0


def test_eta_rejects_non_positive_speed():
    with pytest.raises(ValueError):
        estimate_eta_hours(_shipment(), speed_mph=0)


def test_eta_payload_reports_inputs():
    payload = estimate_eta(_shipment(status="delayed"))
    assert payload["eta_hours"] == 25.0
    assert payload["delay_buffer_applied"] is True
    assert payload["planning_speed_mph"] == 28.0
    assert payload["shipment_id"] == 1
