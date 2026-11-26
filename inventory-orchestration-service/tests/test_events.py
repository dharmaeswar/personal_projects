"""Event-bus tests: schema enforcement, ordering, replay, subscriptions."""

import pytest

from inventory_orchestration.events import EventBus, EventValidationError


def test_publish_assigns_sequence_numbers_in_order():
    bus = EventBus()
    first = bus.publish("inventory.reserved",
                        {"order_id": "ORD-1", "sku": "SKU-1001", "warehouse": "DAL", "qty": 5})
    second = bus.publish("inventory.reserved",
                         {"order_id": "ORD-1", "sku": "SKU-1001", "warehouse": "FTW", "qty": 2})
    assert first["seq"] == 1 and second["seq"] == 2
    assert len(bus) == 2


def test_missing_field_is_rejected_and_nothing_is_logged():
    bus = EventBus()
    with pytest.raises(EventValidationError):
        bus.publish("inventory.reserved",
                    {"order_id": "ORD-1", "sku": "SKU-1001", "warehouse": "DAL"})
    assert len(bus) == 0


def test_non_positive_qty_is_rejected():
    bus = EventBus()
    with pytest.raises(EventValidationError):
        bus.publish("inventory.reserved",
                    {"order_id": "ORD-1", "sku": "SKU-1001", "warehouse": "DAL", "qty": 0})


def test_unknown_topic_and_unknown_fields_rejected():
    bus = EventBus()
    with pytest.raises(EventValidationError):
        bus.publish("payments.charged", {"order_id": "ORD-1"})
    with pytest.raises(EventValidationError):
        bus.publish("order.cancelled", {"order_id": "ORD-1", "reason": "nope"})


def test_subscriber_receives_only_its_topic():
    bus = EventBus()
    seen = []
    bus.subscribe("order.fulfilled", lambda e: seen.append(e["payload"]["order_id"]))
    bus.publish("order.fulfilled", {"order_id": "ORD-7", "sku": "SKU-1001", "qty": 3})
    bus.publish("order.cancelled", {"order_id": "ORD-8"})
    assert seen == ["ORD-7"]


def test_replay_from_a_sequence_number():
    bus = EventBus()
    for i in range(3):
        bus.publish("inventory.restocked",
                    {"sku": "SKU-1001", "warehouse": "DAL", "qty": i + 1})
    replayed = bus.events(after=1)
    assert [e["seq"] for e in replayed] == [2, 3]
    assert bus.events(topic="order.cancelled") == []
