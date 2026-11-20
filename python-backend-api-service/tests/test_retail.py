"""Tests for the retail orders-and-inventory module.

Unit tests cover validation, tax math, atomic stock reservation and the
order state machine; integration tests cover the new REST endpoints
end to end.
"""

import http.client
import json
import threading

import pytest

from payments_api.app import create_server
from payments_api.retail import (
    RetailStore,
    ValidationError,
    compute_tax_cents,
    validate_order,
    validate_product,
)


def _product(**overrides):
    payload = {
        "sku": "SKU-100",
        "name": "Cordless Drill",
        "price_cents": 129_99,
        "stock": 10,
    }
    payload.update(overrides)
    return payload


def _order(**overrides):
    payload = {
        "customer_id": "cust_7",
        "items": [{"sku": "SKU-100", "quantity": 2}],
    }
    payload.update(overrides)
    return payload


# --- tax math ---


def test_tax_rounds_half_up():
    # 8% of 10,000 = 800 exactly; 8% of 106 = 8.48 -> 8; 8% of 107 = 8.56 -> 9.
    assert compute_tax_cents(10_000) == 800
    assert compute_tax_cents(106) == 8
    assert compute_tax_cents(107) == 9
    assert compute_tax_cents(0) == 0


# --- validation ---


def test_validate_product_rejects_bad_inputs():
    for bad in (
        _product(sku="sku-100"),  # lowercase not allowed
        _product(sku="AB"),  # too short
        _product(name="  "),
        _product(price_cents=0),
        _product(price_cents=12.5),
        _product(stock=-1),
    ):
        with pytest.raises(ValidationError):
            validate_product(bad)


def test_validate_order_rejects_bad_inputs():
    for bad in (
        _order(customer_id=""),
        _order(items=[]),
        _order(items=[{"sku": "SKU-100", "quantity": 0}]),
        _order(items=[{"sku": "SKU-100", "quantity": 1}, {"sku": "SKU-100", "quantity": 1}]),
        _order(items=[{"sku": "bad sku", "quantity": 1}]),
    ):
        with pytest.raises(ValidationError):
            validate_order(bad)


# --- store behaviour ---


def test_duplicate_sku_rejected():
    store = RetailStore()
    store.create_product(validate_product(_product()))
    with pytest.raises(ValidationError):
        store.create_product(validate_product(_product()))


def test_place_order_totals_and_stock_reservation():
    store = RetailStore()
    product = store.create_product(validate_product(_product()))
    order, low = store.place_order(validate_order(_order()))
    # subtotal 2 x 12,999 = 25,998; tax 8% = 2,080 (2,079.84 rounds up); total 28,078.
    assert order.subtotal_cents == 25_998
    assert order.tax_cents == 2_080
    assert order.total_cents == 28_078
    assert order.status == "placed"
    assert product.stock == 8
    assert low == []  # 8 left, above the threshold of 5


def test_insufficient_stock_rejected_and_nothing_changes():
    store = RetailStore()
    product = store.create_product(validate_product(_product(stock=3)))
    store.create_product(validate_product(_product(sku="SKU-200", name="Paint", stock=9)))
    with pytest.raises(ValidationError):
        store.place_order(
            validate_order(
                _order(
                    items=[
                        {"sku": "SKU-200", "quantity": 2},
                        {"sku": "SKU-100", "quantity": 4},  # only 3 on hand
                    ]
                )
            )
        )
    # Atomic: the fillable first line was NOT reserved either.
    assert store.get_by_sku("SKU-200").stock == 9
    assert product.stock == 3
    assert store.order_count() == 0


def test_unknown_sku_rejected():
    store = RetailStore()
    store.create_product(validate_product(_product()))
    with pytest.raises(ValidationError):
        store.place_order(validate_order(_order(items=[{"sku": "SKU-999", "quantity": 1}])))


def test_low_stock_reported_when_reservation_crosses_threshold():
    store = RetailStore()
    store.create_product(validate_product(_product(stock=7)))
    _, low = store.place_order(validate_order(_order()))  # 7 - 2 = 5, at threshold
    assert [p.sku for p in low] == ["SKU-100"]
    assert [p.sku for p in store.low_stock()] == ["SKU-100"]


