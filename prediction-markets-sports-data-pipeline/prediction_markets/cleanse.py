"""Cleanse raw odds snapshots into research-ready records.

Steps, in order: drop exact duplicates, quarantine rows with missing odds,
quarantine stale rows (a lone timestamp far behind its own stream — the
feed's normal cadence is 5 minutes), convert American odds to implied
probabilities, and remove the book's overround (vig) so the two fair
probabilities sum to 1. Every dropped or quarantined row is reported,
never silently fixed.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from .ingest import Snapshot, american_to_prob

# A row is stale when the next snapshot for the same (event, book) stream
# arrives more than this long later (normal cadence is 5 minutes).
STALE_GAP = timedelta(minutes=15)


@dataclass
class CleanRecord:
    event_id: str
    book: str
    ts: datetime
    fair_home: float
    fair_away: float
    overround: float


@dataclass
class CleanseReport:
    total: int
    kept: int
    duplicates: int
    missing_odds: int
    stale: int
    quarantined: list[dict]

    def as_dict(self) -> dict:
        return {
            "total": self.total,
            "kept": self.kept,
            "duplicates": self.duplicates,
            "missing_odds": self.missing_odds,
            "stale": self.stale,
            "quarantined": self.quarantined,
        }


def remove_vig(p_home_raw: float, p_away_raw: float) -> tuple[float, float, float]:
    """Normalise two raw implied probabilities so they sum to 1.

    Returns (fair_home, fair_away, overround) where overround is the raw
    sum minus 1 (typically ~0.045 for a 4.5% book margin).
    """
    total = p_home_raw + p_away_raw
    if total <= 0:
        raise ValueError("implied probabilities must sum above zero")
    return p_home_raw / total, p_away_raw / total, total - 1.0


def cleanse(snapshots: list[Snapshot]) -> tuple[list[CleanRecord], CleanseReport]:
    # Gap to the next snapshot in the same (event, book) stream, by row id.
    ordered = sorted(snapshots, key=lambda s: (s.event_id, s.book, s.ts))
    gap_after: dict[int, timedelta] = {}
    for i, snap in enumerate(ordered):
        nxt = ordered[i + 1] if i + 1 < len(ordered) else None
        if nxt is not None and nxt.event_id == snap.event_id and nxt.book == snap.book:
            gap_after[id(snap)] = nxt.ts - snap.ts

    seen: set[tuple] = set()
    kept: list[CleanRecord] = []
    quarantined: list[dict] = []
    duplicates = missing = stale = 0
    for snap in sorted(snapshots, key=lambda s: (s.ts, s.event_id, s.book)):
        key = (snap.event_id, snap.book, snap.ts, snap.odds_home, snap.odds_away)
        if key in seen:
            duplicates += 1
            quarantined.append({"reason": "duplicate", "row": snap.to_row()})
            continue
        seen.add(key)
        if snap.odds_home is None or snap.odds_away is None:
            missing += 1
            quarantined.append({"reason": "missing_odds", "row": snap.to_row()})
            continue
        gap = gap_after.get(id(snap))
        if gap is not None and gap > STALE_GAP:
            stale += 1
            quarantined.append({"reason": "stale_timestamp", "row": snap.to_row()})
            continue
        p_home_raw = american_to_prob(snap.odds_home)
        p_away_raw = american_to_prob(snap.odds_away)
        fair_home, fair_away, over = remove_vig(p_home_raw, p_away_raw)
        kept.append(CleanRecord(snap.event_id, snap.book, snap.ts,
                                fair_home, fair_away, over))
    report = CleanseReport(total=len(snapshots), kept=len(kept),
                           duplicates=duplicates, missing_odds=missing,
                           stale=stale, quarantined=quarantined)
    return kept, report
