"""Tests for the shipment store: validation, events, progress, dashboard."""

import pytest

from freight_ops.store import ShipmentStore, ValidationError, validate_event, validate_shipment


def _payload(**over):
    body = {
        "reference": "BNSF-1001",
        "origin": "Fort Worth, TX",
        "destination": "Chicago, IL",
        "cars": 40,
        "weight_tons": 3200,
        "distance_miles": 925,
    }
    body.update(over)
    return body


def test_create_sets_booked_and_full_distance_remaining():
    store = ShipmentStore()
    shipment = store.create(validate_shipment(_payload()))
    assert shipment["status"] == "booked"
    assert shipment["distance_remaining_miles"] == 925
    assert shipment["events"] == []
    assert shipment["reference"] == "BNSF-1001"


def test_create_rejects_bad_reference():
    with pytest.raises(ValidationError):
        validate_shipment(_payload(reference="x"))  # too short
    with pytest.raises(ValidationError):
        validate_shipment(_payload(reference="BAD REF!"))  # space and bang


def test_create_rejects_zero_cars_and_negative_weight():
    with pytest.raises(ValidationError):
        validate_shipment(_payload(cars=0))
    with pytest.raises(ValidationError):
        validate_shipment(_payload(cars=201))
    with pytest.raises(ValidationError):
        validate_shipment(_payload(weight_tons=0))
    with pytest.raises(ValidationError):
        validate_shipment(_payload(distance_miles=-5))


def test_create_rejects_non_object_body():
    with pytest.raises(ValidationError):
        validate_shipment(["not", "an", "object"])


def test_event_flow_moves_status_forward():
    store = ShipmentStore()
    shipment = store.create(validate_shipment(_payload()))
    store.add_event(shipment["id"], validate_event({"type": "departed", "location": "Fort Worth, TX"}))
    assert store.get(shipment["id"])["status"] == "in_transit"
    store.add_event(shipment["id"], validate_event({"type": "delayed", "location": "Kansas City, MO", "note": "crew change"}))
    assert store.get(shipment["id"])["status"] == "delayed"
    store.add_event(shipment["id"], validate_event({"type": "delivered", "location": "Chicago, IL"}))
    final = store.get(shipment["id"])
    assert final["status"] == "delivered"
    assert final["distance_remaining_miles"] == 0.0
    assert len(final["events"]) == 3


def test_event_rejects_unknown_type():
    with pytest.raises(ValidationError):
        validate_event({"type": "teleported", "location": "Nowhere"})


def test_add_event_to_missing_shipment_returns_none():
    store = ShipmentStore()
    assert store.add_event(999, validate_event({"type": "departed", "location": "Fort Worth, TX"})) is None


def test_progress_update_validates_bounds():
    store = ShipmentStore()
    shipment = store.create(validate_shipment(_payload()))
    store.update_progress(shipment["id"], 400)
    assert store.get(shipment["id"])["distance_remaining_miles"] == 400
    with pytest.raises(ValidationError):
        store.update_progress(shipment["id"], 926)  # beyond total distance
    with pytest.raises(ValidationError):
        store.update_progress(shipment["id"], -1)


def test_list_filters_by_status():
    store = ShipmentStore()
    first = store.create(validate_shipment(_payload()))
    store.create(validate_shipment(_payload(reference="BNSF-1002")))
    store.add_event(first["id"], validate_event({"type": "departed", "location": "Fort Worth, TX"}))
    assert len(store.list()) == 2
    assert len(store.list("in_transit")) == 1
    assert len(store.list("booked")) == 1
    with pytest.raises(ValidationError):
        store.list("lost")


def test_dashboard_counts_and_on_time_rate():
    store = ShipmentStore()
    on_time = store.create(validate_shipment(_payload()))
    late = store.create(validate_shipment(_payload(reference="BNSF-1002")))
    store.add_event(on_time["id"], validate_event({"type": "delivered", "location": "Chicago, IL"}))
    store.add_event(late["id"], validate_event({"type": "delayed", "location": "Kansas City, MO"}))
    store.add_event(late["id"], validate_event({"type": "delivered", "location": "Chicago, IL"}))
    dashboard = store.dashboard()
    assert dashboard["total_shipments"] == 2
    assert dashboard["by_status"]["delivered"] == 2
    assert dashboard["total_cars"] == 80
    assert dashboard["delivered"] == 2
    assert dashboard["on_time_rate"] == 0.5


def test_dashboard_on_time_rate_none_before_any_delivery():
    store = ShipmentStore()
    store.create(validate_shipment(_payload()))
    assert store.dashboard()["on_time_rate"] is None
