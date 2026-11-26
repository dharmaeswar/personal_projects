"""Tests for research tooling: signals and backtest."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from replay.backtest import backtest, backtest_ticks, momentum_signal
from replay.ingest import Tick, generate_ticks


def test_momentum_signal_flat_then_trend():
    closes = [100.0, 100.0, 100.0, 101.0, 102.0, 103.0]
    signals = momentum_signal(closes, lookback=3)
    assert signals[:3] == [0, 0, 0]
    assert signals[3:] == [1, 1, 1]


def test_momentum_signal_below_mean_is_short():
    closes = [103.0, 102.0, 101.0, 100.0, 99.0, 98.0]
    signals = momentum_signal(closes, lookback=3)
    assert signals[3:] == [-1, -1, -1]


def test_backtest_no_lookahead_and_metrics():
    closes = [100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0]
    result = backtest(closes, lookback=2)
    assert result["bars"] == 7
    assert len(result["returns"]) == 6
    assert result["total_return"] > 0
    assert 0.0 <= result["max_drawdown"] <= 1.0
    assert result["trades"] > 0


def test_backtest_requires_enough_data():
    with pytest.raises(ValueError):
        backtest([100.0, 101.0], lookback=2)


def test_backtest_ticks_end_to_end():
    ticks = generate_ticks("ES", 1_000_000, 2_000, seed=21)
    # force every tick to be a trade so bars exist
    ticks = [Tick(t.ts_ns, t.symbol, "T", t.price, t.size) for t in ticks]
    result = backtest_ticks(ticks, bar_ns=1_000_000, lookback=5)
    assert result["bars"] > 0
    assert result["trades"] >= 0
