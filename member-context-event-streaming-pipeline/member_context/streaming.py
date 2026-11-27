"""Stream processing: sessions and point-in-time member context.

The stream processor consumes validated events in offset order and
builds the member-context foundation:

- Sessions: events from one member grouped with a 30-minute inactivity
  gap, so a member's web/app/agent activity becomes journeys, not rows.
- Point-in-time context snapshots: for a member at an as-of timestamp,
  every feature is computed from events strictly BEFORE that timestamp,
  so a model trained or served on the snapshot can never see the future.
- Windowed aggregates: 7-day engagement counts per member and channel.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from .events import MemberEvent

SESSION_GAP = timedelta(minutes=30)
CONTEXT_WINDOW = timedelta(days=7)


@dataclass
class Session:
    member_id: str
    session_id: str
    started_at: datetime
    ended_at: datetime
    event_count: int
    channels: list[str] = field(default_factory=list)
    event_types: list[str] = field(default_factory=list)

    @property
    def duration_minutes(self) -> float:
        return (self.ended_at - self.started_at).total_seconds() / 60.0


def build_sessions(events: list[MemberEvent]) -> list[Session]:
    """Group a member's events into sessions on a 30-minute gap."""
    sessions: list[Session] = []
    by_member: dict[str, list[MemberEvent]] = {}
    for event in events:
        by_member.setdefault(event.member_id, []).append(event)
    for member_id, member_events in by_member.items():
        ordered = sorted(member_events, key=lambda e: e.occurred_at)
        current: list[MemberEvent] = [ordered[0]]
        for event in ordered[1:]:
            if event.occurred_at - current[-1].occurred_at > SESSION_GAP:
                sessions.append(_close_session(member_id, current))
                current = [event]
            else:
                current.append(event)
        sessions.append(_close_session(member_id, current))
    sessions.sort(key=lambda s: (s.started_at, s.member_id))
    return sessions


def _close_session(member_id: str, events: list[MemberEvent]) -> Session:
    return Session(
        member_id=member_id,
        session_id=events[0].payload.get("session_id", "unknown"),
        started_at=events[0].occurred_at,
        ended_at=events[-1].occurred_at,
        event_count=len(events),
        channels=sorted({e.channel for e in events}),
        event_types=sorted({e.event_type for e in events}),
    )


@dataclass
class MemberContext:
    """Point-in-time-correct context for one member at one as-of time."""

    member_id: str
    as_of: datetime
    events_7d: int
    sessions_7d: int
    channels_7d: list[str]
    event_counts_7d: dict[str, int]
    last_event_at: datetime | None
    last_event_type: str | None
    days_since_last_event: float | None


def build_member_context(
    events: list[MemberEvent], member_id: str, as_of: datetime
) -> MemberContext:
    """Features from events strictly before ``as_of`` — never the future."""
    window_start = as_of - CONTEXT_WINDOW
    prior = [
        e
        for e in events
        if e.member_id == member_id and window_start <= e.occurred_at < as_of
    ]
    prior.sort(key=lambda e: e.occurred_at)
    sessions = build_sessions(prior) if prior else []
    counts: dict[str, int] = {}
    for e in prior:
        counts[e.event_type] = counts.get(e.event_type, 0) + 1
    last = prior[-1] if prior else None
    return MemberContext(
        member_id=member_id,
        as_of=as_of,
        events_7d=len(prior),
        sessions_7d=len(sessions),
        channels_7d=sorted({e.channel for e in prior}),
        event_counts_7d=counts,
        last_event_at=last.occurred_at if last else None,
        last_event_type=last.event_type if last else None,
        days_since_last_event=(
            (as_of - last.occurred_at).total_seconds() / 86400.0 if last else None
        ),
    )


def windowed_counts(
    events: list[MemberEvent], as_of: datetime, window: timedelta = CONTEXT_WINDOW
) -> dict[str, dict[str, int]]:
    """Per-member, per-channel event counts inside the window ending at as_of."""
    out: dict[str, dict[str, int]] = {}
    start = as_of - window
    for e in events:
        if start <= e.occurred_at < as_of:
            out.setdefault(e.member_id, {}).setdefault(e.channel, 0)
            out[e.member_id][e.channel] += 1
    return out
