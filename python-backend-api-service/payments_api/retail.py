"""Retail orders-and-inventory module for the backend API service.

Added for the Home Depot — Software Engineer 2 application: the same
service patterns as the loan checkout and the insurance module (REST
endpoints, strict validation, integer-cents money math, event publishing,
thread-safe stores) applied to a retail domain — a product catalog,
on-hand inventory, and customer orders that reserve stock.

Pure Python, standard library only. Domain rules:

- Every amount is integer cents; an order total is the line subtotal plus
  sales tax at a flat rate in basis points, rounded half-up to the cent.
- Placing an order reserves stock atomically: either every line can be
  filled from on-hand inventory and all stock counts drop, or the order
  is rejected and nothing changes.
- A placed order can be fulfilled (stock stays out) or cancelled (stock
  is returned). Terminal orders cannot change state again.
- When a reservation leaves a product at or below the low-stock
  threshold, the store reports it so the HTTP layer can publish an
  ``inventory.low`` event next to the ``order.placed`` event.
"""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass, field

from .models import LOAN_ID_RE, ValidationError

SKU_RE = re.compile(r"^[A-Z0-9][A-Z0-9-]{2,19}$")
TAX_RATE_BPS = 800  # flat 8% sales tax
LOW_STOCK_THRESHOLD = 5
MIN_PRICE_CENTS = 1
MAX_PRICE_CENTS = 100_000_00  # $100,000
MAX_STOCK = 1_000_000
MAX_LINES_PER_ORDER = 50
MAX_QTY_PER_LINE = 10_000


def validate_product(payload: dict) -> dict:
    """Validate a product-creation payload. Returns a cleaned dict or raises."""
    if not isinstance(payload, dict):
        raise ValidationError("request body must be a JSON object")
    sku = payload.get("sku")
    name = payload.get("name")
    price = payload.get("price_cents")
    stock = payload.get("stock")

    if not isinstance(sku, str) or not SKU_RE.match(sku):
        raise ValidationError("sku must be 3-20 chars of A-Z, 0-9 and '-'")
    if not isinstance(name, str) or not name.strip():
        raise ValidationError("name must be a non-empty string")
    if not isinstance(price, int) or isinstance(price, bool):
        raise ValidationError("price_cents must be an integer number of cents")
    if price < MIN_PRICE_CENTS or price > MAX_PRICE_CENTS:
        raise ValidationError("price_cents must be between 1 and 10000000")
    if not isinstance(stock, int) or isinstance(stock, bool):
        raise ValidationError("stock must be an integer")
    if stock < 0 or stock > MAX_STOCK:
        raise ValidationError("stock must be between 0 and 1000000")
    return {
        "sku": sku,
        "name": name.strip(),
        "price_cents": price,
        "stock": stock,
    }


def validate_order(payload: dict) -> dict:
    """Validate an order payload. Returns cleaned lines or raises.

    Only the shape is checked here; product existence and stock levels
    are checked by the store, which owns the inventory.
    """
    if not isinstance(payload, dict):
        raise ValidationError("request body must be a JSON object")
    customer_id = payload.get("customer_id")
    items = payload.get("items")
    if not isinstance(customer_id, str) or not LOAN_ID_RE.match(customer_id):
        raise ValidationError("customer_id must be a non-empty id string")
    if not isinstance(items, list) or not items:
        raise ValidationError("items must be a non-empty list")
    if len(items) > MAX_LINES_PER_ORDER:
        raise ValidationError("items must have at most 50 lines")
    lines = []
    seen_skus: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            raise ValidationError("each item must be an object")
        sku = item.get("sku")
        qty = item.get("quantity")
        if not isinstance(sku, str) or not SKU_RE.match(sku):
            raise ValidationError("each item sku must be 3-20 chars of A-Z, 0-9 and '-'")
        if sku in seen_skus:
            raise ValidationError(f"duplicate line for sku {sku}")
        seen_skus.add(sku)
        if not isinstance(qty, int) or isinstance(qty, bool):
            raise ValidationError("quantity must be an integer")
        if qty < 1 or qty > MAX_QTY_PER_LINE:
            raise ValidationError("quantity must be between 1 and 10000")
        lines.append({"sku": sku, "quantity": qty})
    return {"customer_id": customer_id, "items": lines}


def compute_tax_cents(subtotal_cents: int) -> int:
    """Sales tax on a subtotal, integer cents, rounded half-up."""
    return (subtotal_cents * TAX_RATE_BPS + 5_000) // 10_000


@dataclass
class Product:
    id: str
    sku: str
    name: str
    price_cents: int
    stock: int

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "sku": self.sku,
            "name": self.name,
            "price_cents": self.price_cents,
            "stock": self.stock,
        }


