"""Deterministic replay engine.

Merges tick streams from many symbols into one strictly time-ordered event
stream and drives them through a simulation loop — the same shape as a game
engine's replay loop or a backtester's event loop. Determinism is the point:
the same input and the same handlers always produce the same event order
and the same outputs, so a researcher can reproduce a run exactly.
"""

from __future__ import annotations

import heapq
from collections.abc import Callable, Iterable

from .ingest import Tick

Handler = Callable[[Tick, int], None]  # handler(tick, event_index)


class ReplayEngine:
    """Time-ordered, deterministic replay over one or more tick streams."""

    def __init__(self, streams: Iterable[Iterable[Tick]]):
        self._streams = [iter(s) for s in streams]
        self.events_seen = 0
        self.max_lag_ns = 0

    def run(self, handlers: list[Handler], limit: int | None = None) -> dict:
        """Replay all streams in timestamp order, calling each handler.

        Ties on timestamp break by stream order, so the result is fully
        deterministic. Returns run stats.
        """
        heap: list[tuple[int, int, Tick]] = []
        for idx, stream in enumerate(self._streams):
            first = next(stream, None)
            if first is not None:
                heapq.heappush(heap, (first.ts_ns, idx, first))
        last_ts: int | None = None
        while heap:
            if limit is not None and self.events_seen >= limit:
                break
            ts_ns, idx, tick = heapq.heappop(heap)
            if last_ts is not None:
                self.max_lag_ns = max(self.max_lag_ns, ts_ns - last_ts)
            last_ts = ts_ns
            for handler in handlers:
                handler(tick, self.events_seen)
            self.events_seen += 1
            nxt = next(self._streams[idx], None)
            if nxt is not None:
                heapq.heappush(heap, (nxt.ts_ns, idx, nxt))
        return {
            "events": self.events_seen,
            "max_gap_ns": self.max_lag_ns,
            "streams_drained": len(self._streams),
        }


def slice_window(ticks: list[Tick], start_ns: int, end_ns: int) -> list[Tick]:
    """Return the ticks inside [start_ns, end_ns], in original order."""
    if start_ns > end_ns:
        raise ValueError("start_ns must not exceed end_ns")
    return [t for t in ticks if start_ns <= t.ts_ns <= end_ns]


def to_bars(ticks: list[Tick], bar_ns: int) -> list[dict]:
    """Aggregate trade ticks into time bars (open/high/low/close/volume)."""
    if bar_ns <= 0:
        raise ValueError("bar_ns must be positive")
    trades = [t for t in ticks if t.side == "T"]
    bars: list[dict] = []
    current: dict | None = None
    for t in trades:
        bucket = (t.ts_ns // bar_ns) * bar_ns
        if current is None or current["bar_start_ns"] != bucket:
            if current is not None:
                bars.append(current)
            current = {
                "bar_start_ns": bucket,
                "open": t.price,
                "high": t.price,
                "low": t.price,
                "close": t.price,
                "volume": t.size,
                "trades": 1,
            }
        else:
            current["high"] = max(current["high"], t.price)
            current["low"] = min(current["low"], t.price)
            current["close"] = t.price
            current["volume"] += t.size
            current["trades"] += 1
    if current is not None:
        bars.append(current)
    return bars
