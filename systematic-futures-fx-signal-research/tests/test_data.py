import numpy as np
import pandas as pd

from sys_signal_research.data import (
    CARRY_BASE,
    INSTRUMENTS,
    daily_returns,
    generate_carry,
    generate_prices,
)


def test_prices_cover_all_instruments_and_are_positive():
    prices = generate_prices()
    assert list(prices.columns) == list(INSTRUMENTS)
    assert len(prices) > 1200
    assert (prices > 0).all().all()
    assert prices.index.is_monotonic_increasing
    assert prices.index[0] == pd.Timestamp("2021-01-01")
    assert prices.index[-1] == pd.Timestamp("2025-12-31")


def test_prices_are_deterministic_for_a_seed():
    a = generate_prices(seed=42)
    b = generate_prices(seed=42)
    pd.testing.assert_frame_equal(a, b)
    c = generate_prices(seed=43)
    assert not a.equals(c)


def test_vol_regime_changes_show_up_in_realised_vol():
    prices = generate_prices()
    rets = daily_returns(prices)["CL"]
    n = len(rets)
    first_vol = rets.iloc[: n // 3].std()
    last_vol = rets.iloc[2 * n // 3 :].std()
    assert last_vol > first_vol  # stressed regime is twice the calm one


def test_carry_is_fx_only_and_mean_reverts_to_base():
    prices = generate_prices()
    carry = generate_carry(prices)
    assert list(carry.columns) == list(CARRY_BASE)
    assert carry.index.equals(prices.index)
    assert carry.notna().all().all()
    for pair, base in CARRY_BASE.items():
        assert abs(carry[pair].mean() - base) < 0.5
        assert carry[pair].min() > -8 and carry[pair].max() < 3


def test_daily_returns_shape_and_no_nans():
    prices = generate_prices()
    rets = daily_returns(prices)
    assert len(rets) == len(prices) - 1
    assert rets.notna().all().all()
    assert np.allclose(rets["ES"].iloc[0], prices["ES"].iloc[1] / prices["ES"].iloc[0] - 1)
