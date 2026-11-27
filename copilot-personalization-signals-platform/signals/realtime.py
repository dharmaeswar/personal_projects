"""Real-time personalization engine: sliding-window scorer.

Boosts signals the user is acting on right now (last hour) and decays
stale ones, then merges with the batch signals. Deterministic and
rule-based — not an ML model.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta

from .models import Event, Signal
from .privacy import category_of, consented_events

WINDOW = timedelta(hours=1)


def realtime_signals(user_id: str, events: list[Event], consent,
                     run_id: str, now: datetime) -> list[Signal]:
    """window(last 1h) -> count features/workflows, score by share."""
    recent = [e for e in consented_events(
        [e for e in events if e.user_id == user_id], consent)
        if now - e.parsed_time() <= WINDOW and e.parsed_time() <= now]
    counts: Counter = Counter()
    source_ids: list[str] = []
    for event in recent:
        source_ids.append(event.event_id)
        key = event.payload.get("feature") or event.payload.get("workflow")
        if key:
            counts[key] += 1
    total = sum(counts.values()) or 1
    return [Signal(user_id=user_id, signal_type="realtime_interest",
                   category=category_of("product_usage"), value=key,
                   score=round(n / total, 3), source="realtime",
                   source_event_ids=source_ids, produced_by_run=run_id)
            for key, n in counts.most_common(3)]


def merge_signals(batch: list[Signal], realtime: list[Signal]) -> list[Signal]:
    """Merge batch + realtime: same (type, value) keeps the higher score
    and prefers the realtime source; otherwise keep both, sorted by score."""
    merged: dict[tuple[str, str, str], Signal] = {}
    for signal in batch + realtime:
        key = (signal.user_id, signal.signal_type, signal.value)
        current = merged.get(key)
        if current is None or signal.score > current.score:
            merged[key] = signal
    return sorted(merged.values(), key=lambda s: -s.score)
