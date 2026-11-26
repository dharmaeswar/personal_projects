"""API tests: the real HTTP server on an ephemeral port, via urllib."""

import json
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from inventory_orchestration.app import make_handler
from inventory_orchestration.events import EventBus
from inventory_orchestration.service import InventoryService
from inventory_orchestration.store import demo_store


@pytest.fixture()
def base_url():
    service = InventoryService(store=demo_store(), bus=EventBus())
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(service))
    import threading

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def request(base_url, method, path, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(base_url + path, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def test_health_and_inventory(base_url):
    status, body = request(base_url, "GET", "/health")
    assert status == 200 and body == {"status": "ok"}
    status, rows = request(base_url, "GET", "/v1/inventory")
    assert status == 200
    dal_headsets = [r for r in rows if r["sku"] == "SKU-1001" and r["warehouse"] == "DAL"]
    assert dal_headsets == [{"sku": "SKU-1001", "name": "Wireless headset",
                             "warehouse": "DAL", "available": 120, "reserved": 0,
                             "on_hand": 120}]


def test_create_fulfil_and_list_orders(base_url):
    status, order = request(base_url, "POST", "/v1/orders",
                            {"sku": "SKU-1002", "qty": 10})
    assert status == 201 and order["status"] == "allocated"
    status, done = request(base_url, "POST", f"/v1/orders/{order['order_id']}/fulfill")
    assert status == 200 and done["status"] == "fulfilled"
    status, orders = request(base_url, "GET", "/v1/orders")
    assert [o["order_id"] for o in orders] == [order["order_id"]]


def test_create_order_rejects_unknown_sku(base_url):
    status, body = request(base_url, "POST", "/v1/orders", {"sku": "NOPE", "qty": 1})
    assert status == 400 and "unknown sku" in body["error"]


def test_dashboard_served_and_events_listed(base_url):
    req = urllib.request.Request(base_url + "/")
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
        assert b"Inventory Orchestration" in resp.read()
    request(base_url, "POST", "/v1/restock", {"sku": "SKU-1004", "warehouse": "HOU", "qty": 7})
    status, events = request(base_url, "GET", "/v1/events?topic=inventory.restocked")
    assert status == 200 and len(events) == 1
    assert events[0]["payload"] == {"sku": "SKU-1004", "warehouse": "HOU", "qty": 7}


def test_metrics_counts_orders_and_events(base_url):
    request(base_url, "POST", "/v1/orders", {"sku": "SKU-1001", "qty": 1})
    req = urllib.request.Request(base_url + "/metrics")
    with urllib.request.urlopen(req) as resp:
        text = resp.read().decode()
    assert "inventory_orders_total 1" in text
    assert "inventory_events_total 2" in text  # reserved + allocated
