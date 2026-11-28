import math

from options.pricing import (call_price, put_price, greeks, implied_vol,
                             norm_cdf)


def test_call_put_parity():
    spot, strike, t, rate, vol = 100.0, 100.0, 0.25, 0.05, 0.25
    lhs = call_price(spot, strike, t, rate, vol) - put_price(spot, strike, t, rate, vol)
    rhs = spot - strike * math.exp(-rate * t)
    assert abs(lhs - rhs) < 1e-9


def test_call_price_known_value():
    # Textbook case: S=100, K=100, T=1, r=5%, sigma=20% -> call ~10.45
    assert abs(call_price(100.0, 100.0, 1.0, 0.05, 0.20) - 10.4506) < 0.01
    assert abs(put_price(100.0, 100.0, 1.0, 0.05, 0.20) - 5.5735) < 0.01


def test_deep_itm_call_near_intrinsic():
    price = call_price(150.0, 100.0, 0.25, 0.05, 0.20)
    assert abs(price - (50.0 + 100.0 * (1 - math.exp(-0.05 * 0.25)))) < 0.5


def test_greeks_call_delta_range_and_gamma_positive():
    g = greeks(100.0, 100.0, 0.25, 0.05, 0.25, "call")
    assert 0.0 < g["delta"] < 1.0
    assert g["gamma"] > 0
    assert g["vega"] > 0
    assert g["theta"] < 0  # long call loses value with time


def test_greeks_put_delta_negative():
    g = greeks(100.0, 100.0, 0.25, 0.05, 0.25, "put")
    assert -1.0 < g["delta"] < 0.0
    assert g["gamma"] > 0
    assert g["vega"] > 0


def test_call_plus_put_delta_is_one():
    gc = greeks(100.0, 105.0, 0.5, 0.05, 0.30, "call")
    gp = greeks(100.0, 105.0, 0.5, 0.05, 0.30, "put")
    assert abs((gc["delta"] - gp["delta"]) - 1.0) < 1e-9


def test_implied_vol_round_trip():
    vol = 0.30
    price = call_price(100.0, 110.0, 0.5, 0.05, vol)
    assert abs(implied_vol(price, 100.0, 110.0, 0.5, 0.05, "call") - vol) < 1e-4
    price = put_price(95.0, 100.0, 0.25, 0.05, vol)
    assert abs(implied_vol(price, 95.0, 100.0, 0.25, 0.05, "put") - vol) < 1e-4


def test_implied_vol_none_below_intrinsic():
    assert implied_vol(1.0, 100.0, 90.0, 0.25, 0.05, "call") is None


def test_invalid_inputs_raise():
    import pytest
    with pytest.raises(ValueError):
        call_price(100.0, 100.0, 0.0, 0.05, 0.25)
    with pytest.raises(ValueError):
        call_price(100.0, 100.0, 0.25, 0.05, -0.1)
    with pytest.raises(ValueError):
        greeks(100.0, 100.0, 0.25, 0.05, 0.25, "straddle")
