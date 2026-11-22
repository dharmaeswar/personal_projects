import numpy as np
import pandas as pd

from sys_signal_research.backtest import (
    apply_vol_target,
    backtest,
    diversification_stats,
    portfolio_metrics,
    risk_parity_weights,
    vol_target_scale,
)
from sys_signal_research.data import daily_returns, generate_prices

PRICES = generate_prices()
ES = PRICES["ES"]


def test_backtest_long_only_rising_market_makes_money():
    idx = pd.bdate_range("2021-01-01", periods=300)
    rising = pd.Series(100.0 * (1.001 ** np.arange(300)), index=idx)
    pos = pd.Series(1.0, index=idx)
    res = backtest(rising, pos, cost_bps=0.0)
    assert res["equity"].iloc[-1] > 1.0
    assert np.allclose(res["return"], res["gross_return"])
    assert (res["cost"] == 0.0).all()


def test_backtest_charges_cost_on_turnover_only():
    pos = pd.Series(1.0, index=ES.index)
    pos.iloc[500:] = -1.0
    res = backtest(ES, pos, cost_bps=10.0)
    assert res["cost"].iloc[0] == 0.0
    assert res["cost"].iloc[1] > 0.0  # entering the long position pays
    assert res["cost"].iloc[2:501].sum() == 0.0  # holding pays nothing
    assert res["cost"].iloc[501] > 0.0  # the flip from +1 to -1 pays, lagged one day
    assert (res["turnover"] >= 0).all()
    assert res["equity"].iloc[-1] < backtest(ES, pos, cost_bps=0.0)["equity"].iloc[-1]


def test_backtest_applies_positions_with_one_day_lag():
    # A position that flips exactly when the price jumps must miss the jump.
    idx = pd.bdate_range("2021-01-01", periods=5)
    prices = pd.Series([100.0, 100.0, 110.0, 110.0, 110.0], index=idx)
    pos = pd.Series([0.0, 0.0, 1.0, 1.0, 1.0], index=idx)
    res = backtest(prices, pos, cost_bps=0.0)
    assert res["return"].iloc[2] == 0.0  # jump day is missed (lag 1)
    assert res["return"].iloc[3] == 0.0  # flat after the jump


def test_vol_target_scale_is_bounded_and_zero_before_window():
    rets = daily_returns(PRICES)["ES"]
    scale = vol_target_scale(rets, target_vol=0.10, window=60)
    assert scale.iloc[:59].eq(0.0).all()
    assert scale.between(0, 3.0).all()
    assert scale.iloc[60:].gt(0).all()


def test_apply_vol_target_scales_positions_down_when_vol_is_high():
    rets = daily_returns(PRICES)["CL"]  # 35% vol instrument
    pos = pd.Series(1.0, index=PRICES.index)
    scaled = apply_vol_target(pos, rets, target_vol=0.10, window=60)
    assert (scaled.iloc[60:] < 1.0).all()
    assert scaled.between(-3, 3).all()


def test_risk_parity_weights_sum_to_one_and_favour_low_vol():
    cov = np.array([[0.04, 0.0], [0.0, 0.01]])  # 20% vol vs 10% vol
    w = risk_parity_weights(cov)
    assert abs(w.sum() - 1.0) < 1e-9
    assert (w >= 0).all()
    assert w[1] > w[0]  # lower-vol asset gets the bigger weight
    assert abs(w[0] - 1.0 / 3.0) < 0.02
    assert abs(w[1] - 2.0 / 3.0) < 0.02


def test_risk_parity_falls_back_on_bad_input():
    w = risk_parity_weights(np.array([[0.0, 0.0], [0.0, 0.01]]))
    assert abs(w.sum() - 1.0) < 1e-9


def test_portfolio_metrics_on_a_known_curve():
    idx = pd.bdate_range("2021-01-01", periods=253)
    equity = pd.Series(100.0 * (1.001 ** np.arange(253)), index=idx)
    m = portfolio_metrics(equity)
    assert m["total_return"] > 0.28
    assert m["max_drawdown"] == 0.0
    assert m["sharpe"] > 5  # smooth steady climb
    assert m["n_days"] == 252


def test_portfolio_metrics_drawdown_is_negative_on_a_fall():
    idx = pd.bdate_range("2021-01-01", periods=10)
    equity = pd.Series([100, 110, 105, 90, 95, 100, 100, 100, 100, 100], index=idx, dtype=float)
    m = portfolio_metrics(equity)
    assert abs(m["max_drawdown"] - (90.0 / 110.0 - 1.0)) < 1e-9
    assert m["total_return"] == 0.0


def test_diversification_stats():
    rng = np.random.default_rng(0)
    a = pd.Series(rng.standard_normal(500))
    b = pd.Series(rng.standard_normal(500))
    stats = diversification_stats(pd.DataFrame({"a": a, "b": b}))
    assert abs(stats["avg_correlation"]) < 0.15
    identical = diversification_stats(pd.DataFrame({"a": a, "b": a}))
    assert abs(identical["avg_correlation"] - 1.0) < 1e-9
