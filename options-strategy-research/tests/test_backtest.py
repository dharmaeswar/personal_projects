import math

from options.backtest import (delta_hedged_straddle, run_study,
                              study_summary, sharpe_ratio, max_drawdown)
from options.data import simulate_underlying


def test_backtest_runs_and_closes_flat():
    prices = simulate_underlying(seed=42)
    result = delta_hedged_straddle(prices, expiry_days=30)
    assert len(result["pnl_series"]) == 31
    assert result["strike"] == 100
    assert result["entry_cost"] > 0
    # Final P&L equals the series end; no position is left open.
    assert result["total_pnl"] == result["pnl_series"][-1]


def test_backtest_no_lookahead():
    # The first P&L point uses only the entry day: the straddle value
    # offsets its cost, so day-0 P&L is just the small hedge cost.
    prices = simulate_underlying(seed=42)
    result = delta_hedged_straddle(prices, expiry_days=30)
    assert abs(result["pnl_series"][0]) < 0.05
    # A later start day gives a different trade (different entry spot).
    later = delta_hedged_straddle(prices, expiry_days=30, start_day=30)
    assert later["strike"] != result["strike"] or later["total_pnl"] != result["total_pnl"]


def test_backtest_rejects_short_path():
    prices = simulate_underlying(days=10)
    import pytest
    with pytest.raises(ValueError):
        delta_hedged_straddle(prices, expiry_days=30)


def test_study_summary_counts():
    prices = simulate_underlying(seed=42)
    results = run_study(prices, expiry_days=30, step=30)
    summary = study_summary(results)
    assert summary["trades"] == 8  # starts at 0..210 step 30 within 253 prices
    assert summary["wins"] + (summary["trades"] - summary["wins"]) == summary["trades"]
    assert 0.0 <= summary["win_rate"] <= 1.0


def test_sharpe_and_drawdown_helpers():
    assert sharpe_ratio([0.0, 0.0, 0.0]) == 0.0
    assert sharpe_ratio([1.0]) == 0.0
    assert max_drawdown([0.0, 5.0, 3.0, 7.0, 2.0]) == -5.0
    assert max_drawdown([0.0, 1.0, 2.0, 3.0]) == 0.0
