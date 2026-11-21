"""End-to-end HTTP tests: API + UI + metrics, against a live local server."""

import http.client
import json
import threading

import pytest

from freight_ops.app import create_server


@pytest.fixture(scope="module")
def base_url():
    server = create_server(port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    yield f"http://{host}:{port}"
    server.shutdown()
    server.server_close()


def _request(base_url, method, path, body=None):
    conn = http.client.HTTPConnection(base_url.split("://", 1)[1])
    headers = {"Content-Type": "application/json"} if body is not None else {}
    conn.request(method, path, json.dumps(body) if body is not None else None, headers)
    response = conn.getresponse()
    raw = response.read()
    conn.close()
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        parsed = None
    return response.status, parsed, raw


def _shipment_body(reference="BNSF-2001", **over):
    body = {
        "reference": reference,
        "origin": "Fort Worth, TX",
        "destination": "Chicago, IL",
        "cars": 40,
        "weight_tons": 3200,
        "distance_miles": 925,
    }
    body.update(over)
    return body


def test_health_and_ui(base_url):
    status, parsed, _ = _request(base_url, "GET", "/health")
    assert status == 200
    assert parsed == {"status": "ok"}
    status, _, raw = _request(base_url, "GET", "/")
    assert status == 200
    assert b"Shipment Board" in raw
    assert b"fetch(" in raw  # the UI calls the API from the browser


def test_create_get_and_eta_flow(base_url):
    status, created, _ = _request(base_url, "POST", "/v1/shipments", _shipment_body())
    assert status == 201
    shipment_id = created["id"]
    assert created["status"] == "booked"

    status, fetched, _ = _request(base_url, "GET", f"/v1/shipments/{shipment_id}")
    assert status == 200
    assert fetched["reference"] == "BNSF-2001"

    status, updated, _ = _request(
        base_url, "POST", f"/v1/shipments/{shipment_id}/events",
        {"type": "departed", "location": "Fort Worth, TX"},
    )
    assert status == 200
    assert updated["status"] == "in_transit"

    status, progress, _ = _request(
        base_url, "POST", f"/v1/shipments/{shipment_id}/progress",
        {"distance_remaining_miles": 560},
    )
    assert status == 200
    assert progress["distance_remaining_miles"] == 560

    status, eta, _ = _request(base_url, "GET", f"/v1/shipments/{shipment_id}/eta")
    assert status == 200
    assert eta["eta_hours"] == 20.0  # 560 miles at 28 mph


def test_create_rejects_invalid_payload(base_url):
    status, parsed, _ = _request(base_url, "POST", "/v1/shipments", _shipment_body(cars=0))
    assert status == 400
    assert "error" in parsed


def test_missing_shipment_is_404(base_url):
    status, parsed, _ = _request(base_url, "GET", "/v1/shipments/999999")
    assert status == 404
    assert parsed["error"] == "shipment not found"


def test_dashboard_and_metrics(base_url):
    _request(base_url, "POST", "/v1/shipments", _shipment_body("BNSF-2002"))
    status, dashboard, _ = _request(base_url, "GET", "/v1/dashboard")
    assert status == 200
    assert dashboard["total_shipments"] >= 2
    assert dashboard["by_status"]["booked"] >= 1

    status, _, raw = _request(base_url, "GET", "/metrics")
    assert status == 200
    text = raw.decode()
    assert "freight_ops_requests_total" in text
    assert "freight_ops_shipments" in text


def test_unknown_route_is_404(base_url):
    status, parsed, _ = _request(base_url, "GET", "/v1/nope")
    assert status == 404
