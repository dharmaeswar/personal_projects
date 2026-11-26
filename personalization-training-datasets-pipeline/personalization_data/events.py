"""Seeded synthetic content-interaction events.

Mirrors the raw event stream a News & Entertainment ML team would read from
Kafka / Kinesis: one row per playback interaction (impression, view start,
view complete, like, share, skip) across web, mobile, and connected TV.

Spark equivalent: a streaming read of the raw topic, e.g.
``spark.readStream.format("kafka").option("subscribe", "content-interactions")``.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta

import pandas as pd

EVENT_TYPES = ["impression", "view_start", "view_complete", "like", "share", "skip"]
GENRES = ["news", "drama", "documentary", "sports", "kids", "reality"]
SURFACES = ["web", "mobile", "ctv"]
DEVICES = ["ios", "android", "roku", "firetv", "browser"]
COUNTRIES = ["US", "CA", "GB"]

COLUMNS = [
    "event_id",
    "user_id",
    "content_id",
    "event_type",
    "event_ts",
    "ingested_at",
    "device",
    "surface",
    "country",
    "genre",
    "title_type",
    "content_duration_s",
    "watch_seconds",
]


def generate_events(n_impressions: int = 400, seed: int = 42,
                    start: str = "2026-11-01", days: int = 14) -> pd.DataFrame:
    """Generate a seeded stream of content-interaction events.

    Every impression seeds a small chain of follow-on events for the same
    (user, content) pair, so labels can be derived from what happens *after*
    the impression. About 2% of events are re-delivered with the same
    ``event_id`` and a later ``ingested_at`` (producer retries).
    """
    rng = random.Random(seed)
    base = datetime.fromisoformat(start)
    users = [f"U{i:04d}" for i in range(1, 121)]
    contents = {}
    for i in range(1, 61):
        contents[f"C{i:04d}"] = {
            "genre": rng.choice(GENRES),
            "title_type": rng.choice(["movie", "series", "news_segment", "live_event"]),
            "content_duration_s": rng.choice([180, 600, 1500, 2700, 3600]),
        }

    rows = []
    seq = 0

    def _emit(user, content, etype, ts, watch=None):
        nonlocal seq
        seq += 1
        meta = contents[content]
        ingest = ts + timedelta(seconds=rng.randint(1, 300))
        rows.append({
            "event_id": f"E{seq:06d}",
            "user_id": user,
            "content_id": content,
            "event_type": etype,
            "event_ts": ts,
            "ingested_at": ingest,
            "device": rng.choice(DEVICES),
            "surface": rng.choice(SURFACES),
            "country": rng.choice(COUNTRIES),
            "genre": meta["genre"],
            "title_type": meta["title_type"],
            "content_duration_s": meta["content_duration_s"],
            "watch_seconds": watch,
        })

    for _ in range(n_impressions):
        user = rng.choice(users)
        content = rng.choice(list(contents))
        ts = base + timedelta(
            days=rng.randint(0, days - 1),
            seconds=rng.randint(0, 86399),
        )
        duration = contents[content]["content_duration_s"]
        _emit(user, content, "impression", ts)
        roll = rng.random()
        if roll < 0.72:  # user starts watching
            start_ts = ts + timedelta(seconds=rng.randint(5, 120))
            watch = round(rng.uniform(0.1, 1.0) * duration, 1)
            _emit(user, content, "view_start", start_ts, watch=watch)
            if rng.random() < 0.55:  # watches to the end
                _emit(user, content, "view_complete",
                      start_ts + timedelta(seconds=int(watch)), watch=watch)
            if rng.random() < 0.18:
                _emit(user, content, "like",
                      start_ts + timedelta(seconds=rng.randint(60, 600)))
            if rng.random() < 0.06:
                _emit(user, content, "share",
                      start_ts + timedelta(seconds=rng.randint(60, 900)))
        elif roll < 0.88:  # skips quickly
            _emit(user, content, "skip", ts + timedelta(seconds=rng.randint(2, 30)),
                  watch=round(rng.uniform(0, 15), 1))

    df = pd.DataFrame(rows, columns=COLUMNS)
    # Re-deliver ~2% of events: same event_id, later ingested_at (producer retry).
    dupes = df.sample(frac=0.02, random_state=seed).copy()
    dupes["ingested_at"] = dupes["ingested_at"] + pd.Timedelta(minutes=5)
    df = pd.concat([df, dupes], ignore_index=True)
    df["event_ts"] = pd.to_datetime(df["event_ts"])
    df["ingested_at"] = pd.to_datetime(df["ingested_at"])
    return df.sort_values("event_ts").reset_index(drop=True)
