"""Black-Scholes pricing and implied-vol solver tests."""

import math

import pytest

from vol_surface_checker.black_scholes import bs_price, implied_vol, total_variance


def test_call_price_known_value():
    # S = K = 100, T = 1, r = 0, sigma = 0.2 -> textbook value 7.9656.
    price = bs_price(100.0, 100.0, 1.0, 0.0, 0.2, "call")
    assert price == pytest.approx(7.9656, abs=1e-3)


def test_put_price_known_value():
    # With S = K and r = 0, put-call parity makes the put equal to the call.
    put = bs_price(100.0, 100.0, 1.0, 0.0, 0.2, "put")
    assert put == pytest.approx(7.9656, abs=1e-3)


def test_put_call_parity():
    spot, strike, maturity, rate, vol = 100.0, 95.0, 0.5, 0.05, 0.3
    call = bs_price(spot, strike, maturity, rate, vol, "call")
    put = bs_price(spot, strike, maturity, rate, vol, "put")
    assert call - put == pytest.approx(spot - strike * math.exp(-rate * maturity))


@pytest.mark.parametrize("vol", [0.1, 0.2, 0.35, 0.6])
@pytest.mark.parametrize("strike", [80.0, 100.0, 120.0])
def test_implied_vol_round_trip_call(vol, strike):
    price = bs_price(100.0, strike, 0.75, 0.03, vol, "call")
    solved = implied_vol(price, 100.0, strike, 0.75, 0.03, "call")
    assert solved == pytest.approx(vol, abs=1e-7)


def test_implied_vol_round_trip_put():
    price = bs_price(100.0, 110.0, 0.25, 0.02, 0.28, "put")
    solved = implied_vol(price, 100.0, 110.0, 0.25, 0.02, "put")
    assert solved == pytest.approx(0.28, abs=1e-7)


def test_implied_vol_rejects_price_below_intrinsic():
    # A call priced below discounted intrinsic value has no implied vol.
    with pytest.raises(ValueError):
        implied_vol(1.0, 100.0, 80.0, 1.0, 0.03, "call")


def test_implied_vol_rejects_price_above_upper_bound():
    with pytest.raises(ValueError):
        implied_vol(150.0, 100.0, 100.0, 1.0, 0.03, "call")


def test_bs_price_rejects_bad_inputs():
    with pytest.raises(ValueError):
        bs_price(100.0, 100.0, 0.0, 0.03, 0.2)
    with pytest.raises(ValueError):
        bs_price(100.0, 100.0, 1.0, 0.03, -0.2)
    with pytest.raises(ValueError):
        bs_price(100.0, 100.0, 1.0, 0.03, 0.2, "straddle")


def test_total_variance():
    assert total_variance(0.2, 0.5) == pytest.approx(0.02)
    assert total_variance(0.3, 2.0) == pytest.approx(0.18)
