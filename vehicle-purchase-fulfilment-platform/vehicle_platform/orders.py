"""Order lifecycle and pricing for an online vehicle purchase.

States: RESERVED -> INSPECTED -> FINANCED -> DELIVERY_SCHEDULED ->
DELIVERED. CANCELLED is reachable from any state except DELIVERED.
Pricing uses Decimal and integer cents throughout; no floats touch
money.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
import re

STATES = (
    "RESERVED",
    "INSPECTED",
    "FINANCED",
    "DELIVERY_SCHEDULED",
    "DELIVERED",
    "CANCELLED",
)

# Legal forward transitions. CANCELLED is handled separately.
TRANSITIONS = {
    "RESERVED": {"INSPECTED"},
    "INSPECTED": {"FINANCED"},
    "FINANCED": {"DELIVERY_SCHEDULED"},
    "DELIVERY_SCHEDULED": {"DELIVERED"},
    "DELIVERED": set(),
    "CANCELLED": set(),
}

DOC_FEE_CENTS = 59_900  # $599 documentation fee
DELIVERY_FEE_CENTS = 19_900  # $199 flat delivery fee

# State sales-tax rates used by the demo (real rates change; these are
# the rates the demo documents and tests pin).
TAX_RATES = {
    "AZ": Decimal("0.081"),
    "NY": Decimal("0.04"),
    "TX": Decimal("0.0625"),
    "CA": Decimal("0.0725"),
}

VIN_RE = re.compile(r"^[A-HJ-NPR-Z0-9]{17}$")  # 17 chars, no I/O/Q
ZIP_RE = re.compile(r"^\d{5}$")


class OrderError(ValueError):
    """Raised for invalid orders, transitions, or pricing inputs."""


@dataclass
class Order:
    order_id: str
    vin: str
    customer_id: str
    list_price_cents: int
    state_code: str
    delivery_zip: str
    status: str = "RESERVED"
    events_applied: int = 0

    def advance(self, to_state: str) -> None:
        """Move the order to the next lifecycle state, or raise."""
        if to_state == "CANCELLED":
            if self.status == "DELIVERED":
                raise OrderError("a delivered order cannot be cancelled")
            self.status = "CANCELLED"
            return
        if to_state not in TRANSITIONS.get(self.status, set()):
            raise OrderError(
                f"cannot move order from {self.status} to {to_state}"
            )
        self.status = to_state

    def total_cents(self) -> int:
        """List price + doc fee + delivery fee + sales tax on price+doc."""
        rate = TAX_RATES.get(self.state_code)
        if rate is None:
            raise OrderError(f"no tax rate configured for {self.state_code}")
        taxable = self.list_price_cents + DOC_FEE_CENTS
        tax = (Decimal(taxable) * rate).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
        return (
            self.list_price_cents
            + DOC_FEE_CENTS
            + DELIVERY_FEE_CENTS
            + int(tax)
        )

    def to_dict(self) -> dict:
        return {
            "order_id": self.order_id,
            "vin": self.vin,
            "customer_id": self.customer_id,
            "list_price_cents": self.list_price_cents,
            "state_code": self.state_code,
            "delivery_zip": self.delivery_zip,
            "status": self.status,
            "total_cents": self.total_cents(),
        }


def validate_new_order(payload: dict) -> Order:
    """Validate a create-order payload and build the Order, or raise."""
    order_id = payload.get("order_id", "")
    vin = payload.get("vin", "")
    customer_id = payload.get("customer_id", "")
    price = payload.get("list_price_cents")
    state_code = payload.get("state_code", "")
    delivery_zip = payload.get("delivery_zip", "")
    if not isinstance(order_id, str) or not order_id.strip():
        raise OrderError("order_id is required")
    if not isinstance(vin, str) or not VIN_RE.match(vin):
        raise OrderError("vin must be a 17-character VIN (no I, O, or Q)")
    if not isinstance(customer_id, str) or not customer_id.strip():
        raise OrderError("customer_id is required")
    if not isinstance(price, int) or isinstance(price, bool) or price <= 0:
        raise OrderError("list_price_cents must be a positive integer")
    if state_code not in TAX_RATES:
        raise OrderError(f"unsupported state_code: {state_code!r}")
    if not isinstance(delivery_zip, str) or not ZIP_RE.match(delivery_zip):
        raise OrderError("delivery_zip must be a 5-digit ZIP code")
    return Order(
        order_id=order_id.strip(),
        vin=vin,
        customer_id=customer_id.strip(),
        list_price_cents=price,
        state_code=state_code,
        delivery_zip=delivery_zip,
    )


def rebuild_from_events(order_id: str, events: list[dict]) -> Order | None:
    """Replay order events (in offset order) into the current Order.

    Each event carries the full order snapshot at that point, so replay
    is a fold over the snapshots; the function also verifies the
    transition sequence is legal.
    """
    order = None
    for event in events:
        payload = event["payload"]
        if order is None:
            order = Order(
                order_id=payload["order_id"],
                vin=payload["vin"],
                customer_id=payload["customer_id"],
                list_price_cents=payload["list_price_cents"],
                state_code=payload["state_code"],
                delivery_zip=payload["delivery_zip"],
                status="RESERVED",
            )
        else:
            order.advance(payload["status"])
        order.events_applied += 1
    if order is not None and order.order_id != order_id:
        raise OrderError("event log contains a different order id")
    return order
