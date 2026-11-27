"""JSON-file store. Local files stand in for the warehouse / feature
store; no cloud services are called.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict

from .models import Event, Signal, UserContext


class Store:
    def __init__(self, path: str):
        self.path = path
        self.data: dict = {"events": [], "profiles": {}, "signals": [], "audit": []}
        if os.path.exists(path):
            with open(path) as f:
                self.data = json.load(f)

    def save(self) -> None:
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        with open(self.path, "w") as f:
            json.dump(self.data, f, indent=2, sort_keys=True)

    # -- events ------------------------------------------------------
    def add_events(self, events: list[Event]) -> None:
        self.data["events"].extend(asdict(e) for e in events)
        self.save()

    def events(self) -> list[Event]:
        return [Event(**e) for e in self.data["events"]]

    def event_ids(self) -> set[str]:
        return {e["event_id"] for e in self.data["events"]}

    # -- profiles / signals ------------------------------------------
    def put_profile(self, profile: UserContext) -> None:
        self.data["profiles"][profile.user_id] = asdict(profile)
        self.save()

    def profile(self, user_id: str) -> UserContext | None:
        raw = self.data["profiles"].get(user_id)
        return UserContext(**raw) if raw else None

    def put_signals(self, signals: list[Signal]) -> None:
        self.data["signals"] = [asdict(s) for s in signals]
        self.save()

    def signals_for(self, user_id: str) -> list[Signal]:
        return [Signal(**s) for s in self.data["signals"] if s["user_id"] == user_id]

    # -- audit ---------------------------------------------------------
    def audit(self, entry: dict) -> None:
        self.data["audit"].append(entry)
        self.save()
