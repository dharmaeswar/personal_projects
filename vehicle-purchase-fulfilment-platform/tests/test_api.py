"""Tests for the REST + GraphQL-style API (api.py), over real HTTP."""

import json
import threading
import urllib.request
import urllib.error

import pytest

from vehicle_platform.api import Service, serve

VEHICLE = {
    "vin": "1HGCM82633A004352", "make": "Honda", "model": "Civic",
    "year": 2021, "mileage": 28410, "list_price_cents": 2_450_000,
    "status": "AVAILABLE", "features": ["backup camera"],
}

ORDER = {
    "order_id": "ORD-1",
    "vin": "1HGCM82633A004352",
    "customer_id": "CUST-1",
    "list_price_cents": 2_450_000,
    "state_code": "AZ",
    "delivery_zip": "85281",
}


@pytest.fixture()
def live(tmp_path):
    service = Service(tmp_path)
    service.seed_vehicle(dict(VEHICLE))
    server = serve(service, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    yield base, service
    server.shutdown()
    server.server_close()


def _req(base, method, path, body=None, headers=None):
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(base + path, data=data, method=method,
                                     headers={"Content-Type": "application/json",
                                              **(headers or {})})
    try:
        with urllib.request.urlopen(request) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read() or b"{}")


def test_health(live):
    base, _ = live
    status, body = _req(base, "GET", "/health")
    assert status == 200 and body == {"status": "ok"}


def test_dashboard_serves_html(live):
    base, _ = live
    with urllib.request.urlopen(base + "/") as resp:
        assert resp.status == 200
        assert "Vehicle Purchase Fulfilment" in resp.read().decode()


def test_create_and_get_order(live):
    base, _ = live
    status, body = _req(base, "POST", "/v1/orders", ORDER)
    assert status == 201
    assert body["status"] == "RESERVED"
    assert body["total_cents"] == 2_733_102
    status, body = _req(base, "GET", "/v1/orders/ORD-1")
    assert status == 200 and body["order_id"] == "ORD-1"


def test_create_order_idempotent_on_key(live):
    base, service = live
    headers = {"Idempotency-Key": "key-1"}
    first, _ = _req(base, "POST", "/v1/orders", ORDER, headers)
    second, body = _req(base, "POST", "/v1/orders", ORDER, headers)
    assert first == 201 and second == 200
    assert body["order_id"] == "ORD-1"
    assert len(service.events.read_key("order-events", "ORD-1")) == 1


def test_create_order_bad_vin_returns_one_error_shape(live):
    base, _ = live
    status, body = _req(base, "POST", "/v1/orders", dict(ORDER, vin="BAD"))
    assert status == 400
    assert set(body) == {"error"}
    assert body["error"]["code"] == 400


def test_advance_order_happy_path_and_illegal(live):
    base, _ = live
    _req(base, "POST", "/v1/orders", ORDER)
    status, body = _req(base, "POST", "/v1/orders/ORD-1/advance",
                        {"to": "INSPECTED"})
    assert status == 200 and body["status"] == "INSPECTED"
    status, body = _req(base, "POST", "/v1/orders/ORD-1/advance",
                        {"to": "DELIVERED"})
    assert status == 400  # skips FINANCED and DELIVERY_SCHEDULED


def test_advance_unknown_order_404_shape(live):
    base, _ = live
    status, body = _req(base, "POST", "/v1/orders/NOPE/advance",
                        {"to": "INSPECTED"})
    assert status == 400
    assert "unknown order" in body["error"]["message"]


def test_get_vehicle(live):
    base, _ = live
    status, body = _req(base, "GET", "/v1/vehicles/1HGCM82633A004352")
    assert status == 200 and body["make"] == "Honda"
    status, body = _req(base, "GET", "/v1/vehicles/UNKNOWNVIN00000001")
    assert status == 404


def test_graphql_vehicle_query(live):
    base, _ = live
    status, body = _req(
        base, "POST", "/v1/graphql",
        {"query": '{ vehicle(vin: "1HGCM82633A004352") { make listPriceCents } }'})
    assert status == 200
    assert body["data"] == {"make": "Honda", "listPriceCents": 2_450_000}


def test_graphql_order_query_after_advance(live):
    base, _ = live
    _req(base, "POST", "/v1/orders", ORDER)
    _req(base, "POST", "/v1/orders/ORD-1/advance", {"to": "INSPECTED"})
    status, body = _req(
        base, "POST", "/v1/graphql",
        {"query": '{ order(id: "ORD-1") { status totalCents } }'})
    assert status == 200
    assert body["data"] == {"status": "INSPECTED", "totalCents": 2_733_102}


def test_graphql_unknown_field_rejected(live):
    base, _ = live
    status, body = _req(
        base, "POST", "/v1/graphql",
        {"query": '{ vehicle(vin: "1HGCM82633A004352") { paintColor } }'})
    assert status == 400
    assert "unknown fields" in body["error"]["message"]


def test_replay_matches_stored_order(live):
    base, service = live
    _req(base, "POST", "/v1/orders", ORDER)
    _req(base, "POST", "/v1/orders/ORD-1/advance", {"to": "INSPECTED"})
    rebuilt = service.replay_order("ORD-1")
    stored = service.orders.get_order("ORD-1")
    assert rebuilt.status == stored.status == "INSPECTED"
    assert rebuilt.total_cents() == stored.total_cents()
