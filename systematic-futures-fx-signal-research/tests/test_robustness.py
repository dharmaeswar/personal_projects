import numpy as np
import pandas as pd

from sys_signal_research.__main__ import run_research
from sys_signal_research.backtest import backtest
from sys_signal_research.data import generate_prices
from sys_signal_research.robustness import (
    cost_sensitivity,
    signal_decay,
    sim_vs_actual_gap,
    walk_forward,
)
from sys_signal_research.signals import time_series_momentum

PRICES = generate_prices()
ES = PRICES["ES"]
MOM = time_series_momentum(ES)


def test_walk_forward_returns_one_row_per_fold_after_the_first():
    rows = walk_forward(
        ES,
        lambda p, lookback=252: time_series_momentum(p, lookback=lookback),
        param_grid=[{"lookback": 63}, {"lookback": 252}],
        n_folds=4,
        cost_bps=2.0,
    )
    assert len(rows) == 3
    for row in rows:
        assert row["chosen_params"] in ({"lookback": 63}, {"lookback": 252})
        assert np.isfinite(row["in_sample_sharpe"])
        assert np.isfinite(row["out_of_sample_sharpe"])


def test_cost_sensitivity_sharpe_falls_as_costs_rise():
    out = cost_sensitivity(ES, MOM, cost_levels=(0, 2, 5, 10))
    assert list(out) == [0.0, 2.0, 5.0, 10.0]
    assert out[0.0] >= out[2.0] >= out[5.0] >= out[10.0]


def test_signal_decay_returns_a_value_per_lag():
    decay = signal_decay(ES, MOM, max_lag=5)
    assert list(decay) == [0, 1, 2, 3, 4, 5]
    assert all(-1.0 <= v <= 1.0 for v in decay.values())


def test_sim_vs_actual_gap_costs_eat_part_of_the_edge():
    res = backtest(ES, MOM, cost_bps=2.0)
    gap = sim_vs_actual_gap(res)
    assert gap["total_cost_paid"] > 0
    assert gap["net_total_return"] <= gap["gross_total_return"]
    assert gap["avg_daily_turnover"] > 0
    assert 0.0 <= gap["cost_share_of_gross_edge"] or gap["gross_total_return"] <= 0


def test_full_research_report_runs_and_is_consistent():
    report = run_research()
    assert len(report["instruments"]) == 9
    assert report["n_days"] > 1200
    m = report["portfolio_metrics"]
    assert np.isfinite(m["sharpe"])
    assert m["max_drawdown"] <= 0
    assert abs(sum(report["risk_parity_weights"].values()) - 1.0) < 1e-6
    assert len(report["walk_forward_es_momentum"]) == 3
    assert len(report["cost_sensitivity_es_momentum"]) == 5
    assert len(report["signal_decay_es_momentum"]) == 11
    assert report["sim_vs_actual_gap_es"]["total_cost_paid"] > 0
