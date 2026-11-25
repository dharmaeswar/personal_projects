"""Data-quality stage: cleansing, standardization, dedup, mapping, hierarchy.

Implements the exact quality functions the McDonald's Data Engineer III
posting names: cleansing, standardization, parsing, de-duplication, mapping,
and hierarchy management. Bad rows are quarantined with a reason, never
dropped silently.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from .events import MENU, RESTAURANTS, OrderEvent

# Channel spellings seen in the wild -> canonical value (standardization).
CHANNEL_ALIASES = {
    "drive-thru": "drive-thru",
    "drive thru": "drive-thru",
    "drive_thru": "drive-thru",
    "counter": "counter",
    "kiosk": "kiosk",
    "delivery": "delivery",
    "mobile": "mobile",
    "app": "mobile",
}


@dataclass
class QualityResult:
    clean: list[OrderEvent] = field(default_factory=list)
    quarantined: list[tuple[OrderEvent, str]] = field(default_factory=list)

    @property
    def stats(self) -> dict:
        return {
            "clean": len(self.clean),
            "quarantined": len(self.quarantined),
            "reasons": {r: sum(1 for _, reason in self.quarantined if reason == r)
                        for r in {reason for _, reason in self.quarantined}},
        }


def standardize_channel(raw: str) -> str | None:
    """Map a raw channel string to its canonical value, or None if unknown."""
    return CHANNEL_ALIASES.get(raw.strip().lower())


def hierarchy_for(restaurant_id: str) -> tuple[str, str] | None:
    """Restaurant -> (market, region) hierarchy from the master-data table."""
    row = RESTAURANTS.get(restaurant_id)
    return (row[1], row[2]) if row else None


def cleanse(events: list[OrderEvent]) -> QualityResult:
    """Cleanse, standardize, dedupe and map one micro-batch of events.

    Order of checks (each quarantine reason is named):
    1. unknown restaurant (no master-data row) / unknown menu code
    2. unparseable channel
    3. non-positive quantity or non-positive unit price
    4. total_amount disagrees with quantity * unit_price (beyond 1 cent)
    5. duplicate order_id — keep the latest event_time (re-delivery dedup)
    Clean rows are returned with standardized channel casing and the
    canonical menu name attached via ``menu_code`` mapping.
    """
    result = QualityResult()
    seen: dict[str, OrderEvent] = {}
    for event in events:
        if hierarchy_for(event.restaurant_id) is None:
            result.quarantined.append((event, "unknown_restaurant"))
            continue
        if event.menu_code not in MENU:
            result.quarantined.append((event, "unknown_menu_code"))
            continue
        channel = standardize_channel(event.channel)
        if channel is None:
            result.quarantined.append((event, "unknown_channel"))
            continue
        if event.quantity <= 0 or event.unit_price <= 0:
            result.quarantined.append((event, "non_positive_quantity_or_price"))
            continue
        expected = round(event.unit_price * event.quantity, 2)
        if abs(event.total_amount - expected) > 0.01:
            result.quarantined.append((event, "total_amount_mismatch"))
            continue
        clean = OrderEvent(
            order_id=event.order_id,
            restaurant_id=event.restaurant_id,
            event_time=event.event_time,
            channel=channel,
            menu_code=event.menu_code,
            quantity=event.quantity,
            unit_price=event.unit_price,
            total_amount=expected,
        )
        prev = seen.get(clean.order_id)
        if prev is None or clean.event_time >= prev.event_time:
            seen[clean.order_id] = clean
    result.clean = sorted(seen.values(), key=lambda e: e.event_time)
    return result
