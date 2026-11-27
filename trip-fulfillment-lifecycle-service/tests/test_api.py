import json
import threading
import urllib.request
import urllib.error
from http.server import ThreadingHTTPServer

import pytest

from fulfillment import api as api_module


@pytest.fixture(scope="module")
def server():
    api_module.SERVICE = __import__(
        "fulfillment.service", fromlist=["FulfillmentService"]
    ).FulfillmentService(
        __import__("fulfillment.service", fromlist=["demo_drivers"]).demo_drivers()
    )
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), api_module.Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


def _req(base, method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base + path, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def test_quote_endpoint(server):
    status, body = _req(server, "POST", "/quote",
                        {"distance_km": 10.0, "duration_min": 20.0,
                         "surge_multiplier": 1.0})
    assert status == 200
    assert body["total_cents"] == 1950


def test_full_trip_flow_over_http(server):
    _, quote = _req(server, "POST", "/quote",
                    {"distance_km": 8.0, "duration_min": 20.0})
    status, trip = _req(server, "POST", "/trips", {
        "rider_id": "rider-9", "vertical": "eats",
        "pickup_lat": 37.7749, "pickup_lon": -122.4194,
        "dropoff_lat": 37.8049, "dropoff_lon": -122.4494,
        "quote": quote, "idempotency_key": "api-demo-1"})
    assert status == 201
    trip_id = trip["trip_id"]
    assert trip["state"] == "requested"

    status, body = _req(server, "POST", f"/trips/{trip_id}/match")
    assert status == 200
    assert body["trip"]["state"] == "dispatched"
    assert body["driver_id"] == "drv-001"

    status, body = _req(server, "POST", f"/trips/{trip_id}/advance",
                        {"state": "pickup"})
    assert status == 200 and body["state"] == "pickup"

    status, body = _req(server, "GET", f"/trips/{trip_id}")
    assert status == 200
    assert len(body["events"]) >= 4
    assert body["events"][0]["seq"] == 1


def test_unknown_trip_404(server):
    status, body = _req(server, "GET", "/trips/trip-999999")
    assert status == 404
