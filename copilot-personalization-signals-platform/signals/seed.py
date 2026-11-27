"""Deterministic synthetic seed data (seed 42). No real user data."""
from __future__ import annotations

import random
from datetime import datetime, timedelta

USERS = [f"user-{i:02d}" for i in range(1, 9)]
WORKFLOWS = ["draft-email", "summarize-doc", "plan-day", "code-review", "research-topic"]
FEATURES = ["summarize", "draft", "translate", "schedule", "explain-code"]
GOALS = ["productivity", "learning", "writing", "coding"]
SOURCES = ["copilot-app", "editor", "mobile"]


def seed_events(now: datetime | None = None, count: int = 240) -> list[dict]:
    """240 synthetic events over 7 days, with deliberately broken rows
    planted so the quarantine and dedupe paths run every time."""
    now = now or datetime(2026, 11, 26, 12, 0, 0)
    rng = random.Random(42)
    events: list[dict] = []
    for i in range(count):
        user = rng.choice(USERS)
        event_type = rng.choice(["telemetry", "product_usage", "product_usage",
                                 "experimentation"])
        ts = now - timedelta(days=rng.uniform(0, 7), hours=rng.uniform(0, 5))
        payload: dict = {}
        if event_type == "experimentation":
            payload = {"experiment": rng.choice(["exp-a", "exp-b"]),
                       "experiment_arm": rng.choice(["control", "treatment"])}
        else:
            payload = {"workflow": rng.choice(WORKFLOWS),
                       "feature": rng.choice(FEATURES),
                       "goal": rng.choice(GOALS),
                       "duration_seconds": rng.randint(5, 600)}
        events.append({"event_id": f"evt-{i:04d}", "user_id": user,
                       "event_type": event_type, "source": rng.choice(SOURCES),
                       "timestamp": ts.isoformat(), "payload": payload})
    # Planted bad rows: missing user, duplicate id, unknown type, future
    # timestamp, negative duration.
    events.append({"event_id": "evt-bad-1", "user_id": "", "event_type": "telemetry",
                   "source": "copilot-app", "timestamp": now.isoformat(), "payload": {}})
    events.append({"event_id": "evt-0001", "user_id": "user-01", "event_type": "telemetry",
                   "source": "copilot-app", "timestamp": now.isoformat(), "payload": {}})
    events.append({"event_id": "evt-bad-3", "user_id": "user-01", "event_type": "mystery",
                   "source": "copilot-app", "timestamp": now.isoformat(), "payload": {}})
    events.append({"event_id": "evt-bad-4", "user_id": "user-01", "event_type": "telemetry",
                   "source": "copilot-app",
                   "timestamp": (now + timedelta(days=1)).isoformat(), "payload": {}})
    events.append({"event_id": "evt-bad-5", "user_id": "user-01", "event_type": "product_usage",
                   "source": "copilot-app", "timestamp": now.isoformat(),
                   "payload": {"duration_seconds": -30}})
    return events


def seed_consents() -> dict:
    """One user (user-03) has telemetry consent off, so the privacy
    path runs on every execution."""
    from .models import Consent
    return {u: Consent(user_id=u) for u in USERS} | {
        "user-03": Consent(user_id="user-03", telemetry=False)}
