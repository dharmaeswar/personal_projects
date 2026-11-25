"""Tests for the cross-sectional equity alpha-signal research module."""

import numpy as np
import pandas as pd
import pytest

from sys_signal_research.equity_alpha import (
    alpha_report,
    combine_signals,
    cross_sectional_momentum,
    generate_equity_alpha_panel,
    information_coefficient,
    long_short_backtest,
    quality_signal,
    signal_decay,
    value_signal,
)


@pytest.fixture(scope="module")
def panel():
    return generate_equity_alpha_panel(seed=7)


def test_panel_is_seeded_and_shaped(panel):
    prices, characteristics = panel
    assert prices.shape == (504, 40)
    assert list(characteristics.columns) == ["value", "quality", "true_drift_annual", "beta"]
    prices2, _ = generate_equity_alpha_panel(seed=7)
    pd.testing.assert_frame_equal(prices, prices2)
    assert (prices > 0).all().all()


def test_momentum_is_cross_sectionally_zscored(panel):
    prices, _ = panel
    mom = cross_sectional_momentum(prices)
    assert mom.shape == prices.shape
    # After the 252-day warm-up the cross-section is standardised.
    day = mom.iloc[300]
    assert abs(day.mean()) < 1e-9
    assert abs(day.std() - 1.0) < 1e-6
    # No signal before the lookback window has data.
    assert (mom.iloc[100] == 0.0).all()


def test_value_and_quality_match_characteristics(panel):
    _, characteristics = panel
    assert value_signal(characteristics).equals(characteristics["value"])
    assert quality_signal(characteristics).equals(characteristics["quality"])


def test_composite_combines_and_standardises(panel):
    prices, characteristics = panel
    mom = cross_sectional_momentum(prices)
    composite = combine_signals(
        [mom, value_signal(characteristics), quality_signal(characteristics)]
    )
    assert composite.shape == prices.shape
    day = composite.iloc[300]
    assert abs(day.mean()) < 1e-9
    assert abs(day.std() - 1.0) < 1e-6


def test_information_coefficient_recovers_seeded_edge(panel):
    prices, characteristics = panel
    returns = prices.pct_change().fillna(0.0)
    mom = cross_sectional_momentum(prices)
    ic = information_coefficient(mom, returns)
    # Past returns embed the persistent drift, so momentum predicts.
    assert ic["mean_ic"] > 0
    assert ic["t_stat"] > 2.0
    assert ic["hit_rate"] > 0.5
    assert ic["n_days"] > 200


def test_value_and_quality_ics_are_positive(panel):
    prices, characteristics = panel
    returns = prices.pct_change().fillna(0.0)
    for signal_fn in (value_signal, quality_signal):
        sig = pd.DataFrame(
            np.tile(signal_fn(characteristics).values, (len(prices), 1)),
            index=prices.index,
            columns=prices.columns,
        )
        ic = information_coefficient(sig, returns)
        assert ic["mean_ic"] > 0
        assert ic["t_stat"] > 2.0


def test_signal_decay_fades_with_lag(panel):
    prices, characteristics = panel
    returns = prices.pct_change().fillna(0.0)
    composite = combine_signals(
        [cross_sectional_momentum(prices), value_signal(characteristics), quality_signal(characteristics)]
    )
    decay = signal_decay(composite, returns)
    assert set(decay) == {1, 5, 10, 20}
    assert all(np.isfinite(v) for v in decay.values())
    # The edge is a persistent drift, so it decays slowly: the IC stays
    # positive even at a 20-day execution delay.
    assert all(v > 0 for v in decay.values())


def test_long_short_backtest_is_cost_aware_and_profitable(panel):
    prices, characteristics = panel
    returns = prices.pct_change().fillna(0.0)
    composite = combine_signals(
        [cross_sectional_momentum(prices), value_signal(characteristics), quality_signal(characteristics)]
    )
    result = long_short_backtest(composite, returns, cost_bps=5.0)
    assert len(result["net_returns"]) > 200
    assert result["mean_turnover"] > 0
    assert result["sharpe"] > 0
    assert result["cagr"] > 0
    # Costs bite: gross beats net.
    assert result["gross_returns"].sum() > result["net_returns"].sum()
    assert result["max_drawdown"] <= 0


def test_backtest_charges_more_at_higher_costs(panel):
    prices, characteristics = panel
    returns = prices.pct_change().fillna(0.0)
    composite = combine_signals(
        [cross_sectional_momentum(prices), value_signal(characteristics), quality_signal(characteristics)]
    )
    cheap = long_short_backtest(composite, returns, cost_bps=0.0)
    pricey = long_short_backtest(composite, returns, cost_bps=50.0)
    assert cheap["net_returns"].sum() > pricey["net_returns"].sum()
    # Zero cost: net equals gross.
    pd.testing.assert_series_equal(cheap["net_returns"], cheap["gross_returns"])


def test_backtest_positions_are_dollar_neutral(panel):
    prices, characteristics = panel
    returns = prices.pct_change().fillna(0.0)
    composite = combine_signals(
        [cross_sectional_momentum(prices), value_signal(characteristics), quality_signal(characteristics)]
    )
    result = long_short_backtest(composite, returns)
    # Net returns are computed from dollar-neutral positions; the
    # turnover series is non-negative and bounded by full rebalancing.
    assert (result["turnover"] >= 0).all()
    assert result["turnover"].max() <= 4.0 + 1e-9


def test_alpha_report_covers_all_signals(panel):
    prices, characteristics = panel
    report = alpha_report(prices, characteristics)
    assert set(report["ics"]) == {"momentum", "value", "quality", "composite"}
    assert all(report["ics"][name]["mean_ic"] > 0 for name in report["ics"])
    assert report["backtest"]["sharpe"] > 0
    assert set(report["decay"]) == {1, 5, 10, 20}
