"""Unit tests for the Black-Scholes equity model."""

import math

import pytest

from model_validation_suite.models.equity import black_scholes, black_scholes_delta

S, R, VOL, T = 100.0, 0.05, 0.20, 1.0


def test_black_scholes_known_value():
    # Textbook value: S=K=100, r=5%, sigma=20%, T=1 -> call ~= 10.4506.
    call = black_scholes(S, 100.0, R, VOL, T, is_call=True)
    assert call == pytest.approx(10.4506, abs=1e-3)


@pytest.mark.parametrize("strike", [80.0, 90.0, 100.0, 110.0, 120.0])
def test_put_call_parity(strike):
    call = black_scholes(S, strike, R, VOL, T, is_call=True)
    put = black_scholes(S, strike, R, VOL, T, is_call=False)
    assert call - put == pytest.approx(S - strike * math.exp(-R * T), abs=1e-10)


def test_call_bounds():
    for k in (80.0, 100.0, 120.0):
        call = black_scholes(S, k, R, VOL, T, is_call=True)
        assert max(S - k * math.exp(-R * T), 0.0) <= call <= S


def test_put_bounds():
    for k in (80.0, 100.0, 120.0):
        put = black_scholes(S, k, R, VOL, T, is_call=False)
        assert max(k * math.exp(-R * T) - S, 0.0) <= put <= k * math.exp(-R * T)


def test_call_decreases_in_strike_and_increases_in_spot():
    strikes = [80.0, 90.0, 100.0, 110.0, 120.0]
    prices = [black_scholes(S, k, R, VOL, T, is_call=True) for k in strikes]
    assert all(b < a for a, b in zip(prices, prices[1:]))
    assert black_scholes(S * 1.05, 100.0, R, VOL, T, is_call=True) > prices[2]


def test_delta_bounds():
    for k in (80.0, 100.0, 120.0):
        assert 0.0 <= black_scholes_delta(S, k, R, VOL, T, is_call=True) <= 1.0
        assert -1.0 <= black_scholes_delta(S, k, R, VOL, T, is_call=False) <= 0.0


def test_atm_call_delta_near_half():
    delta = black_scholes_delta(S, 100.0, R, VOL, T, is_call=True)
    assert 0.5 < delta < 0.7
