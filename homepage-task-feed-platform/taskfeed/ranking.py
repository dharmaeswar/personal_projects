"""Ranking: one score orders every task in the feed, whatever its source.

score = priority weight + due-date urgency + source relevance + freshness.
All weights are explicit constants so a ranking change is a reviewable diff,
not a hidden tweak. Ties break deterministically on (created_at, key) so two
identical feed builds return identical order.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from .models import Task

PRIORITY_WEIGHT = 20.0   # per priority point (1..5)
OVERDUE_BONUS = 30.0
DUE_TODAY_BONUS = 20.0
DUE_THIS_WEEK_BONUS = 10.0
RELEVANCE_WEIGHT = 20.0  # relevance 0..1 maps to 0..20
FRESHNESS_HALF_LIFE_DAYS = 14.0  # score decays slowly as a task ages


def urgency_bonus(task: Task, now: datetime) -> float:
    if task.due_at is None:
        return 0.0
    if task.due_at < now:
        return OVERDUE_BONUS
    if task.due_at.date() == now.date():
        return DUE_TODAY_BONUS
    if task.due_at <= now + timedelta(days=7):
        return DUE_THIS_WEEK_BONUS
    return 0.0


def freshness_factor(task: Task, now: datetime) -> float:
    """0..1: recent tasks keep full weight, old ones decay toward 0.5."""
    age_days = max(0.0, (now - task.created_at).total_seconds() / 86400.0)
    return 0.5 + 0.5 * (0.5 ** (age_days / FRESHNESS_HALF_LIFE_DAYS))


def score(task: Task, now: datetime) -> float:
    base = (
        task.priority * PRIORITY_WEIGHT
        + urgency_bonus(task, now)
        + task.relevance * RELEVANCE_WEIGHT
    )
    return round(base * freshness_factor(task, now), 4)


def rank(tasks: list[Task], now: datetime) -> list[Task]:
    """Highest score first; deterministic tie-break on (created_at, key)."""
    return sorted(
        tasks,
        key=lambda t: (-score(t, now), t.created_at, t.key),
    )
