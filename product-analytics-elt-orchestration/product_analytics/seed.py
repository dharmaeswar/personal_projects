"""Deterministic synthetic product events for local runs and tests.

Seeded with ``random.Random(42)`` so every run produces the same data.
Events span 14 days for 300 users across the five contracted event
types, with realistic behaviour: some users save pins they view, some
click through, a few sign up. A small share of rows is deliberately
broken (missing fields, duplicate ids, unknown types) so the contract
and quarantine paths are exercised on every run.
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta

PAGES = ("home", "search", "pin_detail", "board", "profile")
BOARDS = ("home-decor", "recipes", "travel", "diy", "fashion")
CHANNELS = ("organic", "invite", "ads", "email")


def _payload(event_type: str, rng: random.Random) -> dict:
    if event_type == "page_view":
        return {"page": rng.choice(PAGES)}
    if event_type in ("pin_save", "pin_click"):
        payload = {"pin_id": f"pin_{rng.randint(1, 5000)}"}
        if event_type == "pin_save":
            payload["board_id"] = rng.choice(BOARDS)
        return payload
    if event_type == "search":
        return {"query": rng.choice(["fall decor", "pasta", "kyoto", "bookshelf"])}
    return {"channel": rng.choice(CHANNELS)}


def generate_events(count: int = 6000, days: int = 14, seed: int = 42) -> list[dict]:
    rng = random.Random(seed)
    start = datetime(2026, 11, 1, 0, 0, 0)
    events: list[dict] = []
    for i in range(count):
        user = f"user_{rng.randint(1, 300):03d}"
        event_type = rng.choices(
            ["page_view", "pin_save", "pin_click", "search", "signup"],
            weights=[45, 20, 20, 12, 3],
        )[0]
        ts = start + timedelta(
            days=rng.randint(0, days - 1),
            seconds=rng.randint(0, 86399),
        )
        events.append(
            {
                "event_id": f"evt_{i:06d}",
                "user_id": user,
                "event_type": event_type,
                "event_ts": ts.strftime("%Y-%m-%dT%H:%M:%S"),
                "payload": _payload(event_type, rng),
            }
        )
    # Deliberately broken rows: missing user, duplicate id, unknown type.
    events.append({"event_id": "evt_bad_1", "user_id": "", "event_type": "page_view",
                   "event_ts": "2026-11-03T10:00:00", "payload": {"page": "home"}})
    events.append(dict(events[0]))  # duplicate event_id, re-delivered batch
    events.append({"event_id": "evt_bad_2", "user_id": "user_001", "event_type": "mystery",
                   "event_ts": "2026-11-03T10:00:00", "payload": {}})
    events.append({"event_id": "evt_bad_3", "user_id": "user_002", "event_type": "pin_save",
                   "event_ts": "2026-11-03T10:00:00", "payload": {}})
    return events
