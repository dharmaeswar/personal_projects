"""Robust research procedures: walk-forward validation, cost and
slippage sensitivity, signal decay, and the simulated-vs-actual gap.

A signal that only works in-sample is not a trading idea. These checks
quantify how much of a backtest survives out-of-sample data, realistic
costs, and slower execution — the gap between simulated and actual
performance that the research process has to close.
"""

import numpy as np
import pandas as pd

from .backtest import backtest, portfolio_metrics


def walk_forward(prices, signal_fn, param_grid, n_folds=4, cost_bps=2.0):
    """Walk-forward test: pick the best parameter in-sample, test it out.

    The sample is split into ``n_folds`` contiguous blocks. For each
    fold, every parameter set in ``param_grid`` is backtested on all
    data before the fold (in-sample); the set with the best in-sample
    Sharpe is then backtested on the fold itself (out-of-sample).
    Returns one row per fold with the chosen parameters and the
    in-sample / out-of-sample Sharpe ratios.
    """
    index = prices.index
    n = len(index)
    fold_len = n // n_folds
    rows = []
    for fold in range(1, n_folds):
        train_end = fold * fold_len
        test_end = min((fold + 1) * fold_len, n)
        train = prices.iloc[:train_end]
        test = prices.iloc[train_end:test_end]
        best_params, best_sharpe = None, -np.inf
        for params in param_grid:
            pos = signal_fn(train, **params)
            res = backtest(train, pos, cost_bps=cost_bps)
            m = portfolio_metrics(res["equity"])
            if m["sharpe"] > best_sharpe:
                best_sharpe, best_params = m["sharpe"], params
        oos_pos = signal_fn(test, **best_params)
        oos = backtest(test, oos_pos, cost_bps=cost_bps)
        oos_m = portfolio_metrics(oos["equity"])
        rows.append(
            {
                "fold": fold,
                "chosen_params": best_params,
                "in_sample_sharpe": round(float(best_sharpe), 3),
                "out_of_sample_sharpe": round(float(oos_m["sharpe"]), 3),
                "out_of_sample_return": round(float(oos_m["total_return"]), 4),
            }
        )
    return rows


def cost_sensitivity(prices, positions, cost_levels=(0, 1, 2, 5, 10)):
    """Sharpe ratio of one signal at several transaction-cost levels."""
    out = {}
    for bps in cost_levels:
        res = backtest(prices, positions, cost_bps=float(bps))
        out[float(bps)] = round(float(portfolio_metrics(res["equity"])["sharpe"]), 3)
    return out


def signal_decay(prices, positions, max_lag=20):
    """How fast a signal's edge fades if execution is delayed.

    For each lag in days, the position is applied ``lag`` days late and
    the correlation between the delayed strategy return and the
    next-day market return is reported. A signal whose edge survives
    several days of delay is robust to slow execution; one that dies
    at lag 1 is not tradable in practice.
    """
    rets = prices.pct_change()
    out = {}
    for lag in range(0, max_lag + 1):
        delayed = positions.shift(1 + lag).fillna(0.0)
        strat = delayed * rets
        corr = float(np.corrcoef(strat.fillna(0.0), rets.fillna(0.0))[0, 1])
        out[lag] = round(corr, 4) if np.isfinite(corr) else 0.0
    return out


def sim_vs_actual_gap(backtest_result):
    """Split a backtest into gross edge, cost drag, and net result.

    The gap between a simulated backtest and what a live book earns is
    mostly turnover cost and slippage. This reports the gross return,
    the total cost paid, the cost as a share of the gross edge, and the
    average daily turnover, so a researcher can see whether the idea
    survives realistic friction.
    """
    gross_total = float((1.0 + backtest_result["gross_return"]).prod() - 1.0)
    net_total = float(backtest_result["equity"].iloc[-1] - 1.0)
    cost_total = float(backtest_result["cost"].sum())
    gap_share = float(cost_total / gross_total) if gross_total > 0 else 0.0
    return {
        "gross_total_return": round(gross_total, 4),
        "net_total_return": round(net_total, 4),
        "total_cost_paid": round(cost_total, 4),
        "cost_share_of_gross_edge": round(gap_share, 3),
        "avg_daily_turnover": round(float(backtest_result["turnover"].mean()), 4),
    }
