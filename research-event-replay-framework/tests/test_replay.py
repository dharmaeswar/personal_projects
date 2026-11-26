"""Tests for the deterministic replay engine and bar aggregation."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from replay.ingest import Tick, generate_ticks
from replay.replay import ReplayEngine, slice_window, to_bars


def test_replay_merges_in_time_order():
    a = generate_ticks("ES", 1_000_000, 50, seed=1)
    b = generate_ticks("NQ", 1_000_000, 50, seed=2)
    seen: list[Tick] = []
    engine = ReplayEngine([a, b])
    stats = engine.run([lambda t, i: seen.append(t)])
    assert stats["events"] == 100
    assert all(seen[i].ts_ns <= seen[i + 1].ts_ns for i in range(99))


def test_replay_is_deterministic():
    a = generate_ticks("ES", 1_000_000, 40, seed=1)
    b = generate_ticks("NQ", 1_000_000, 40, seed=2)
    first: list[int] = []
    second: list[int] = []
    ReplayEngine([a, b]).run([lambda t, i: first.append(t.ts_ns)])
    ReplayEngine([generate_ticks("ES", 1_000_000, 40, seed=1),
                  generate_ticks("NQ", 1_000_000, 40, seed=2)]).run(
        [lambda t, i: second.append(t.ts_ns)])
    assert first == second


def test_replay_limit():
    a = generate_ticks("ES", 1_000_000, 50, seed=1)
    seen: list[Tick] = []
    stats = ReplayEngine([a]).run([lambda t, i: seen.append(t)], limit=10)
    assert stats["events"] == 10 and len(seen) == 10


def test_slice_window_and_bounds():
    ticks = generate_ticks("ES", 1_000_000, 100, seed=3)
    lo, hi = ticks[10].ts_ns, ticks[20].ts_ns
    window = slice_window(ticks, lo, hi)
    assert len(window) == 11
    assert all(lo <= t.ts_ns <= hi for t in window)
    with pytest.raises(ValueError):
        slice_window(ticks, hi, lo)


def test_to_bars_aggregates_trades_only():
    ticks = [
        Tick(0, "ES", "T", 100.0, 10),
        Tick(1, "ES", "B", 99.0, 5),
        Tick(2, "ES", "T", 102.0, 20),
        Tick(10_000_000_001, "ES", "T", 101.0, 7),
    ]
    bars = to_bars(ticks, bar_ns=10_000_000_000)
    assert len(bars) == 2
    assert bars[0]["open"] == 100.0 and bars[0]["high"] == 102.0
    assert bars[0]["low"] == 100.0 and bars[0]["close"] == 102.0
    assert bars[0]["volume"] == 30 and bars[0]["trades"] == 2
    assert bars[1]["volume"] == 7
