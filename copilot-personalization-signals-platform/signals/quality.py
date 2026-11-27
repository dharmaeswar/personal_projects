"""Data-quality checks. A failed check blocks publish."""
from __future__ import annotations

from datetime import datetime, timedelta

from .models import Event, Signal


def check_events(events: list[Event], now: datetime) -> list[str]:
    problems: list[str] = []
    ids = [e.event_id for e in events]
    if len(ids) != len(set(ids)):
        problems.append("duplicate event_id in store")
    if any(not e.user_id for e in events):
        problems.append("event with missing user_id")
    if events:
        newest = max(e.parsed_time() for e in events)
        if now - newest > timedelta(days=2):
            problems.append("freshness: newest event older than 2 days")
    return problems


def check_signals(signals: list[Signal], events: list[Event]) -> list[str]:
    """Reconciliation: every signal's source events must exist; every
    score in range; no signal without a source."""
    problems: list[str] = []
    known = {e.event_id for e in events}
    for signal in signals:
        if not 0.0 <= signal.score <= 1.0:
            problems.append(f"signal {signal.value} score out of range")
        if not signal.source_event_ids:
            problems.append(f"signal {signal.value} has no source events")
        elif not set(signal.source_event_ids) <= known:
            problems.append(f"signal {signal.value} cites unknown event ids")
    return problems
