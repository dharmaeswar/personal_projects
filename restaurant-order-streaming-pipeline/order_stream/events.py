"""Synthetic restaurant order events and a Kafka-modelled streaming topic.

All data is synthetic and seeded. No real McDonald's order, restaurant, or
customer data is used, and nothing here describes a real restaurant system.

The topic mirrors Apache Kafka: events are partitioned by restaurant_id,
each partition keeps offsets in order, and consumer groups track committed
offsets per partition. It runs in memory; no Kafka broker is needed.
"""
from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta

CHANNELS = ("drive-thru", "counter", "kiosk", "delivery", "mobile")
MENU = {
    "M001": ("Classic Burger", 5.99),
    "M002": ("Cheeseburger", 6.49),
    "M003": ("Chicken Sandwich", 6.99),
    "M004": ("Fries Medium", 3.49),
    "M005": ("Soft Drink Large", 2.49),
    "M006": ("McNuggets 10pc", 5.49),
    "M007": ("Salad Bowl", 7.29),
    "M008": ("Coffee", 1.99),
}
RESTAURANTS = {
    "R1001": ("Chicago Downtown", "Chicago", "Midwest"),
    "R1002": ("Chicago O'Hare", "Chicago", "Midwest"),
    "R1003": ("Naperville", "Chicago", "Midwest"),
    "R1004": ("Austin North", "Austin", "South"),
    "R1005": ("Dallas Central", "Dallas", "South"),
}


@dataclass(frozen=True)
class OrderEvent:
    """One restaurant order event as it arrives on the stream."""

    order_id: str
    restaurant_id: str
    event_time: datetime
    channel: str
    menu_code: str
    quantity: int
    unit_price: float
    total_amount: float
    currency: str = "USD"

    @property
    def partition_key(self) -> str:
        return self.restaurant_id


def seed_events(n: int = 120, seed: int = 7) -> list[OrderEvent]:
    """Generate ``n`` deterministic synthetic order events.

    The seed plants realistic mess on purpose: a few duplicate order_ids
    (re-delivered events), a few late events, a couple of bad rows (negative
    quantity, unknown menu code, unparseable channel casing) that the
    quality stage must quarantine.
    """
    rng = random.Random(seed)
    base = datetime(2026, 11, 20, 11, 0, 0)
    events: list[OrderEvent] = []
    rest_ids = list(RESTAURANTS)
    codes = list(MENU)
    for i in range(n):
        rid = rng.choice(rest_ids)
        code = rng.choice(codes)
        name, price = MENU[code]
        qty = rng.randint(1, 4)
        event_time = base + timedelta(minutes=i * 2, seconds=rng.randint(0, 59))
        events.append(
            OrderEvent(
                order_id=f"ORD-{10000 + i}",
                restaurant_id=rid,
                event_time=event_time,
                channel=rng.choice(CHANNELS),
                menu_code=code,
                quantity=qty,
                unit_price=price,
                total_amount=round(price * qty, 2),
            )
        )
    # Arrival order is event-time order, as in a live stream. Planted mess
    # is appended in arrival order: 3 re-delivered duplicates mid-stream,
    # 2 late events that arrive at the end (delayed 3 hours in transit),
    # 3 bad rows that the quality stage must quarantine.
    for pos, dup in ((6, events[5]), (41, events[40]), (91, events[90])):
        events.insert(pos, dup)
    for late in (events[10], events[60]):
        events.append(
            OrderEvent(**{**late.__dict__, "event_time": late.event_time - timedelta(hours=3)})
        )
    events.append(
        OrderEvent("ORD-19991", "R1001", base + timedelta(minutes=238), "drive-thru",
                   "M001", -2, 5.99, -11.98)
    )
    events.append(
        OrderEvent("ORD-19992", "R1002", base + timedelta(minutes=240), "DRIVE-THRU",
                   "M999", 1, 0.0, 0.0)
    )
    events.append(
        OrderEvent("ORD-19993", "R1003", base + timedelta(minutes=242), "counter",
                   "M004", 1, 3.49, 999.99)  # total disagrees with qty * price
    )
    return events


class KafkaTopic:
    """In-memory Kafka-style topic: partitions, offsets, consumer groups.

    Mirrors the Kafka model, not a broker: ``produce`` appends to the
    partition chosen by hashing the key, ``poll`` reads from a consumer
    group's committed offset, ``commit`` advances it.
    """

    def __init__(self, name: str, partitions: int = 4):
        self.name = name
        self.partitions = partitions
        self._log: dict[int, list[OrderEvent]] = {p: [] for p in range(partitions)}
        self._global: list[OrderEvent] = []  # production order across partitions
        self._committed: dict[str, int] = {}  # consumer group -> global offset

    def partition_for(self, key: str) -> int:
        return int(hashlib.md5(key.encode()).hexdigest(), 16) % self.partitions

    def produce(self, event: OrderEvent) -> tuple[int, int]:
        p = self.partition_for(event.partition_key)
        self._log[p].append(event)
        self._global.append(event)
        return p, len(self._log[p]) - 1

    def poll(self, group: str, max_records: int = 50) -> list[OrderEvent]:
        offset = self._committed.get(group, 0)
        return self._global[offset:offset + max_records]

    def commit(self, group: str, consumed: list[OrderEvent]) -> None:
        if not consumed:
            return
        last = consumed[-1]
        self._committed[group] = self._global.index(last) + 1

    def lag(self, group: str) -> int:
        return len(self._global) - self._committed.get(group, 0)
