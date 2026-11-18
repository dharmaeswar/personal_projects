"""Black-Scholes pricing and implied-volatility solving.

Pure NumPy implementation used by every check in this package:

* :func:`bs_price` -- European call/put price from an implied volatility.
* :func:`implied_vol` -- recover the implied volatility from a market price
  (Newton iteration with a bisection fallback, so it stays robust for
  deep in/out-of-the-money quotes).
"""

from __future__ import annotations

import math

import numpy as np

_SQRT2 = math.sqrt(2.0)


def _norm_cdf(x: float) -> float:
    """Standard normal CDF via the error function."""
    return 0.5 * (1.0 + math.erf(x / _SQRT2))


def bs_price(
    spot: float,
    strike: float,
    maturity: float,
    rate: float,
    vol: float,
    option_type: str = "call",
) -> float:
    """Black-Scholes price of a European option.

    Parameters
    ----------
    spot, strike : float
        Spot and strike of the underlying.
    maturity : float
        Time to expiry in years (must be > 0).
    rate : float
        Continuously compounded risk-free rate (no dividends).
    vol : float
        Annualised volatility (must be > 0).
    option_type : str
        ``"call"`` or ``"put"``.
    """
    if maturity <= 0:
        raise ValueError("maturity must be positive")
    if vol <= 0:
        raise ValueError("vol must be positive")
    if spot <= 0 or strike <= 0:
        raise ValueError("spot and strike must be positive")

    d1 = (math.log(spot / strike) + (rate + 0.5 * vol * vol) * maturity) / (
        vol * math.sqrt(maturity)
    )
    d2 = d1 - vol * math.sqrt(maturity)
    discount = math.exp(-rate * maturity)

    if option_type == "call":
        return spot * _norm_cdf(d1) - strike * discount * _norm_cdf(d2)
    if option_type == "put":
        return strike * discount * _norm_cdf(-d2) - spot * _norm_cdf(-d1)
    raise ValueError(f"unknown option_type: {option_type!r}")


def bs_vega(spot: float, strike: float, maturity: float, rate: float, vol: float) -> float:
    """Black-Scholes vega (dPrice/dVol), same for calls and puts."""
    d1 = (math.log(spot / strike) + (rate + 0.5 * vol * vol) * maturity) / (
        vol * math.sqrt(maturity)
    )
    return spot * math.exp(-0.5 * d1 * d1) / math.sqrt(2.0 * math.pi) * math.sqrt(maturity)


def intrinsic_value(
    spot: float, strike: float, maturity: float, rate: float, option_type: str = "call"
) -> float:
    """Discounted intrinsic value -- the no-arbitrage floor for the price."""
    discount = math.exp(-rate * maturity)
    forward = spot / discount
    if option_type == "call":
        return discount * max(forward - strike, 0.0)
    return discount * max(strike - forward, 0.0)


def implied_vol(
    price: float,
    spot: float,
    strike: float,
    maturity: float,
    rate: float,
    option_type: str = "call",
    tol: float = 1e-10,
    max_iter: int = 100,
) -> float:
    """Solve for the implied volatility that reproduces ``price``.

    Newton iteration seeded from a Brenner-Subrahmanyam style guess, with a
    bisection fallback on [1e-6, 5.0] whenever Newton steps out of bounds or
    vega degenerates. Raises ``ValueError`` if the price is outside the
    no-arbitrage bounds for the contract.
    """
    if maturity <= 0:
        raise ValueError("maturity must be positive")
    discount = math.exp(-rate * maturity)
    upper = spot if option_type == "call" else strike * discount
    lower = intrinsic_value(spot, strike, maturity, rate, option_type)
    if price < lower - 1e-12 or price > upper + 1e-12:
        raise ValueError(
            f"price {price} outside no-arbitrage bounds [{lower}, {upper}]"
        )
    if abs(price - lower) <= 1e-12:
        return 0.0

    lo, hi = 1e-6, 5.0
    # Brenner-Subrahmanyam initial guess, clamped into the bracket.
    guess = math.sqrt(2.0 * math.pi / maturity) * price / spot
    vol = min(max(guess, lo + 1e-6), hi - 1e-6)

    for _ in range(max_iter):
        model = bs_price(spot, strike, maturity, rate, vol, option_type)
        diff = model - price
        if abs(diff) < tol:
            return vol
        if diff > 0:
            hi = vol
        else:
            lo = vol
        vega = bs_vega(spot, strike, maturity, rate, vol)
        if vega > 1e-12:
            candidate = vol - diff / vega
        else:
            candidate = float("nan")
        if not (lo < candidate < hi):
            candidate = 0.5 * (lo + hi)
        vol = candidate
    # Final bisection polish.
    for _ in range(200):
        vol = 0.5 * (lo + hi)
        model = bs_price(spot, strike, maturity, rate, vol, option_type)
        if abs(model - price) < tol:
            return vol
        if model > price:
            hi = vol
        else:
            lo = vol
    return vol


def total_variance(vol: float, maturity: float) -> float:
    """Total implied variance ``w = sigma^2 * T``."""
    return float(np.square(vol) * maturity)
