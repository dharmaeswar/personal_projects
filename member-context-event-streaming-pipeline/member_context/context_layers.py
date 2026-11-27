"""Curated context layers for ML inference and LLM consumption.

Two layers are built from the validated, point-in-time-correct stream:

- ``member_context_snapshot`` — one feature row per member per as-of
  time, for traditional ML inference (ranking / next-best-action models).
- ``llm_context_document`` — one retrieval-ready structured document per
  member: recent journey, active actions, and the context an LLM agent
  needs to interpret the member's situation, with no free-text health
  detail beyond the synthetic event types.
- ``action_journey_catalogue`` — the catalogue of action and journey
  options the personalization platform can offer a member.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from .events import MemberEvent
from .streaming import MemberContext, build_member_context

ACTIONS = [
    {"action_id": "action-01", "name": "find_primary_care", "journey": "find_care"},
    {"action_id": "action-02", "name": "find_urgent_care", "journey": "find_care"},
    {"action_id": "action-03", "name": "review_plan_benefits", "journey": "understand_plan"},
    {"action_id": "action-04", "name": "check_claim_status", "journey": "track_claim"},
    {"action_id": "action-05", "name": "message_health_agent", "journey": "get_help"},
    {"action_id": "action-06", "name": "book_preventive_visit", "journey": "stay_healthy"},
    {"action_id": "action-07", "name": "compare_plans", "journey": "understand_plan"},
    {"action_id": "action-08", "name": "view_benefits", "journey": "understand_plan"},
]


@dataclass
class SnapshotRow:
    """One ML-inference feature row: member context as of a timestamp."""

    member_id: str
    as_of: str
    events_7d: int
    sessions_7d: int
    channels: str
    last_event_type: str | None
    days_since_last_event: float | None
    care_search_7d: int
    agent_message_7d: int
    outbound_click_7d: int

    def to_dict(self) -> dict:
        return {
            "member_id": self.member_id,
            "as_of": self.as_of,
            "events_7d": self.events_7d,
            "sessions_7d": self.sessions_7d,
            "channels": self.channels,
            "last_event_type": self.last_event_type,
            "days_since_last_event": self.days_since_last_event,
            "care_search_7d": self.care_search_7d,
            "agent_message_7d": self.agent_message_7d,
            "outbound_click_7d": self.outbound_click_7d,
        }


def build_snapshot_rows(
    events: list[MemberEvent], member_ids: list[str], as_of: datetime
) -> list[SnapshotRow]:
    rows: list[SnapshotRow] = []
    for member_id in member_ids:
        ctx: MemberContext = build_member_context(events, member_id, as_of)
        rows.append(
            SnapshotRow(
                member_id=member_id,
                as_of=as_of.isoformat(),
                events_7d=ctx.events_7d,
                sessions_7d=ctx.sessions_7d,
                channels=",".join(ctx.channels_7d),
                last_event_type=ctx.last_event_type,
                days_since_last_event=(
                    round(ctx.days_since_last_event, 2)
                    if ctx.days_since_last_event is not None
                    else None
                ),
                care_search_7d=ctx.event_counts_7d.get("care_search", 0),
                agent_message_7d=ctx.event_counts_7d.get("agent_message", 0),
                outbound_click_7d=ctx.event_counts_7d.get("outbound_click", 0),
            )
        )
    return rows


@dataclass
class LlmContextDocument:
    """Retrieval-ready structured context for one member."""

    member_id: str
    as_of: str
    summary: str
    recent_journey: list[dict]
    suggested_actions: list[dict]

    def to_dict(self) -> dict:
        return {
            "member_id": self.member_id,
            "as_of": self.as_of,
            "summary": self.summary,
            "recent_journey": self.recent_journey,
            "suggested_actions": self.suggested_actions,
        }


def build_llm_documents(
    events: list[MemberEvent], member_ids: list[str], as_of: datetime
) -> list[LlmContextDocument]:
    docs: list[LlmContextDocument] = []
    for member_id in member_ids:
        ctx = build_member_context(events, member_id, as_of)
        recent = [
            {
                "event_type": e.event_type,
                "channel": e.channel,
                "occurred_at": e.occurred_at.isoformat(),
            }
            for e in sorted(
                [e for e in events if e.member_id == member_id and e.occurred_at < as_of],
                key=lambda e: e.occurred_at,
            )[-10:]
        ]
        suggested = [a for a in ACTIONS if a["journey"] in _journeys_for(ctx)][:3]
        docs.append(
            LlmContextDocument(
                member_id=member_id,
                as_of=as_of.isoformat(),
                summary=(
                    f"Member {member_id} had {ctx.events_7d} engagement events across "
                    f"{ctx.sessions_7d} sessions in the last 7 days via "
                    f"{', '.join(ctx.channels_7d) or 'no channel'}; last event was "
                    f"{ctx.last_event_type or 'none'}."
                ),
                recent_journey=recent,
                suggested_actions=suggested,
            )
        )
    return docs


def _journeys_for(ctx: MemberContext) -> set[str]:
    journeys = {"get_help"}
    if ctx.event_counts_7d.get("care_search", 0):
        journeys.add("find_care")
    if ctx.event_counts_7d.get("plan_browse", 0) or ctx.event_counts_7d.get("benefit_view", 0):
        journeys.add("understand_plan")
    if ctx.event_counts_7d.get("claim_status_check", 0):
        journeys.add("track_claim")
    return journeys


def action_journey_catalogue() -> list[dict]:
    """The catalogue of action and journey options for engagement."""
    return [dict(a) for a in ACTIONS]
