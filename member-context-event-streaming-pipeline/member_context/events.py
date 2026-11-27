"""Synthetic member engagement events.

All data is synthetic and seeded. No real Oscar member, health, or
engagement data is used, and nothing here describes a real company's
traffic or a production pipeline.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

EVENT_TYPES = (
    "web_page_view",
    "app_open",
    "search",
    "plan_browse",
    "care_search",
    "agent_message",
    "outbound_click",
    "benefit_view",
    "claim_status_check",
)

CHANNELS = ("web", "app", "agent", "outbound")

# Fields each event type must carry. The data contract (contracts.py)
# enforces these; the generator deliberately emits a small share of rows
# that break them so the quality layer has something to quarantine.
REQUIRED_FIELDS = {
    "web_page_view": ("page", "session_id"),
    "app_open": ("session_id",),
    "search": ("query", "session_id"),
    "plan_browse": ("plan_id", "session_id"),
    "care_search": ("specialty", "session_id"),
    "agent_message": ("agent_id", "session_id"),
    "outbound_click": ("campaign_id", "action_id"),
    "benefit_view": ("benefit_id", "session_id"),
    "claim_status_check": ("claim_id", "session_id"),
}


@dataclass
class MemberEvent:
    """One member engagement event, as it arrives on a Kafka topic."""

    event_id: str
    member_id: str
    event_type: str
    occurred_at: datetime
    ingested_at: datetime
    channel: str
    payload: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "member_id": self.member_id,
            "event_type": self.event_type,
            "occurred_at": self.occurred_at.isoformat(),
            "ingested_at": self.ingested_at.isoformat(),
            "channel": self.channel,
            **self.payload,
        }


def generate_events(
    n_members: int = 40,
    events_per_member: int = 25,
    seed: int = 42,
    start: datetime | None = None,
) -> list[MemberEvent]:
    """Generate seeded synthetic events.

    Roughly 2% of events are producer re-deliveries (same event_id twice),
    ~2% arrive late (ingested hours after they occurred), and ~3% break
    the contract (missing field, unknown type, future timestamp, or a
    negative value) so the quality layer can quarantine them.
    """
    rng = random.Random(seed)
    start = start or datetime(2026, 11, 20, 0, 0, tzinfo=timezone.utc)
    events: list[MemberEvent] = []
    seq = 0
    for m in range(n_members):
        member_id = f"member-{m:04d}"
        n = events_per_member + rng.randint(-5, 5)
        for _ in range(n):
            seq += 1
            event_type = rng.choice(EVENT_TYPES)
            occurred = start + timedelta(
                minutes=rng.randint(0, 6 * 24 * 60), seconds=rng.randint(0, 59)
            )
            ingested = occurred + timedelta(seconds=rng.randint(1, 300))
            if rng.random() < 0.02:  # late arrival
                ingested = occurred + timedelta(hours=rng.randint(2, 12))
            payload = {
                "session_id": f"session-{rng.randint(1, 5000):05d}",
                "page": f"/page-{rng.randint(1, 40)}",
                "query": rng.choice(["find doctor", "urgent care", "plan benefits"]),
                "plan_id": f"plan-{rng.randint(1, 6)}",
                "specialty": rng.choice(["primary care", "dermatology", "pediatrics"]),
                "agent_id": f"agent-{rng.randint(1, 12):02d}",
                "campaign_id": f"campaign-{rng.randint(1, 8)}",
                "action_id": f"action-{rng.randint(1, 20):02d}",
                "benefit_id": f"benefit-{rng.randint(1, 10):02d}",
                "claim_id": f"claim-{rng.randint(1, 9000):05d}",
            }
            event = MemberEvent(
                event_id=f"evt-{seq:06d}",
                member_id=member_id,
                event_type=event_type,
                occurred_at=occurred,
                ingested_at=ingested,
                channel=rng.choice(CHANNELS),
                payload={k: payload[k] for k in REQUIRED_FIELDS[event_type]},
            )
            events.append(event)
            if rng.random() < 0.02:  # producer re-delivery: same event_id again
                events.append(
                    MemberEvent(
                        event_id=event.event_id,
                        member_id=event.member_id,
                        event_type=event.event_type,
                        occurred_at=event.occurred_at,
                        ingested_at=event.ingested_at + timedelta(seconds=5),
                        channel=event.channel,
                        payload=dict(event.payload),
                    )
                )
            if rng.random() < 0.03:  # contract-breaking row
                bad = rng.choice(["missing_field", "unknown_type", "future_ts", "bad_value"])
                seq += 1
                if bad == "missing_field":
                    bad_payload = dict(event.payload)
                    bad_payload.pop(next(iter(bad_payload)))
                    events.append(
                        MemberEvent(
                            event_id=f"evt-{seq:06d}",
                            member_id=member_id,
                            event_type=event_type,
                            occurred_at=occurred,
                            ingested_at=ingested,
                            channel=event.channel,
                            payload=bad_payload,
                        )
                    )
                elif bad == "unknown_type":
                    events.append(
                        MemberEvent(
                            event_id=f"evt-{seq:06d}",
                            member_id=member_id,
                            event_type="mystery_event",
                            occurred_at=occurred,
                            ingested_at=ingested,
                            channel=event.channel,
                            payload={},
                        )
                    )
                elif bad == "future_ts":
                    events.append(
                        MemberEvent(
                            event_id=f"evt-{seq:06d}",
                            member_id=member_id,
                            event_type=event_type,
                            occurred_at=occurred + timedelta(days=30),
                            ingested_at=ingested,
                            channel=event.channel,
                            payload=dict(event.payload),
                        )
                    )
                else:
                    bad_payload = dict(event.payload)
                    bad_payload["duration_seconds"] = -45
                    events.append(
                        MemberEvent(
                            event_id=f"evt-{seq:06d}",
                            member_id=member_id,
                            event_type=event_type,
                            occurred_at=occurred,
                            ingested_at=ingested,
                            channel=event.channel,
                            payload=bad_payload,
                        )
                    )
    events.sort(key=lambda e: (e.ingested_at, e.event_id))
    return events
