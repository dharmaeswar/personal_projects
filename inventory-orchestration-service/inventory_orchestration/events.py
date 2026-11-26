"""Validated event bus modelling the Kafka topics of the service.

Each topic has a schema (required fields and their types), the way a Schema
Registry enforces contracts in production. Publishing an event that breaks
its schema raises :class:`EventValidationError` and publishes nothing, so a
bad producer can never corrupt the log. The log is append-only and every
event carries a sequence number, so consumers can replay from any point.
"""

import threading
import time

TOPIC_SCHEMAS = {
    "inventory.reserved": {"order_id": str, "sku": str, "warehouse": str, "qty": int},
    "inventory.released": {"order_id": str, "sku": str, "warehouse": str, "qty": int},
    "inventory.allocated": {"order_id": str, "sku": str, "allocations": list, "total_qty": int},
    "inventory.restocked": {"sku": str, "warehouse": str, "qty": int},
    "order.fulfilled": {"order_id": str, "sku": str, "qty": int},
    "order.backordered": {"order_id": str, "sku": str, "qty": int, "short_qty": int},
    "order.cancelled": {"order_id": str},
}


class EventValidationError(ValueError):
    """Raised when an event payload breaks its topic schema."""


def validate(topic, payload):
    """Check *payload* against the schema for *topic*; raise on any break."""
    schema = TOPIC_SCHEMAS.get(topic)
    if schema is None:
        raise EventValidationError(f"unknown topic: {topic!r}")
    if not isinstance(payload, dict):
        raise EventValidationError(f"payload for {topic!r} must be a dict")
    for field, kind in schema.items():
        if field not in payload:
            raise EventValidationError(f"{topic!r} event missing field: {field}")
        value = payload[field]
        if kind is int:
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise EventValidationError(
                    f"{topic!r} field {field} must be a positive int, got {value!r}"
                )
        elif not isinstance(value, kind):
            raise EventValidationError(
                f"{topic!r} field {field} must be {kind.__name__}, got {type(value).__name__}"
            )
    extra = set(payload) - set(schema)
    if extra:
        raise EventValidationError(f"{topic!r} event has unknown fields: {sorted(extra)}")


class EventBus:
    """Thread-safe, append-only event log with topic subscriptions."""

    def __init__(self):
        self._log = []
        self._subscribers = {}
        self._lock = threading.Lock()
        self._seq = 0

    def publish(self, topic, payload):
        """Validate and append an event; notify subscribers; return the event."""
        validate(topic, payload)
        with self._lock:
            self._seq += 1
            event = {
                "seq": self._seq,
                "topic": topic,
                "payload": dict(payload),
                "ts": time.time(),
            }
            self._log.append(event)
            handlers = list(self._subscribers.get(topic, []))
        for handler in handlers:
            handler(event)
        return event

    def subscribe(self, topic, handler):
        """Register *handler(event)* to run on every future event on *topic*."""
        if topic not in TOPIC_SCHEMAS:
            raise EventValidationError(f"unknown topic: {topic!r}")
        with self._lock:
            self._subscribers.setdefault(topic, []).append(handler)

    def events(self, topic=None, after=0):
        """Return logged events, optionally filtered by topic and sequence."""
        with self._lock:
            return [
                dict(e)
                for e in self._log
                if e["seq"] > after and (topic is None or e["topic"] == topic)
            ]

    def __len__(self):
        with self._lock:
            return len(self._log)
