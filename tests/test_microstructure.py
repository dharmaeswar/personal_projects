import numpy as np
import pandas as pd
import pytest

from trade_reg_analytics.data import WarehouseConfig, generate_orders_trades
from trade_reg_analytics.microstructure import (
    daily_microstructure,
    flag_microstructure_days,
    microstructure_summary,
)


@pytest.fixture(scope="module")
def trades():
    _, t = generate_orders_trades(WarehouseConfig(seed=42, days=10))
    return t


def test_vwap_is_quantity_weighted():
    t = pd.DataFrame(
        {
            "trade_id": ["T1", "T2"],
            "instrument": ["ES", "ES"],
            "trade_date": ["2026-10-26", "2026-10-26"],
            "side": ["BUY", "SELL"],
            "quantity": [10, 30],
            "price": [100.0, 102.0],
        }
    )
    ms = daily_microstructure(t)
    assert len(ms) == 1
    assert ms.loc[0, "vwap"] == pytest.approx(101.5)
    assert ms.loc[0, "volume"] == 40
    assert ms.loc[0, "imbalance"] == pytest.approx(-0.5)


def test_one_row_per_instrument_day(trades):
    ms = daily_microstructure(trades)
    assert len(ms) == 10 * 6  # 10 days x 6 instruments
    assert set(ms.columns) >= {
        "instrument", "trade_date", "vwap", "imbalance",
        "mean_abs_dev_bps", "large_trade_share",
    }
    assert ms["imbalance"].abs().max() <= 1.0
    assert (ms["large_trade_share"] >= 0).all()
    assert (ms["large_trade_share"] <= 1).all()
    assert np.isfinite(ms["mean_abs_dev_bps"]).all()


def test_flags_are_a_subset_with_reasons(trades):
    ms = daily_microstructure(trades)
    flagged = flag_microstructure_days(ms)
    assert len(flagged) <= len(ms)
    if len(flagged):
        assert "reason" in flagged.columns
        assert flagged["reason"].str.len().gt(0).all()


def test_summary_counts(trades):
    ms = daily_microstructure(trades)
    s = microstructure_summary(ms)
    assert s["instrument_days"] == 60
    assert s["flagged_days"] == len(flag_microstructure_days(ms))
    assert s["median_mean_abs_dev_bps"] >= 0


def test_empty_input():
    empty = pd.DataFrame(columns=["instrument", "trade_date", "side", "quantity", "price"])
    assert daily_microstructure(empty).empty
    assert microstructure_summary(empty) == {"instrument_days": 0, "flagged_days": 0}
