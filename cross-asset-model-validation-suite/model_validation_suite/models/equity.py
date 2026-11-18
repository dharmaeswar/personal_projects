"""Equity model: Black-Scholes European option pricing (no dividends).

Rates are continuously compounded; times in years.
"""

from __future__ import annotations

import math


def norm_cdf(x: float) -> float:
    """Standard normal CDF via the error function (no scipy needed)."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def black_scholes(spot: float, strike: float, rate: float, vol: float,
                  tenor: float, is_call: bool = True) -> float:
    """Black-Scholes price of a European call or put.

        d1 = [ln(S/K) + (r + sigma^2/2) T] / (sigma sqrt(T)),  d2 = d1 - sigma sqrt(T)
        call = S N(d1) - K e^{-rT} N(d2)
        put  = K e^{-rT} N(-d2) - S N(-d1)
    """
    if tenor <= 0 or vol <= 0:
        disc = math.exp(-rate * max(tenor, 0.0))
        fwd_intrinsic = spot - strike * disc
        return max(fwd_intrinsic, 0.0) if is_call else max(-fwd_intrinsic, 0.0)
    sqrt_t = math.sqrt(tenor)
    d1 = (math.log(spot / strike) + (rate + 0.5 * vol * vol) * tenor) / (vol * sqrt_t)
    d2 = d1 - vol * sqrt_t
    disc = math.exp(-rate * tenor)
    if is_call:
        return spot * norm_cdf(d1) - strike * disc * norm_cdf(d2)
    return strike * disc * norm_cdf(-d2) - spot * norm_cdf(-d1)


def black_scholes_delta(spot: float, strike: float, rate: float, vol: float,
                        tenor: float, is_call: bool = True) -> float:
    """Black-Scholes delta: N(d1) for a call, N(d1) - 1 for a put."""
    if tenor <= 0 or vol <= 0:
        raise ValueError("delta requires positive tenor and vol")
    sqrt_t = math.sqrt(tenor)
    d1 = (math.log(spot / strike) + (rate + 0.5 * vol * vol) * tenor) / (vol * sqrt_t)
    return norm_cdf(d1) if is_call else norm_cdf(d1) - 1.0
