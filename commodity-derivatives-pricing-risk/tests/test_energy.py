"""Tests for the energy derivatives module (spark spreads, power curves)."""

from __future__ import annotations

import math

import pytest

from commodities.energy import (
    check_spark_spread_call_bounds,
    seasonal_power_forward_curve,
    spark_spread,
    spark_spread_breakeven_gas,
    spark_spread_call_mc,
)

P, G, H = 45.0, 3.20, 7.0  # power $/MWh, gas $/MMBtu, heat rate MMBtu/MWh


def test_spark_spread_arithmetic():
    assert spark_spread(P, G, H) == pytest.approx(45.0 - 7.0 * 3.20)
    # A cheaper gas price widens the margin; a higher heat rate narrows it.
    assert spark_spread(P, 2.0, H) > spark_spread(P, G, H)
    assert spark_spread(P, G, 9.0) < spark_spread(P, G, H)


def test_spark_spread_can_go_negative():
    # Expensive gas can wipe out the generation margin entirely.
    assert spark_spread(30.0, 6.0, H) < 0


def test_spark_spread_rejects_non_positive_inputs():
    with pytest.raises(ValueError):
        spark_spread(0.0, G, H)
    with pytest.raises(ValueError):
        spark_spread(P, -1.0, H)
    with pytest.raises(ValueError):
        spark_spread(P, G, 0.0)


def test_breakeven_gas_solves_spread_equation():
    be = spark_spread_breakeven_gas(P, H)
    assert spark_spread(P, be, H) == pytest.approx(0.0, abs=1e-9)
    assert be == pytest.approx(P / H)
    # A strike of 5 needs gas 5/H cheaper to stay in the money.
    assert spark_spread_breakeven_gas(P, H, strike=5.0) == pytest.approx((P - 5.0) / H)
    with pytest.raises(ValueError):
        spark_spread_breakeven_gas(10.0, H, strike=20.0)


def test_seasonal_curve_peaks_in_july_and_troughs_in_january():
    curve = seasonal_power_forward_curve(40.0)
    assert len(curve) == 12
    assert list(curve["month"]) == list(range(1, 13))
    july = float(curve.loc[curve["month"] == 7, "forward_price"].iloc[0])
    january = float(curve.loc[curve["month"] == 1, "forward_price"].iloc[0])
    assert july == pytest.approx(40.0 * 1.25)
    assert january == pytest.approx(40.0 * 0.75)
    assert july == float(curve["forward_price"].max())
    assert january == float(curve["forward_price"].min())
    # Seasonal factors average to 1 over a full year.
    assert float(curve["seasonal_factor"].mean()) == pytest.approx(1.0, abs=1e-3)


def test_seasonal_curve_rejects_bad_inputs():
    with pytest.raises(ValueError):
        seasonal_power_forward_curve(0.0)
    with pytest.raises(ValueError):
        seasonal_power_forward_curve(40.0, peak_month=13)
    with pytest.raises(ValueError):
        seasonal_power_forward_curve(40.0, amplitude=1.0)


def _mc(**over):
    kw = dict(power_forward=P, gas_forward=G, T=0.5, r=0.045)
    kw.update(over)
    return spark_spread_call_mc(**kw)


def test_spark_spread_call_above_intrinsic_and_below_power_leg():
    res = _mc(strike=5.0)
    check = check_spark_spread_call_bounds(res, P, 0.045, 0.5)
    assert check["passed"]
    assert res["value"] > res["discounted_intrinsic"]
    assert res["std_error"] > 0


def test_spark_spread_call_seed_reproducible():
    assert _mc(strike=5.0)["value"] == _mc(strike=5.0)["value"]


def test_spark_spread_call_falls_with_strike_and_rises_with_vol():
    low_k = _mc(strike=0.0)["value"]
    high_k = _mc(strike=10.0)["value"]
    assert low_k > high_k
    low_vol = _mc(strike=5.0, power_vol=0.2, gas_vol=0.2)["value"]
    high_vol = _mc(strike=5.0, power_vol=1.2, gas_vol=1.0)["value"]
    assert high_vol > low_vol


def test_spark_spread_call_near_zero_vol_equals_intrinsic():
    res = _mc(strike=5.0, power_vol=1e-6, gas_vol=1e-6)
    assert res["value"] == pytest.approx(res["discounted_intrinsic"], abs=0.05)


def test_spark_spread_call_correlation_moves_value():
    # Higher power-gas correlation narrows the spread distribution,
    # so an out-of-the-money spread call is worth less.
    low_corr = _mc(strike=25.0, correlation=-0.5)["value"]
    high_corr = _mc(strike=25.0, correlation=0.9)["value"]
    assert low_corr > high_corr


def test_spark_spread_call_rejects_bad_inputs():
    with pytest.raises(ValueError):
        _mc(correlation=1.5)
    with pytest.raises(ValueError):
        _mc(power_vol=-0.1)
    with pytest.raises(ValueError):
        _mc(T=0.0)
