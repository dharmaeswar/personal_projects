"""Orchestration logic: reserve, allocate, fulfil, cancel, restock.

An order is allocated cheapest-warehouse-first across the DCs, so a single
order can split across warehouses. Every stock movement is published on the
event bus, so downstream services (shipping, billing, replenishment) can
react without calling this service. A repeated request with the same
idempotency key returns the original order instead of reserving twice.
"""

import threading

from .events import EventBus
from .store import Store


class OrderError(ValueError):
    """Raised for bad order requests (unknown SKU, bad quantity, bad state)."""


class InventoryService:
    def __init__(self, store=None, bus=None):
        self.store = store or Store()
        self.bus = bus or EventBus()
        self._lock = threading.Lock()

    # -- helpers ---------------------------------------------------------
    def _warehouses_by_cost(self, preferred=None):
        codes = sorted(
            self.store.warehouses,
            key=lambda c: self.store.warehouses[c]["ship_cost"],
        )
        if preferred in codes:
            codes.remove(preferred)
            codes.insert(0, preferred)
        return codes

    # -- orders ----------------------------------------------------------
    def create_order(self, sku, qty, idempotency_key=None, warehouse=None):
        """Reserve stock for a new order; returns the order dict."""
        if sku not in self.store.skus:
            raise OrderError(f"unknown sku: {sku}")
        if not isinstance(qty, int) or isinstance(qty, bool) or qty <= 0:
            raise OrderError(f"qty must be a positive int, got {qty!r}")
        if warehouse is not None and warehouse not in self.store.warehouses:
            raise OrderError(f"unknown warehouse: {warehouse}")
        with self._lock:
            if idempotency_key:
                existing = self.store.order_for_key(idempotency_key)
                if existing is not None:
                    return dict(existing)
            order_id = self.store.next_order_id()
            remaining, allocations = qty, []
            for code in self._warehouses_by_cost(warehouse):
                if remaining == 0:
                    break
                take = min(self.store.available(sku, code), remaining)
                if take:
                    key = (sku, code)
                    self.store.reserved[key] = self.store.reserved.get(key, 0) + take
                    allocations.append({"warehouse": code, "qty": take})
                    remaining -= take
                    self.bus.publish(
                        "inventory.reserved",
                        {"order_id": order_id, "sku": sku, "warehouse": code, "qty": take},
                    )
            allocated = qty - remaining
            status = "allocated" if remaining == 0 else "backordered"
            order = {
                "order_id": order_id,
                "sku": sku,
                "qty": qty,
                "allocated_qty": allocated,
                "allocations": allocations,
                "status": status,
            }
            self.store.orders[order_id] = order
            if idempotency_key:
                self.store.record_idempotency(idempotency_key, order_id)
            if allocated:
                self.bus.publish(
                    "inventory.allocated",
                    {
                        "order_id": order_id,
                        "sku": sku,
                        "allocations": [dict(a) for a in allocations],
                        "total_qty": allocated,
                    },
                )
            if remaining:
                self.bus.publish(
                    "order.backordered",
                    {"order_id": order_id, "sku": sku, "qty": qty, "short_qty": remaining},
                )
            return dict(order)

    def fulfill_order(self, order_id):
        """Consume the reservation and mark the order fulfilled."""
        with self._lock:
            order = self.store.orders.get(order_id)
            if order is None:
                raise OrderError(f"unknown order: {order_id}")
            if order["status"] not in ("allocated", "backordered"):
                raise OrderError(f"order {order_id} is {order['status']}, cannot fulfil")
            if order["allocated_qty"] == 0:
                raise OrderError(f"order {order_id} has nothing allocated to fulfil")
            for alloc in order["allocations"]:
                key = (order["sku"], alloc["warehouse"])
                self.store.reserved[key] -= alloc["qty"]
                self.store.stock[key] -= alloc["qty"]
            order["status"] = "fulfilled"
            self.bus.publish(
                "order.fulfilled",
                {"order_id": order_id, "sku": order["sku"], "qty": order["allocated_qty"]},
            )
            return dict(order)

    def cancel_order(self, order_id):
        """Return reserved units to available stock and cancel the order."""
        with self._lock:
            order = self.store.orders.get(order_id)
            if order is None:
                raise OrderError(f"unknown order: {order_id}")
            if order["status"] not in ("allocated", "backordered"):
                raise OrderError(f"order {order_id} is {order['status']}, cannot cancel")
            for alloc in order["allocations"]:
                key = (order["sku"], alloc["warehouse"])
                self.store.reserved[key] -= alloc["qty"]
                self.bus.publish(
                    "inventory.released",
                    {
                        "order_id": order_id,
                        "sku": order["sku"],
                        "warehouse": alloc["warehouse"],
                        "qty": alloc["qty"],
                    },
                )
            order["status"] = "cancelled"
            self.bus.publish("order.cancelled", {"order_id": order_id})
            return dict(order)

    def restock(self, sku, warehouse, qty):
        """Add units to a warehouse and publish the restock event."""
        if sku not in self.store.skus:
            raise OrderError(f"unknown sku: {sku}")
        if warehouse not in self.store.warehouses:
            raise OrderError(f"unknown warehouse: {warehouse}")
        if not isinstance(qty, int) or isinstance(qty, bool) or qty <= 0:
            raise OrderError(f"qty must be a positive int, got {qty!r}")
        with self._lock:
            key = (sku, warehouse)
            self.store.stock[key] = self.store.stock.get(key, 0) + qty
            self.store.reserved.setdefault(key, 0)
            self.bus.publish(
                "inventory.restocked", {"sku": sku, "warehouse": warehouse, "qty": qty}
            )
            return {"sku": sku, "warehouse": warehouse, "on_hand": self.store.stock[key]}

    def list_orders(self):
        with self._lock:
            return [dict(o) for o in self.store.orders.values()]
