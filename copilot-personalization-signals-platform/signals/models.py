"""Data models for the Copilot personalization signals platform.

All data is synthetic. No real user data is used anywhere.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

EVENT_TYPES = ("telemetry", "product_usage", "experimentation")
SIGNAL_CATEGORIES = ("usage", "telemetry", "experimentation")


@dataclass
class Event:
    """One raw signal event, as it arrives from a producer.

    Mirrors a Kafka record on topic ``copilot.signals.raw`` (the queue
    here is in-memory; no Kafka broker is involved).
    """

    event_id: str
    user_id: str
    event_type: str  # telemetry | product_usage | experimentation
    source: str  # e.g. "copilot-app", "editor", "mobile"
    timestamp: str  # ISO 8601
    payload: dict = field(default_factory=dict)

    def parsed_time(self) -> datetime:
        return datetime.fromisoformat(self.timestamp)


@dataclass
class Consent:
    """Per-category consent for one user. A category the user opted out
    of is excluded from batch aggregates and never served."""

    user_id: str
    usage: bool = True
    telemetry: bool = True
    experimentation: bool = True

    def allows(self, category: str) -> bool:
        return bool(getattr(self, category, False))


@dataclass
class UserContext:
    """Governed user-context model: preferences, workflows, goals and
    experiment membership, with lineage back to the producing run."""

    user_id: str
    top_workflows: list[str] = field(default_factory=list)
    preferred_features: list[str] = field(default_factory=list)
    goal_affinity: dict[str, float] = field(default_factory=dict)
    experiment_arms: dict[str, str] = field(default_factory=dict)
    telemetry_event_count: int = 0
    produced_by_run: str = ""
    source_event_ids: list[str] = field(default_factory=list)


@dataclass
class Signal:
    """One personalization signal served to the Copilot runtime."""

    user_id: str
    signal_type: str  # e.g. "preferred_feature", "workflow_affinity"
    category: str  # usage | telemetry | experimentation
    value: str
    score: float  # 0.0 - 1.0, recency-weighted
    source: str  # "batch" | "realtime"
    source_event_ids: list[str] = field(default_factory=list)
    produced_by_run: str = ""
