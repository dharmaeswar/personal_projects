"""Instrumentation contracts: the event schema every producer must follow.

This is the "instrumentation standards" layer of the pipeline. A contract
names the required top-level fields for every event and the required
payload keys per event type. Events that break the contract are quarantined
with the exact reason instead of silently entering analytics tables, so a
bad release shows up as a data-quality signal instead of a wrong metric.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

EVENT_TYPES = ("page_view", "pin_save", "pin_click", "search", "signup")

REQUIRED_FIELDS = ("event_id", "user_id", "event_type", "event_ts")

# Payload keys each event type must carry. Payloads are nested JSON, so a
# missing nested key is a contract break even when the top level is fine.
REQUIRED_PAYLOAD = {
    "page_view": ("page",),
    "pin_save": ("pin_id", "board_id"),
    "pin_click": ("pin_id",),
    "search": ("query",),
    "signup": ("channel",),
}


@dataclass
class Violation:
    event_id: str | None
    reason: str


def validate_event(event: dict) -> list[Violation]:
    """Return every contract violation for one event (empty means valid)."""
    violations: list[Violation] = []
    for field in REQUIRED_FIELDS:
        if not event.get(field):
            violations.append(
                Violation(event.get("event_id"), f"missing required field: {field}")
            )
    event_type = event.get("event_type")
    if event_type and event_type not in EVENT_TYPES:
        violations.append(
            Violation(event.get("event_id"), f"unknown event_type: {event_type}")
        )
    if event_type in REQUIRED_PAYLOAD:
        payload = event.get("payload") or {}
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError:
                payload = {}
        if not isinstance(payload, dict):
            payload = {}
        for key in REQUIRED_PAYLOAD[event_type]:
            if not payload.get(key):
                violations.append(
                    Violation(
                        event.get("event_id"),
                        f"missing payload field for {event_type}: {key}",
                    )
                )
    return violations


def validate_batch(events: list[dict]) -> tuple[list[dict], list[Violation]]:
    """Split a batch into contract-valid events and the violations found."""
    good: list[dict] = []
    bad: list[Violation] = []
    for event in events:
        found = validate_event(event)
        if found:
            bad.extend(found)
        else:
            good.append(event)
    return good, bad
