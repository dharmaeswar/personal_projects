"""Tests for normalisation: partner field maps, units, timestamps."""

from cold_chain.models import parse_ts
from cold_chain.normalize import (load_partner_specs, normalize_milestones,
                                  normalize_orders, normalize_telemetry)

SPECS = load_partner_specs("configs/partners.json")


def test_orders_map_to_shared_model():
    rows = [{"order_ref": "ORD-10000", "cust_name": "Customer 01",
             "from_city": "Buffalo, NY", "to_city": "Chicago, IL",
             "product_name": "Vaccines", "temp_min": 2.0, "temp_max": 8.0,
             "ship_dt": "2026-11-10", "carrier_name": "NorthStar Freight"}]
    out = normalize_orders(rows, SPECS["customer_orders"])
    assert len(out) == 1
    assert out[0].shipment_id == "ORD-10000"
    assert out[0].temp_range() == (2.0, 8.0)
    assert out[0].carrier == "NorthStar Freight"


def test_telemetry_maps_and_parses_timestamp():
    rows = [{"id": "R00001", "shipment": "ORD-10000", "dev": "TempSense-101",
             "ts": "2026-11-10T08:30:00Z", "tempC": 5.2, "hum": 55.0}]
    out = normalize_telemetry(rows, SPECS["device_telemetry"])
    assert out[0].temperature_c == 5.2
    assert out[0].recorded_at == parse_ts("2026-11-10T08:30:00Z")
    assert out[0].humidity_pct == 55.0


def test_telemetry_fahrenheit_partner_converts_to_celsius():
    spec = dict(SPECS["device_telemetry"], temp_unit="F", name="fahrenheit-dev")
    rows = [{"id": "R00002", "shipment": "ORD-10000", "dev": "TempSense-102",
             "ts": "2026-11-10 08:30:00", "tempC": 41.0, "hum": 50.0}]
    out = normalize_telemetry(rows, spec)
    assert out[0].temperature_c == 5.0  # 41F == 5C


def test_milestones_map_and_uppercase_event():
    rows = [{"milestone_id": "M0000-0", "order_ref": "ORD-10000",
             "carrier": "NorthStar Freight", "status": "picked_up",
             "event_time": "2026-11-10 08:00:00", "loc": "Buffalo, NY"}]
    out = normalize_milestones(rows, SPECS["carrier_milestones"])
    assert out[0].event == "PICKED_UP"
    assert out[0].shipment_id == "ORD-10000"


def test_parse_ts_rejects_garbage():
    import pytest
    with pytest.raises(ValueError):
        parse_ts("not-a-date")


def test_missing_field_raises_key_error():
    import pytest
    rows = [{"id": "R00003", "shipment": "ORD-10000", "dev": "TempSense-103",
             "ts": "2026-11-10T08:30:00Z", "hum": 50.0}]  # no tempC
    with pytest.raises(KeyError):
        normalize_telemetry(rows, SPECS["device_telemetry"])