def test_cancel_returns_stock_and_double_cancel_rejected():
    store = RetailStore()
    product = store.create_product(validate_product(_product()))
    order, _ = store.place_order(validate_order(_order()))
    assert product.stock == 8
    cancelled = store.cancel_order(order)
    assert cancelled.status == "cancelled"
    assert product.stock == 10
    with pytest.raises(ValidationError):
        store.cancel_order(order)


def test_fulfill_then_cancel_rejected():
    store = RetailStore()
    store.create_product(validate_product(_product()))
    order, _ = store.place_order(validate_order(_order()))
    assert store.fulfill_order(order).status == "fulfilled"
    with pytest.raises(ValidationError):
        store.cancel_order(order)


def test_restock_adds_stock_and_validates():
    store = RetailStore()
    product = store.create_product(validate_product(_product(stock=2)))
    assert store.restock(product, 5).stock == 7
    with pytest.raises(ValidationError):
        store.restock(product, 0)


# --- HTTP integration ---


@pytest.fixture(scope="module")
def server():
    srv = create_server(port=0)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    yield srv
    srv.shutdown()
    srv.server_close()


def _request(server, method, path, body=None):
    conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
    payload = json.dumps(body) if body is not None else None
    conn.request(method, path, body=payload, headers={"Content-Type": "application/json"})
    resp = conn.getresponse()
    data = json.loads(resp.read().decode() or "{}")
    conn.close()
    return resp.status, data


def test_product_and_order_flow_end_to_end(server):
    status, product = _request(server, "POST", "/v1/products", _product(sku="SKU-300", stock=6))
    assert status == 201
    product_id = product["id"]

    status, fetched = _request(server, "GET", f"/v1/products/{product_id}")
    assert status == 200 and fetched["sku"] == "SKU-300"

    before = server.events.count()
    status, order = _request(
        server,
        "POST",
        "/v1/orders",
        {"customer_id": "cust_9", "items": [{"sku": "SKU-300", "quantity": 2}]},
    )
    assert status == 201
    assert order["total_cents"] == 28_078
    assert order["status"] == "placed"
    order_id = order["id"]

    # Stock dropped to 4: at/below threshold, so order.placed + inventory.low fired.
    status, fetched = _request(server, "GET", f"/v1/products/{product_id}")
    assert fetched["stock"] == 4
    assert server.events.count() == before + 2
    status, events = _request(server, "GET", "/v1/events?topic=inventory.low")
    assert any(e["key"] == product_id for e in events["events"])

    status, low = _request(server, "GET", "/v1/inventory/low-stock")
    assert status == 200
    assert any(p["id"] == product_id for p in low["products"])

    status, fulfilled = _request(server, "POST", f"/v1/orders/{order_id}/fulfill")
    assert status == 200 and fulfilled["status"] == "fulfilled"

    status, data = _request(server, "POST", f"/v1/orders/{order_id}/cancel")
    assert status == 400  # already fulfilled


def test_order_insufficient_stock_returns_400(server):
    _request(server, "POST", "/v1/products", _product(sku="SKU-400", stock=1))
    status, data = _request(
        server,
        "POST",
        "/v1/orders",
        {"customer_id": "cust_9", "items": [{"sku": "SKU-400", "quantity": 5}]},
    )
    assert status == 400
    assert "insufficient stock" in data["error"]


def test_product_validation_and_duplicate_return_400(server):
    status, data = _request(server, "POST", "/v1/products", _product(sku="bad sku"))
    assert status == 400
    _request(server, "POST", "/v1/products", _product(sku="SKU-500"))
    status, data = _request(server, "POST", "/v1/products", _product(sku="SKU-500"))
    assert status == 400
    assert "already exists" in data["error"]


def test_unknown_product_and_order_return_404(server):
    status, data = _request(server, "GET", "/v1/products/prd_999999")
    assert status == 404 and data["error"] == "product not found"
    status, data = _request(server, "GET", "/v1/orders/ord_999999")
    assert status == 404 and data["error"] == "order not found"


def test_restock_endpoint(server):
    _, product = _request(server, "POST", "/v1/products", _product(sku="SKU-600", stock=2))
    status, updated = _request(
        server, "POST", f"/v1/products/{product['id']}/restock", {"quantity": 3}
    )
    assert status == 200 and updated["stock"] == 5
    status, data = _request(
        server, "POST", f"/v1/products/{product['id']}/restock", {"quantity": 0}
    )
    assert status == 400
