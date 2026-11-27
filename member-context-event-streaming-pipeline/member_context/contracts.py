"""Data contracts and data quality.

A data contract is the reusable, versioned definition of what a valid
member event looks like: required fields, allowed types, value ranges.
Every event is validated against its contract before it enters the
context layers. Bad rows are quarantined with the rule that fired —
never dropped silently — and re-deliveries collapse on ``event_id``
(idempotent, exactly-once effect).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from .events import EVENT_TYPES, REQUIRED_FIELDS, MemberEvent


@dataclass
class Contract:
    """Reusable data contract for one event type (versioned)."""

    event_type: str
    version: str
    required_fields: tuple[str, ...]
    allowed_channels: tuple[str, ...] = ("web", "app", "agent", "outbound")

    def validate(self, event: MemberEvent, now: datetime | None = None) -> list[str]:
        """Return the list of violations; empty means the event is valid."""
        now = now or datetime.now(timezone.utc)
        violations: list[str] = []
        if event.event_type != self.event_type:
            violations.append(f"event_type {event.event_type!r} != contract {self.event_type!r}")
            return violations
        for f in self.required_fields:
            if f not in event.payload or event.payload[f] in (None, ""):
                violations.append(f"missing required field: {f}")
        if event.channel not in self.allowed_channels:
            violations.append(f"unknown channel: {event.channel!r}")
        if event.occurred_at > now + timedelta(seconds=60):
            violations.append("occurred_at is in the future")
        if event.ingested_at < event.occurred_at:
            violations.append("ingested_at is before occurred_at")
        duration = event.payload.get("duration_seconds")
        if duration is not None and duration < 0:
            violations.append("duration_seconds is negative")
        return violations


CONTRACTS: dict[str, Contract] = {
    event_type: Contract(
        event_type=event_type,
        version="1.0",
        required_fields=REQUIRED_FIELDS[event_type],
    )
    for event_type in EVENT_TYPES
}


@dataclass
class QuarantinedRow:
    event_id: str
    member_id: str
    event_type: str
    reason: str
    event: dict


@dataclass
class QualityResult:
    valid: list[MemberEvent] = field(default_factory=list)
    quarantined: list[QuarantinedRow] = field(default_factory=list)
    duplicates_dropped: int = 0

    @property
    def total_seen(self) -> int:
        return len(self.valid) + len(self.quarantined) + self.duplicates_dropped


def check_quality(events: list[MemberEvent], now: datetime | None = None) -> QualityResult:
    """Validate events against contracts; dedupe on event_id.

    Dedupe keeps the earliest-ingested copy of each event_id, giving an
    exactly-once effect for producer re-deliveries. Unknown event types
    have no contract and are quarantined.
    """
    result = QualityResult()
    seen_ids: set[str] = set()
    for event in sorted(events, key=lambda e: (e.ingested_at, e.event_id)):
        if event.event_id in seen_ids:
            result.duplicates_dropped += 1
            continue
        seen_ids.add(event.event_id)
        contract = CONTRACTS.get(event.event_type)
        if contract is None:
            result.quarantined.append(
                QuarantinedRow(
                    event_id=event.event_id,
                    member_id=event.member_id,
                    event_type=event.event_type,
                    reason=f"no contract for event_type {event.event_type!r}",
                    event=event.to_dict(),
                )
            )
            continue
        violations = contract.validate(event, now=now)
        if violations:
            result.quarantined.append(
                QuarantinedRow(
                    event_id=event.event_id,
                    member_id=event.member_id,
                    event_type=event.event_type,
                    reason="; ".join(violations),
                    event=event.to_dict(),
                )
            )
            continue
        result.valid.append(event)
    return result
