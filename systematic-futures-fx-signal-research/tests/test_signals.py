import numpy as np
import pandas as pd

from sys_signal_research.data import generate_carry, generate_prices
from sys_signal_research.signals import (
    carry_signal,
    combine_signals,
    mean_reversion,
    moving_average_crossover,
    time_series_momentum,
)

PRICES = generate_prices()


def test_momentum_is_zero_until_lookback_then_bounded():
    pos = time_series_momentum(PRICES["ES"], lookback=252)
    assert pos.iloc[:252].eq(0.0).all()
    assert pos.between(-1, 1).all()
    assert pos.notna().all()


def test_momentum_follows_a_strong_trend():
    idx = pd.bdate_range("2021-01-01", periods=400)
    rising = pd.Series(100.0 * (1.001 ** np.arange(400)), index=idx)
    pos = time_series_momentum(rising, lookback=63)
    assert pos.iloc[-1] > 0.9
    falling = pd.Series(100.0 * (0.999 ** np.arange(400)), index=idx)
    assert time_series_momentum(falling, lookback=63).iloc[-1] < -0.9


def test_crossover_is_zero_until_slow_window_then_plus_or_minus_one():
    pos = moving_average_crossover(PRICES["ES"], fast=50, slow=200)
    assert pos.iloc[:199].eq(0.0).all()
    assert set(pos.dropna().unique()) <= {-1.0, 0.0, 1.0}


def test_carry_scales_with_the_differential_and_caps():
    carry = pd.Series([4.0, 2.0, 0.0, -2.0, -4.0])
    pos = carry_signal(carry)
    assert list(pos) == [1.0, 1.0, 0.0, -1.0, -1.0]
    assert list(carry_signal(pd.Series([0.5, -1.0]))) == [0.25, -0.5]


def test_mean_reversion_fades_moves_and_is_bounded():
    pos = mean_reversion(PRICES["GC"], window=20)
    assert pos.iloc[:19].eq(0.0).all()
    assert pos.between(-1, 1).all()
    assert pos.notna().all()
    idx = pd.bdate_range("2021-01-01", periods=60)
    flat = pd.Series(100.0, index=idx)
    assert mean_reversion(flat, window=20).eq(0.0).all()


def test_combine_signals_weights_and_clips():
    a = pd.Series([1.0, 1.0, -1.0])
    b = pd.Series([1.0, -1.0, -1.0])
    combined = combine_signals({"a": a, "b": b})
    assert list(combined) == [1.0, 0.0, -1.0]
    weighted = combine_signals({"a": a, "b": b}, weights={"a": 3.0, "b": 1.0})
    assert list(weighted) == [1.0, 0.5, -1.0]


def test_no_signal_uses_future_data():
    # Shifting the input by one day must shift the output the same way.
    pos = time_series_momentum(PRICES["ES"], lookback=63)
    shifted = time_series_momentum(PRICES["ES"].shift(1), lookback=63)
    pd.testing.assert_series_equal(pos.shift(1).fillna(0.0), shifted.fillna(0.0))
