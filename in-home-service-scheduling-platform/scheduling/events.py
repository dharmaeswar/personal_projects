"""Event types and the append-only event store (event sourcing).

Every state change to an appointment is an immutable event appended to
the store. Current state is never stored directly: it is rebuilt by
replaying the event stream for an aggregate (see commands.py and
projections.py). The store persists as one JSON object per line so a
restart can reload the full history.
"""
from __future__ import annotations

import json
import os
import uuid
from dataclasses import asdict, dataclass, field

EVENT_TYPES = (
    "AppointmentScheduled",
    "AppointmentRescheduled",
    "TechnicianAssigned",
    "AppointmentCancelled",
    "AppointmentCompleted",
    "DispatchAttempted",
)


@dataclass(frozen=True)
class Event:
    event_id: str
    aggregate_id: str
    event_type: str
    version: int
    payload: dict
    idempotency_key: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Event":
        return cls(**data)


class EventStore:
    """Append-only store. Appends are atomic per event; versions are
    checked so two writers cannot both claim the same version."""

    def __init__(self, path: str | None = None):
        self.path = path
        self._events: list[Event] = []
        if path and os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if line:
                        self._events.append(Event.from_dict(json.loads(line)))

    def append(self, event: Event) -> Event:
        existing = [e for e in self._events if e.aggregate_id == event.aggregate_id]
        if existing and event.version != existing[-1].version + 1:
            raise ValueError(
                f"version conflict for {event.aggregate_id}: "
                f"expected {existing[-1].version + 1}, got {event.version}"
            )
        if event.event_type not in EVENT_TYPES:
            raise ValueError(f"unknown event type {event.event_type!r}")
        self._events.append(event)
        if self.path:
            with open(self.path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(event.to_dict()) + "\n")
        return event

    def events_for(self, aggregate_id: str) -> list[Event]:
        return [e for e in self._events if e.aggregate_id == aggregate_id]

    def all_events(self) -> list[Event]:
        return list(self._events)

    def next_version(self, aggregate_id: str) -> int:
        events = self.events_for(aggregate_id)
        return (events[-1].version + 1) if events else 1

    def find_by_idempotency_key(self, key: str) -> Event | None:
        for event in self._events:
            if event.idempotency_key == key:
                return event
        return None


def new_event(aggregate_id: str, event_type: str, version: int,
              payload: dict, idempotency_key: str | None = None) -> Event:
    return Event(
        event_id=str(uuid.uuid4()),
        aggregate_id=aggregate_id,
        event_type=event_type,
        version=version,
        payload=payload,
        idempotency_key=idempotency_key,
    )
