"""Closed-form pricing: normal CDF, Black-Scholes, analytic forward EE."""

import numpy as np
import pytest

from xva_benchmark.pricing import (analytic_forward_expected_exposure,
                                   black_scholes_call, black_scholes_put,
                                   norm_cdf)


def test_norm_cdf_known_values():
    assert norm_cdf(0.0) == pytest.approx(0.5, abs=1e-7)
    assert norm_cdf(1.96) == pytest.approx(0.9750021, abs=1e-6)
    assert norm_cdf(-1.96) == pytest.approx(1.0 - 0.9750021, abs=1e-6)


def test_black_scholes_at_expiry_is_intrinsic():
    assert black_scholes_call(120.0, 100.0, 0.0, 0.03, 0.20) == pytest.approx(20.0)
    assert black_scholes_call(80.0, 100.0, 0.0, 0.03, 0.20) == pytest.approx(0.0)
    assert black_scholes_put(80.0, 100.0, 0.0, 0.03, 0.20) == pytest.approx(20.0)


def test_put_call_parity():
    spot, strike, tau, rate, vol = 100.0, 95.0, 2.0, 0.03, 0.25
    call = black_scholes_call(spot, strike, tau, rate, vol)
    put = black_scholes_put(spot, strike, tau, rate, vol)
    forward_value = spot - strike * np.exp(-rate * tau)
    assert call - put == pytest.approx(forward_value, rel=1e-6)


def test_call_price_increases_with_volatility():
    low = black_scholes_call(100.0, 100.0, 3.0, 0.03, 0.10)
    high = black_scholes_call(100.0, 100.0, 3.0, 0.03, 0.40)
    assert high > low > 0.0


def test_analytic_forward_ee_at_time_zero():
    # At t=0 the exposure is the deterministic positive part of the forward.
    ee0 = analytic_forward_expected_exposure(100.0, 100.0, 5.0, 0.0, 0.03, 0.20)
    assert ee0 == pytest.approx(100.0 - 100.0 * np.exp(-0.15), rel=1e-9)
    # A deep out-of-the-money forward has zero exposure at t=0.
    assert analytic_forward_expected_exposure(100.0, 200.0, 5.0, 0.0, 0.03, 0.20) == 0.0
