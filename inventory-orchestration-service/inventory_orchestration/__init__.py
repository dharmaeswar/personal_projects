"""Inventory Orchestration Service — event-driven, full-stack demo.

A small multi-warehouse inventory orchestration service: a REST API plus a
browser dashboard, with every stock movement published as a validated event
on an in-process bus that models the Kafka topics of a production design
(``inventory.reserved``, ``inventory.released``, ``inventory.allocated``,
``order.fulfilled``, ``order.backordered``).

Demo project. Synthetic data only. No real retailer, warehouse, or order
history is involved, and nothing here is a production deployment.
"""

from .events import EventBus, EventValidationError
from .service import InventoryService
from .store import Store, demo_store

__all__ = [
    "EventBus",
    "EventValidationError",
    "InventoryService",
    "Store",
    "demo_store",
]
