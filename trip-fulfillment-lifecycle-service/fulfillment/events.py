"""Event log: every lifecycle step is recorded, in order, exactly once.

The tracking phase of fulfillment is an append-only event stream: one
event per transition, with a monotonic sequence number per trip, so a
consumer can replay a trip's history or resume from any offset without
re-reading the whole log. Duplicate submissions of the same event id are
ignored (idempotency), which is what makes at-least-once delivery safe.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


@dataclass(frozen=True)
class TripEvent:
    trip_id: str
    event_id: str
    event_type: str
    seq: int
    recorded_at: datetime = field(default_factory=_utcnow)
    detail: str = ""


class EventLog:
    def __init__(self) -> None:
        self._events: list[TripEvent] = []
        self._seen_ids: set[str] = set()

    def append(self, trip_id: str, event_id: str, event_type: str,
               detail: str = "") -> TripEvent | None:
        """Append an event; returns None when ``event_id`` was already seen."""
        if event_id in self._seen_ids:
            return None
        seq = sum(1 for e in self._events if e.trip_id == trip_id) + 1
        event = TripEvent(trip_id, event_id, event_type, seq, detail=detail)
        self._events.append(event)
        self._seen_ids.add(event_id)
        return event

    def events_for(self, trip_id: str, after_seq: int = 0) -> list[TripEvent]:
        """All events for a trip, optionally resuming after a sequence number."""
        return [e for e in self._events
                if e.trip_id == trip_id and e.seq > after_seq]

    def __len__(self) -> int:
        return len(self._events)
