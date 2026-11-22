import numpy as np
import pandas as pd
import pytest

from trade_reg_analytics.data import WarehouseConfig, generate_orders_trades
from trade_reg_analytics.stats import (
    account_volume_share,
    add_zscores,
    daily_volume,
    flag_outlier_days,
    price_move_stats,
)


@pytest.fixture(scope="module")
def trades():
    _, t = generate_orders_trades(WarehouseConfig(seed=42, days=10))
    return t


def test_daily_volume_sums_match(trades):
    daily = daily_volume(trades)
    assert daily["volume"].sum() == trades["quantity"].sum()
    assert set(daily.columns) == {"instrument", "trade_date", "volume", "trades"}
    assert len(daily) == 10 * 6  # 10 days x 6 instruments


def test_zscores_finite(trades):
    scored = add_zscores(daily_volume(trades))
    assert np.isfinite(scored["volume_z"]).all()
    assert scored["volume_z"].abs().max() < 10


def test_outlier_flag_subset(trades):
    daily = daily_volume(trades)
    outliers = flag_outlier_days(daily, threshold=2.0)
    assert len(outliers) <= len(daily)
    assert (outliers["volume_z"].abs() >= 2.0).all()


def test_account_shares_sum_to_one(trades):
    shares = account_volume_share(trades)
    totals = shares.groupby(["instrument", "trade_date"])["share"].sum()
    assert np.allclose(totals.values, 1.0)


def test_price_move_stats_returns(trades):
    stats = price_move_stats(trades)
    assert "ret" in stats.columns and "ret_z" in stats.columns
    assert stats["ret"].dropna().abs().max() < 0.05