@dataclass
class OrderLine:
    sku: str
    quantity: int
    unit_price_cents: int

    @property
    def line_total_cents(self) -> int:
        return self.quantity * self.unit_price_cents

    def to_dict(self) -> dict:
        return {
            "sku": self.sku,
            "quantity": self.quantity,
            "unit_price_cents": self.unit_price_cents,
            "line_total_cents": self.line_total_cents,
        }


@dataclass
class Order:
    id: str
    customer_id: str
    lines: list[OrderLine] = field(default_factory=list)
    status: str = "placed"

    @property
    def subtotal_cents(self) -> int:
        return sum(line.line_total_cents for line in self.lines)

    @property
    def tax_cents(self) -> int:
        return compute_tax_cents(self.subtotal_cents)

    @property
    def total_cents(self) -> int:
        return self.subtotal_cents + self.tax_cents

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "customer_id": self.customer_id,
            "items": [line.to_dict() for line in self.lines],
            "subtotal_cents": self.subtotal_cents,
            "tax_cents": self.tax_cents,
            "total_cents": self.total_cents,
            "status": self.status,
        }


class RetailStore:
    """Thread-safe in-memory product catalog, inventory and order store."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._products: dict[str, Product] = {}
        self._by_sku: dict[str, Product] = {}
        self._orders: dict[str, Order] = {}
        self._product_counter = 0
        self._order_counter = 0

    # --- products ---

    def create_product(self, cleaned: dict) -> Product:
        with self._lock:
            if cleaned["sku"] in self._by_sku:
                raise ValidationError(f"sku {cleaned['sku']} already exists")
            self._product_counter += 1
            product = Product(id=f"prd_{self._product_counter:06d}", **cleaned)
            self._products[product.id] = product
            self._by_sku[product.sku] = product
            return product

    def get_product(self, product_id: str) -> Product | None:
        with self._lock:
            return self._products.get(product_id)

    def get_by_sku(self, sku: str) -> Product | None:
        with self._lock:
            return self._by_sku.get(sku)

    def product_count(self) -> int:
        with self._lock:
            return len(self._products)

    def restock(self, product: Product, quantity: int) -> Product:
        if not isinstance(quantity, int) or isinstance(quantity, bool):
            raise ValidationError("quantity must be an integer")
        if quantity < 1 or quantity > MAX_STOCK:
            raise ValidationError("quantity must be between 1 and 1000000")
        with self._lock:
            if product.stock + quantity > MAX_STOCK:
                raise ValidationError("restock would exceed the maximum stock level")
            product.stock += quantity
            return product

    def low_stock(self) -> list[Product]:
        with self._lock:
            return [p for p in self._products.values() if p.stock <= LOW_STOCK_THRESHOLD]

    # --- orders ---

    def place_order(self, cleaned: dict) -> tuple[Order, list[Product]]:
        """Reserve stock and create an order, atomically.

        Returns the order plus the products this reservation pushed to or
        below the low-stock threshold. Raises ValidationError — changing
        nothing — when a sku is unknown or stock is short.
        """
        with self._lock:
            products: list[Product] = []
            for line in cleaned["items"]:
                product = self._by_sku.get(line["sku"])
                if product is None:
                    raise ValidationError(f"unknown sku {line['sku']}")
                if line["quantity"] > product.stock:
                    raise ValidationError(
                        f"insufficient stock for sku {line['sku']}: "
                        f"{product.stock} on hand, {line['quantity']} requested"
                    )
                products.append(product)
            lines = []
            low: list[Product] = []
            for line, product in zip(cleaned["items"], products):
                before = product.stock
                product.stock -= line["quantity"]
                if before > LOW_STOCK_THRESHOLD >= product.stock:
                    low.append(product)
                lines.append(
                    OrderLine(
                        sku=product.sku,
                        quantity=line["quantity"],
                        unit_price_cents=product.price_cents,
                    )
                )
            self._order_counter += 1
            order = Order(
                id=f"ord_{self._order_counter:06d}",
                customer_id=cleaned["customer_id"],
                lines=lines,
            )
            self._orders[order.id] = order
            return order, low

    def get_order(self, order_id: str) -> Order | None:
        with self._lock:
            return self._orders.get(order_id)

    def order_count(self) -> int:
        with self._lock:
            return len(self._orders)

    def fulfill_order(self, order: Order) -> Order:
        with self._lock:
            if order.status != "placed":
                raise ValidationError(f"order {order.id} is {order.status}, not placed")
            order.status = "fulfilled"
            return order

    def cancel_order(self, order: Order) -> Order:
        """Cancel a placed order and return its stock to the shelves."""
        with self._lock:
            if order.status != "placed":
                raise ValidationError(f"order {order.id} is {order.status}, not placed")
            for line in order.lines:
                self._by_sku[line.sku].stock += line.quantity
            order.status = "cancelled"
            return order
