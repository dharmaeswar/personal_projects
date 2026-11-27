"""Ingest: validate, quarantine, dedupe, retry.

Mirrors a Kafka consumer on topic ``copilot.signals.raw``; the queue
here is a plain list, no broker is involved.
"""
from __future__ import annotations

from datetime import datetime

from .models import EVENT_TYPES, Event

REQUIRED_FIELDS = ("event_id", "user_id", "event_type", "source", "timestamp")


def validate_event(raw: dict, now: datetime | None = None) -> list[str]:
    """Return the list of rule violations for one raw event row."""
    now = now or datetime.now()
    problems: list[str] = []
    for field_name in REQUIRED_FIELDS:
        if not raw.get(field_name):
            problems.append(f"missing {field_name}")
    if problems:
        return problems
    if raw["event_type"] not in EVENT_TYPES:
        problems.append(f"unknown event_type {raw['event_type']!r}")
    try:
        ts = datetime.fromisoformat(raw["timestamp"])
    except ValueError:
        problems.append("bad timestamp")
        return problems
    if ts > now:
        problems.append("future timestamp")
    duration = (raw.get("payload") or {}).get("duration_seconds")
    if duration is not None and duration < 0:
        problems.append("negative duration_seconds")
    arm = (raw.get("payload") or {}).get("experiment_arm")
    if raw["event_type"] == "experimentation" and arm not in ("control", "treatment"):
        problems.append("unknown experiment_arm")
    return problems


def ingest_batch(raw_events: list[dict], seen_ids: set[str],
                 now: datetime | None = None):
    """Validate + dedupe a batch.

    Returns (accepted: list[Event], quarantined: list[dict]) where each
    quarantined row carries the rule that fired. Re-delivered events
    collapse on event_id (idempotent, exactly-once effect).
    """
    accepted: list[Event] = []
    quarantined: list[dict] = []
    for raw in raw_events:
        problems = validate_event(raw, now=now)
        if problems:
            quarantined.append({"event": raw, "reasons": problems})
            continue
        if raw["event_id"] in seen_ids:
            quarantined.append({"event": raw, "reasons": ["duplicate event_id"]})
            continue
        seen_ids.add(raw["event_id"])
        accepted.append(Event(
            event_id=raw["event_id"], user_id=raw["user_id"],
            event_type=raw["event_type"], source=raw["source"],
            timestamp=raw["timestamp"], payload=raw.get("payload") or {},
        ))
    return accepted, quarantined


def retry_quarantined(quarantined: list[dict], fixes: dict[str, dict],
                      seen_ids: set[str], now: datetime | None = None):
    """Re-check corrected rows (keyed by event_id in ``fixes``) and
    promote the ones that now pass."""
    promoted: list[Event] = []
    still_bad: list[dict] = []
    for item in quarantined:
        event_id = item["event"].get("event_id")
        fixed = fixes.get(event_id)
        if fixed is None:
            still_bad.append(item)
            continue
        merged = {**item["event"], **fixed}
        problems = validate_event(merged, now=now)
        if problems or merged["event_id"] in seen_ids:
            still_bad.append({"event": merged,
                              "reasons": problems or ["duplicate event_id"]})
            continue
        seen_ids.add(merged["event_id"])
        promoted.append(Event(
            event_id=merged["event_id"], user_id=merged["user_id"],
            event_type=merged["event_type"], source=merged["source"],
            timestamp=merged["timestamp"], payload=merged.get("payload") or {},
        ))
    return promoted, still_bad
