"""Batch personalization engine.

Spark-style aggregation in plain Python; every operation names the
Spark equivalent it mirrors (groupBy, window, join). No Spark cluster
is involved; the same logic maps to PySpark/Databricks.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime

from .models import Event, Signal, UserContext
from .privacy import category_of, consented_events

# Recency half-life: an event 7 days old counts half as much as today's.
HALF_LIFE_DAYS = 7.0


def recency_weight(event_time: datetime, now: datetime) -> float:
    age_days = max(0.0, (now - event_time).total_seconds() / 86400.0)
    return 0.5 ** (age_days / HALF_LIFE_DAYS)


def build_user_context(user_id: str, events: list[Event], consent,
                       run_id: str, now: datetime) -> UserContext:
    """groupBy(user_id) -> aggregate workflows, features, goals, arms.

    Only consented categories feed the aggregate (privacy by design).
    """
    mine = consented_events([e for e in events if e.user_id == user_id], consent)
    workflows: Counter = Counter()
    features: Counter = Counter()
    goals: defaultdict[str, float] = defaultdict(float)
    arms: dict[str, str] = {}
    telemetry_count = 0
    source_ids: list[str] = []
    for event in mine:
        weight = recency_weight(event.parsed_time(), now)
        source_ids.append(event.event_id)
        if event.event_type == "telemetry":
            telemetry_count += 1
        payload = event.payload
        if payload.get("workflow"):
            workflows[payload["workflow"]] += weight
        if payload.get("feature"):
            features[payload["feature"]] += weight
        if payload.get("goal"):
            goals[payload["goal"]] += weight
        if event.event_type == "experimentation" and payload.get("experiment"):
            arms[payload["experiment"]] = payload.get("experiment_arm", "")
    total_goal = sum(goals.values()) or 1.0
    return UserContext(
        user_id=user_id,
        top_workflows=[w for w, _ in workflows.most_common(3)],
        preferred_features=[f for f, _ in features.most_common(3)],
        goal_affinity={g: round(v / total_goal, 3) for g, v in goals.items()},
        experiment_arms=arms,
        telemetry_event_count=telemetry_count,
        produced_by_run=run_id,
        source_event_ids=source_ids,
    )


def build_batch_signals(profile: UserContext, run_id: str) -> list[Signal]:
    """Turn a user-context model into scored batch signals."""
    signals: list[Signal] = []
    for workflow in profile.top_workflows:
        signals.append(Signal(user_id=profile.user_id, signal_type="workflow_affinity",
                              category="usage", value=workflow, score=0.8,
                              source="batch", source_event_ids=profile.source_event_ids,
                              produced_by_run=run_id))
    for feature in profile.preferred_features:
        signals.append(Signal(user_id=profile.user_id, signal_type="preferred_feature",
                              category="usage", value=feature, score=0.75,
                              source="batch", source_event_ids=profile.source_event_ids,
                              produced_by_run=run_id))
    for goal, affinity in profile.goal_affinity.items():
        signals.append(Signal(user_id=profile.user_id, signal_type="goal_affinity",
                              category="usage", value=goal, score=round(affinity, 3),
                              source="batch", source_event_ids=profile.source_event_ids,
                              produced_by_run=run_id))
    for experiment, arm in profile.experiment_arms.items():
        signals.append(Signal(user_id=profile.user_id, signal_type="experiment_arm",
                              category="experimentation", value=f"{experiment}:{arm}",
                              score=1.0, source="batch",
                              source_event_ids=profile.source_event_ids,
                              produced_by_run=run_id))
    if profile.telemetry_event_count:
        signals.append(Signal(user_id=profile.user_id, signal_type="telemetry_activity",
                              category="telemetry",
                              value=f"{profile.telemetry_event_count} telemetry events",
                              score=0.6, source="batch",
                              source_event_ids=profile.source_event_ids,
                              produced_by_run=run_id))
    return signals
