"""Synthetic media session events and a Kafka-style topic simulator.

All data is synthetic and seeded. No real streaming-service session, user,
or title data is used, and nothing here describes a real platform's traffic.
"""
from __future__ import annotations

import hashlib
import random
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

EVENT_TYPES = (
    "session_start", "heartbeat", "pause", "resume", "seek",
    "ad_start", "ad_end", "error", "session_end",
)
DEVICES = ("tv", "mobile", "web", "tablet")
REGIONS = ("us-west", "us-east", "us-central")
APPS = ("video", "sports", "news")
TITLES = [f"title-{i:03d}" for i in range(1, 21)]


def _hash_id(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:16]


def generate_sessions(n_sessions: int, seed: int = 42,
                      start: datetime | None = None) -> list[dict]:
    """Generate synthetic playback-session event streams.

    Each session is a time-ordered event sequence for one viewer watching
    one title: start, heartbeats every ~30s of playhead, optional pause /
    seek / ad events, then end. Returns a flat list of event dicts.
    """
    rng = random.Random(seed)
    base = start or datetime(2026, 11, 20, 12, 0, 0, tzinfo=timezone.utc)
    events: list[dict] = []
    for s in range(n_sessions):
        session_id = str(uuid.UUID(int=rng.getrandbits(128)))
        user_id = _hash_id(f"user-{rng.randrange(10000)}")
        title = rng.choice(TITLES)
        device = rng.choice(DEVICES)
        region = rng.choice(REGIONS)
        app = rng.choice(APPS)
        ts = base + timedelta(minutes=rng.randrange(0, 600))
        playhead = 0.0
        bitrate = rng.choice([2500, 4500, 8000, 12000])
        n_beats = rng.randrange(3, 25)
        seq = [("session_start", 0.0)]
        for _ in range(n_beats):
            playhead += rng.uniform(20.0, 40.0)
            seq.append(("heartbeat", playhead))
            r = rng.random()
            if r < 0.08:
                seq.append(("pause", playhead))
                seq.append(("resume", playhead))
            elif r < 0.13:
                playhead = max(0.0, playhead + rng.uniform(-120.0, 300.0))
                seq.append(("seek", playhead))
            elif r < 0.20:
                seq.append(("ad_start", playhead))
                seq.append(("ad_end", playhead))
            elif r < 0.23:
                seq.append(("error", playhead))
        seq.append(("session_end", playhead))
        for i, (etype, ph) in enumerate(seq):
            events.append({
                "event_id": str(uuid.UUID(int=rng.getrandbits(128))),
                "session_id": session_id,
                "user_id": user_id,
                "title_id": title,
                "device": device,
                "region": region,
                "app": app,
                "event_type": etype,
                "event_ts": ts + timedelta(seconds=30 * i),
                "playhead_seconds": round(ph, 1),
                "bitrate_kbps": bitrate if etype != "error" else 0,
            })
    events.sort(key=lambda e: (e["event_ts"], e["session_id"]))
    return events


@dataclass
class Topic:
    """A Kafka-style partitioned topic, simulated in memory.

    Producers append with a key; the partition is hash(key) % partitions.
    Consumers read per partition in offset order and commit offsets per
    consumer group, so a re-poll never re-delivers committed events.
    """
    name: str
    partitions: int = 4
    _log: dict[int, list[dict]] = field(default_factory=dict)
    _committed: dict[str, dict[int, int]] = field(default_factory=dict)

    def produce(self, event: dict, key: str) -> tuple[int, int]:
        part = int(hashlib.md5(key.encode()).hexdigest(), 16) % self.partitions
        offset = len(self._log.setdefault(part, []))
        self._log[part].append(event)
        return part, offset

    def poll(self, group: str, max_records: int = 100) -> list[dict]:
        out: list[dict] = []
        committed = self._committed.setdefault(group, {})
        for part in sorted(self._log):
            start = committed.get(part, 0)
            for event in self._log[part][start:start + max_records]:
                out.append(event)
            committed[part] = min(len(self._log[part]),
                                  start + max_records)
        return out

    def committed_offsets(self, group: str) -> dict[int, int]:
        return dict(self._committed.get(group, {}))

    def size(self) -> int:
        return sum(len(v) for v in self._log.values())
