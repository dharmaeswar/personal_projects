"""Tests for SQLite order store and JSON vehicle document store."""

from vehicle_platform.orders import validate_new_order
from vehicle_platform.store import OrderStore, VehicleDocStore

GOOD = {
    "order_id": "ORD-1",
    "vin": "1HGCM82633A004352",
    "customer_id": "CUST-1",
    "list_price_cents": 2_450_000,
    "state_code": "AZ",
    "delivery_zip": "85281",
}

VEHICLE = {
    "vin": "1HGCM82633A004352", "make": "Honda", "model": "Civic",
    "year": 2021, "mileage": 28410, "list_price_cents": 2_450_000,
    "status": "AVAILABLE", "features": ["backup camera"],
}


def test_order_round_trip(tmp_path):
    store = OrderStore(tmp_path / "orders.db")
    order = validate_new_order(dict(GOOD))
    store.save_order(order)
    loaded = store.get_order("ORD-1")
    assert loaded is not None
    assert loaded.vin == GOOD["vin"]
    assert loaded.status == "RESERVED"
    assert loaded.total_cents() == 2_733_102
    store.close()


def test_order_status_update_persists(tmp_path):
    store = OrderStore(tmp_path / "orders.db")
    order = validate_new_order(dict(GOOD))
    store.save_order(order)
    order.advance("INSPECTED")
    store.save_order(order)
    assert store.get_order("ORD-1").status == "INSPECTED"
    store.close()


def test_list_orders_filters_by_customer(tmp_path):
    store = OrderStore(tmp_path / "orders.db")
    store.save_order(validate_new_order(dict(GOOD)))
    store.save_order(validate_new_order(dict(GOOD, order_id="ORD-2",
                                             customer_id="CUST-2")))
    assert len(store.list_orders()) == 2
    mine = store.list_orders("CUST-1")
    assert len(mine) == 1 and mine[0].order_id == "ORD-1"
    store.close()


def test_unknown_order_returns_none(tmp_path):
    store = OrderStore(tmp_path / "orders.db")
    assert store.get_order("NOPE") is None
    store.close()


def test_payment_saved(tmp_path):
    store = OrderStore(tmp_path / "orders.db")
    store.save_order(validate_new_order(dict(GOOD)))
    store.save_payment("PAY-1", "ORD-1", 2_733_102, "card")
    rows = store._conn.execute("SELECT amount_cents FROM payments").fetchall()
    assert rows == [(2_733_102,)]
    store.close()


def test_vehicle_doc_round_trip(tmp_path):
    docs = VehicleDocStore(tmp_path / "vehicles")
    docs.put_vehicle(dict(VEHICLE))
    loaded = docs.get_vehicle(VEHICLE["vin"])
    assert loaded["make"] == "Honda"
    assert loaded["features"] == ["backup camera"]
    assert docs.get_vehicle("UNKNOWNVIN00000001") is None


def test_mark_reserved_updates_doc(tmp_path):
    docs = VehicleDocStore(tmp_path / "vehicles")
    docs.put_vehicle(dict(VEHICLE))
    updated = docs.mark_reserved(VEHICLE["vin"], "ORD-1")
    assert updated["status"] == "RESERVED"
    assert updated["order_id"] == "ORD-1"
    assert docs.get_vehicle(VEHICLE["vin"])["status"] == "RESERVED"


def test_list_vehicles(tmp_path):
    docs = VehicleDocStore(tmp_path / "vehicles")
    docs.put_vehicle(dict(VEHICLE))
    docs.put_vehicle(dict(VEHICLE, vin="5YJSA1E26CFF00001", make="Tesla"))
    assert [d["make"] for d in docs.list_vehicles()] == ["Honda", "Tesla"]
