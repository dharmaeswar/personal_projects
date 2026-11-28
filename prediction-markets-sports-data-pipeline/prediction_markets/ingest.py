"""Seeded synthetic prediction-market / sports-odds feed.

Generates deterministic market snapshots for a set of sports matches and
geopolitical questions, as they would arrive from several sportsbooks:
American odds per outcome, per book, timestamped every few minutes.

All data is synthetic and seeded. No real odds, prices, or events are used,
and nothing here is a claim about any real book, market, or outcome.
"""

from __future__ import annotations

import csv
import math
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

BOOKS = ("BookA", "BookB", "BookC")

# (event_id, label, kind, model_prob_home, outcome) — model_prob is the
# research model's pre-event probability for the first outcome; outcome is
# the eventual winner (0 = first outcome, 1 = second outcome).
EVENTS = [
    ("NFL-001", "Kansas City vs Buffalo", "sports", 0.58, 0),
    ("NFL-002", "Philadelphia vs Dallas", "sports", 0.52, 1),
    ("NBA-001", "Boston vs New York", "sports", 0.61, 0),
    ("NBA-002", "Denver vs LA Lakers", "sports", 0.47, 1),
    ("SOC-001", "Arsenal vs Chelsea", "sports", 0.55, 0),
    ("SOC-002", "Real Madrid vs Barcelona", "sports", 0.49, 1),
    ("TEN-001", "Alcaraz vs Sinner", "sports", 0.54, 0),
    ("NHL-001", "Edmonton vs Florida", "sports", 0.50, 1),
    ("GEO-001", "Central bank cuts rates in March?", "geopolitical", 0.42, 1),
    ("GEO-002", "Election: incumbent party retains control?", "geopolitical", 0.57, 0),
    ("GEO-003", "Trade deal signed before June?", "geopolitical", 0.63, 1),
    ("GEO-004", "Oil above $90 at quarter end?", "geopolitical", 0.38, 0),
]

SNAPSHOT_FIELDS = ("event_id", "book", "ts", "odds_home", "odds_away")


@dataclass
class Snapshot:
    event_id: str
    book: str
    ts: datetime
    odds_home: int | None
    odds_away: int | None

    def to_row(self) -> dict:
        return {
            "event_id": self.event_id,
            "book": self.book,
            "ts": self.ts.isoformat(),
            "odds_home": "" if self.odds_home is None else self.odds_home,
            "odds_away": "" if self.odds_away is None else self.odds_away,
        }


def american_to_prob(odds: int) -> float:
    """Convert American odds to an implied probability."""
    if odds > 0:
        return 100.0 / (odds + 100.0)
    return -odds / (-odds + 100.0)


def prob_to_american(prob: float) -> int:
    """Convert an implied probability to American odds (rounded)."""
    prob = min(max(prob, 0.01), 0.99)
    if prob >= 0.5:
        return -round(100.0 * prob / (1.0 - prob))
    return round(100.0 * (1.0 - prob) / prob)


def generate_feed(seed: int = 7, snapshots_per_event: int = 24,
                  start: datetime | None = None) -> list[Snapshot]:
    """Generate the full seeded snapshot feed.

    Each event gets one snapshot per book every 5 minutes. Odds drift from
    the model's probability toward the eventual outcome as the event
    approaches, with per-book noise. A small number of rows are deliberately
    broken (missing odds, stale timestamp, exact duplicate) so the cleanse
    stage has real defects to catch.
    """
    rng = random.Random(seed)
    start = start or datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)
    out: list[Snapshot] = []
    for event_id, _label, _kind, model_p, outcome in EVENTS:
        # The market starts mispriced — it underrates the research model's
        # favoured side by ~12 points — and converges toward the model's
        # (calibrated) probability over the day. Early model-vs-market
        # edges are therefore usually real. Four events are upsets
        # (NFL-002, NHL-001, GEO-003, GEO-004): the outcome goes against
        # the model's favourite, so those edge bets lose — the backtest
        # measures the pipeline, not a guaranteed edge.
        bias = -0.12 if model_p >= 0.5 else 0.12
        start_p = min(max(model_p + bias, 0.05), 0.95)
        for step in range(snapshots_per_event):
            ts = start + timedelta(minutes=5 * step)
            # Market converges toward the model probability over time.
            w = step / max(snapshots_per_event - 1, 1)
            mid = start_p + (model_p - start_p) * w
            for book in BOOKS:
                noise = rng.gauss(0, 0.015)
                p_home = min(max(mid + noise, 0.05), 0.95)
                # Books carry a ~4.5% overround: inflate both implied probs.
                over = 1.045
                p_home_raw = p_home * over
                p_away_raw = (1.0 - p_home) * over
                out.append(Snapshot(
                    event_id=event_id, book=book, ts=ts,
                    odds_home=prob_to_american(p_home_raw),
                    odds_away=prob_to_american(p_away_raw),
                ))
    # Deliberate defects: 2 missing odds, 1 stale timestamp, 2 exact dupes.
    out[5] = Snapshot(out[5].event_id, out[5].book, out[5].ts, None, out[5].odds_away)
    out[40] = Snapshot(out[40].event_id, out[40].book, out[40].ts, out[40].odds_home, None)
    stale = out[100]
    out[100] = Snapshot(stale.event_id, stale.book,
                        stale.ts - timedelta(hours=3), stale.odds_home, stale.odds_away)
    out.append(out[10])
    out.append(out[200])
    rng.shuffle(out)
    return out


def write_feed_csv(snapshots: list[Snapshot], path: str) -> int:
    with open(path, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=SNAPSHOT_FIELDS)
        writer.writeheader()
        for snap in snapshots:
            writer.writerow(snap.to_row())
    return len(snapshots)


def read_feed_csv(path: str) -> list[Snapshot]:
    rows: list[Snapshot] = []
    with open(path, newline="") as fh:
        for row in csv.DictReader(fh):
            rows.append(Snapshot(
                event_id=row["event_id"], book=row["book"],
                ts=datetime.fromisoformat(row["ts"]),
                odds_home=int(row["odds_home"]) if row["odds_home"] else None,
                odds_away=int(row["odds_away"]) if row["odds_away"] else None,
            ))
    return rows
