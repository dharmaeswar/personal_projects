"""Service-level tests: allocation, fulfilment, cancellation, idempotency."""

import pytest

from inventory_orchestration.events import EventBus
from inventory_orchestration.service import InventoryService, OrderError
from inventory_orchestration.store import demo_store


def make_service():
    return InventoryService(store=demo_store(), bus=EventBus())


def test_allocates_cheapest_warehouse_first():
    svc = make_service()
    order = svc.create_order("SKU-1001", 100)
    assert order["status"] == "allocated"
    assert order["allocations"] == [{"warehouse": "DAL", "qty": 100}]
    assert svc.store.available("SKU-1001", "DAL") == 20


def test_splits_across_warehouses_when_one_is_short():
    svc = make_service()
    order = svc.create_order("SKU-1001", 150)
    assert order["status"] == "allocated"
    assert order["allocations"] == [
        {"warehouse": "DAL", "qty": 120},
        {"warehouse": "FTW", "qty": 30},
    ]


def test_backorders_the_shortfall_and_keeps_partial_allocation():
    svc = make_service()
    order = svc.create_order("SKU-1004", 100)
    assert order["status"] == "backordered"
    assert order["allocated_qty"] == 40
    topics = [e["topic"] for e in svc.bus.events()]
    assert "order.backordered" in topics
    assert topics.count("inventory.reserved") == 2


def test_zero_stock_order_backorders_with_no_reservation_events():
    svc = make_service()
    svc.store.set_stock("SKU-1002", "DAL", 0)
    svc.store.set_stock("SKU-1002", "FTW", 0)
    order = svc.create_order("SKU-1002", 5)
    assert order["status"] == "backordered"
    assert order["allocated_qty"] == 0
    assert order["allocations"] == []
    assert "inventory.allocated" not in [e["topic"] for e in svc.bus.events()]


def test_fulfil_consumes_reservation_and_stock():
    svc = make_service()
    order = svc.create_order("SKU-1002", 50)
    done = svc.fulfill_order(order["order_id"])
    assert done["status"] == "fulfilled"
    assert svc.store.stock[("SKU-1002", "DAL")] == 150
    assert svc.store.reserved[("SKU-1002", "DAL")] == 0


def test_cancel_returns_stock_to_available():
    svc = make_service()
    order = svc.create_order("SKU-1003", 10)
    svc.cancel_order(order["order_id"])
    assert svc.store.available("SKU-1003", "DAL") == 45
    assert svc.store.reserved[("SKU-1003", "DAL")] == 0


def test_fulfil_after_cancel_is_rejected():
    svc = make_service()
    order = svc.create_order("SKU-1003", 10)
    svc.cancel_order(order["order_id"])
    with pytest.raises(OrderError):
        svc.fulfill_order(order["order_id"])


def test_repeat_idempotency_key_returns_original_order():
    svc = make_service()
    first = svc.create_order("SKU-1001", 10, idempotency_key="key-1")
    second = svc.create_order("SKU-1001", 10, idempotency_key="key-1")
    assert first["order_id"] == second["order_id"]
    assert svc.store.available("SKU-1001", "DAL") == 110  # reserved only once


def test_unknown_sku_and_bad_qty_rejected():
    svc = make_service()
    with pytest.raises(OrderError):
        svc.create_order("SKU-9999", 1)
    with pytest.raises(OrderError):
        svc.create_order("SKU-1001", 0)
    with pytest.raises(OrderError):
        svc.create_order("SKU-1001", -3)


def test_restock_adds_stock_and_publishes_event():
    svc = make_service()
    out = svc.restock("SKU-1004", "HOU", 10)
    assert out["on_hand"] == 10
    assert svc.bus.events(topic="inventory.restocked")[0]["payload"]["qty"] == 10
