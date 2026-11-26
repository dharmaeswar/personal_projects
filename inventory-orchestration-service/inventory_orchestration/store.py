"""In-memory store: SKUs, warehouses, stock levels, reservations, orders.

Stock is tracked per (SKU, warehouse). A reservation holds units for an
order without removing them from the warehouse; fulfilment consumes the
reservation, cancellation returns the units to available stock. All numbers
are synthetic demo data.
"""

WAREHOUSES = {
    # Shipping cost per unit ranks warehouses for allocation: cheapest first.
    "DAL": {"name": "Dallas DC", "region": "North Texas", "ship_cost": 2},
    "FTW": {"name": "Fort Worth DC", "region": "North Texas", "ship_cost": 3},
    "HOU": {"name": "Houston DC", "region": "Southeast Texas", "ship_cost": 5},
}

SKUS = {
    "SKU-1001": {"name": "Wireless headset", "price": 79},
    "SKU-1002": {"name": "USB-C hub", "price": 49},
    "SKU-1003": {"name": "Mechanical keyboard", "price": 129},
    "SKU-1004": {"name": "27in monitor", "price": 249},
}


class Store:
    """Holds stock, reservations and orders. Not thread-safe on its own;
    the service layer serialises access."""

    def __init__(self, warehouses=None, skus=None):
        self.warehouses = dict(warehouses or WAREHOUSES)
        self.skus = dict(skus or SKUS)
        self.stock = {}  # (sku, warehouse) -> available units
        self.reserved = {}  # (sku, warehouse) -> reserved units
        self.orders = {}  # order_id -> order dict
        self._order_seq = 0
        self._idempotency = {}  # idempotency key -> order_id

    def set_stock(self, sku, warehouse, qty):
        if sku not in self.skus:
            raise KeyError(f"unknown sku: {sku}")
        if warehouse not in self.warehouses:
            raise KeyError(f"unknown warehouse: {warehouse}")
        if qty < 0:
            raise ValueError("stock cannot be negative")
        self.stock[(sku, warehouse)] = qty
        self.reserved.setdefault((sku, warehouse), 0)

    def available(self, sku, warehouse):
        return self.stock.get((sku, warehouse), 0) - self.reserved.get((sku, warehouse), 0)

    def next_order_id(self):
        self._order_seq += 1
        return f"ORD-{self._order_seq:05d}"

    def record_idempotency(self, key, order_id):
        self._idempotency[key] = order_id

    def order_for_key(self, key):
        order_id = self._idempotency.get(key)
        return self.orders.get(order_id) if order_id else None

    def inventory_view(self):
        """One row per SKU/warehouse for the dashboard and the API."""
        rows = []
        for sku in sorted(self.skus):
            for code in sorted(self.warehouses):
                rows.append(
                    {
                        "sku": sku,
                        "name": self.skus[sku]["name"],
                        "warehouse": code,
                        "available": self.available(sku, code),
                        "reserved": self.reserved.get((sku, code), 0),
                        "on_hand": self.stock.get((sku, code), 0),
                    }
                )
        return rows


def demo_store():
    """Seeded store: the four demo SKUs spread across the three DCs."""
    store = Store()
    seed = {
        ("SKU-1001", "DAL"): 120,
        ("SKU-1001", "FTW"): 60,
        ("SKU-1001", "HOU"): 40,
        ("SKU-1002", "DAL"): 200,
        ("SKU-1002", "FTW"): 90,
        ("SKU-1003", "DAL"): 45,
        ("SKU-1003", "HOU"): 30,
        ("SKU-1004", "DAL"): 25,
        ("SKU-1004", "FTW"): 15,
    }
    for (sku, warehouse), qty in seed.items():
        store.set_stock(sku, warehouse, qty)
    return store
