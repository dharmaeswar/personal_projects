"""Unit tests for the FX models."""

import math

import pytest

from model_validation_suite.models.fx import fx_forward, garman_kohlhagen

S, RD, RF, VOL, T = 1.10, 0.03, 0.015, 0.10, 1.0


def test_forward_matches_interest_rate_parity():
    expected = S * math.exp((RD - RF) * T)
    assert fx_forward(S, RD, RF, T) == pytest.approx(expected, rel=1e-12)


def test_forward_increases_with_domestic_rate():
    assert fx_forward(S, RD + 0.01, RF, T) > fx_forward(S, RD, RF, T)


def test_forward_decreases_with_foreign_rate():
    assert fx_forward(S, RD, RF + 0.01, T) < fx_forward(S, RD, RF, T)


@pytest.mark.parametrize("strike", [0.95, 1.05, 1.10, 1.15, 1.25])
def test_garman_kohlhagen_put_call_parity(strike):
    call = garman_kohlhagen(S, strike, RD, RF, VOL, T, is_call=True)
    put = garman_kohlhagen(S, strike, RD, RF, VOL, T, is_call=False)
    rhs = S * math.exp(-RF * T) - strike * math.exp(-RD * T)
    assert call - put == pytest.approx(rhs, abs=1e-10)


def test_garman_kohlhagen_atm_value_positive_and_below_spot():
    call = garman_kohlhagen(S, S, RD, RF, VOL, T, is_call=True)
    assert 0.0 < call < S
