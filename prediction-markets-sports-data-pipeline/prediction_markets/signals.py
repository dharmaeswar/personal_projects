"""Signals and a no-look-ahead backtest over cleansed market data.

- Consensus probability per event and time: the mean fair probability
  across books.
- Movement: the change in consensus probability between the first and the
  last snapshot, and the largest single-step move.
- Edge: research-model probability minus the market's consensus fair
  probability at the same time. A bet is placed only when the edge clears
  a threshold, using the odds available at that time — never later odds.
- Backtest: flat $100 stakes on the side with the edge, settled at the
  known outcome, with a simple Kelly-capped stake option. Reports ROI,
  hit rate, and per-event results.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .cleanse import CleanRecord
from .ingest import EVENTS, prob_to_american


@dataclass
class Movement:
    event_id: str
    first_home: float
    last_home: float
    move: float
    max_step: float


@dataclass
class Bet:
    event_id: str
    side: str  # "home" or "away"
    stake: float
    odds: int
    won: bool
    profit: float


def consensus(records: list[CleanRecord]) -> pd.DataFrame:
    """Per (event, timestamp) mean fair probabilities across books."""
    df = pd.DataFrame([{
        "event_id": r.event_id, "ts": r.ts,
        "fair_home": r.fair_home, "fair_away": r.fair_away,
    } for r in records])
    return df.groupby(["event_id", "ts"], as_index=False).mean(numeric_only=True)


def movements(cons: pd.DataFrame) -> list[Movement]:
    out: list[Movement] = []
    for event_id, group in cons.sort_values("ts").groupby("event_id"):
        probs = group["fair_home"].to_numpy()
        steps = np.abs(np.diff(probs)) if len(probs) > 1 else np.array([0.0])
        out.append(Movement(
            event_id=event_id, first_home=float(probs[0]),
            last_home=float(probs[-1]), move=float(probs[-1] - probs[0]),
            max_step=float(steps.max()),
        ))
    return sorted(out, key=lambda m: abs(m.move), reverse=True)


def backtest(records: list[CleanRecord], edge_threshold: float = 0.05,
             stake: float = 100.0) -> dict:
    """Flat-stake backtest. For each event, scan consensus snapshots in
    time order and place one bet at the FIRST time the model-vs-market
    edge clears the threshold, using the odds available at that time.
    The decision uses only data up to that timestamp — never later odds
    or the known outcome."""
    cons = consensus(records)
    model = {e[0]: e[3] for e in EVENTS}
    outcome = {e[0]: e[4] for e in EVENTS}
    bets: list[Bet] = []
    for event_id, group in cons.sort_values("ts").groupby("event_id"):
        for _, row in group.iterrows():
            p_home, p_away = float(row["fair_home"]), float(row["fair_away"])
            edge_home = model[event_id] - p_home
            edge_away = (1.0 - model[event_id]) - p_away
            if edge_home >= edge_threshold and edge_home >= edge_away:
                side, odds = "home", prob_to_american(p_home)
                won = outcome[event_id] == 0
            elif edge_away >= edge_threshold:
                side, odds = "away", prob_to_american(p_away)
                won = outcome[event_id] == 1
            else:
                continue
            if won:
                profit = stake * (100.0 / abs(odds) if odds < 0 else odds / 100.0)
            else:
                profit = -stake
            bets.append(Bet(event_id, side, stake, odds, won, profit))
            break  # one bet per event, at the first qualifying snapshot
    staked = sum(b.stake for b in bets)
    profit = sum(b.profit for b in bets)
    return {
        "bets": len(bets),
        "staked": staked,
        "profit": round(profit, 2),
        "roi": round(profit / staked, 4) if staked else 0.0,
        "hit_rate": round(sum(b.won for b in bets) / len(bets), 3) if bets else 0.0,
        "detail": [b.__dict__ for b in bets],
    }
