"""Closed-form pricing helpers (numpy only).

The standard normal CDF uses the Abramowitz & Stegun (26.2.17) rational
approximation, whose absolute error is below 7.5e-8 -- more than sufficient
for a 1.2% benchmark tolerance band, and it avoids a scipy dependency.
"""

from __future__ import annotations

import numpy as np

# Abramowitz & Stegun 26.2.17 coefficients.
_AS_P = 0.2316419
_AS_B = (0.319381530, -0.356563782, 1.781477937, -1.821255978, 1.330274429)


def norm_cdf(x):
    """Standard normal CDF, elementwise over scalars or numpy arrays."""
    x = np.asarray(x, dtype=float)
    sign = np.where(x < 0.0, -1.0, 1.0)
    ax = np.abs(x)
    t = 1.0 / (1.0 + _AS_P * ax)
    poly = t * (_AS_B[0] + t * (_AS_B[1] + t * (_AS_B[2] + t * (_AS_B[3] + t * _AS_B[4]))))
    pdf = np.exp(-0.5 * ax * ax) / np.sqrt(2.0 * np.pi)
    cdf_pos = 1.0 - pdf * poly
    result = np.where(x < 0.0, 1.0 - cdf_pos, cdf_pos)
    return float(result) if result.ndim == 0 else result


def _d1_d2(spot, strike, tau, rate, volatility):
    vol_sqrt_tau = volatility * np.sqrt(tau)
    d1 = (np.log(spot / strike) + (rate + 0.5 * volatility ** 2) * tau) / vol_sqrt_tau
    return d1, d1 - vol_sqrt_tau


def black_scholes_call(spot, strike, tau, rate, volatility):
    """European call price; at/past expiry returns intrinsic value."""
    spot = np.asarray(spot, dtype=float)
    tau = np.asarray(tau, dtype=float)
    intrinsic = np.maximum(spot - strike, 0.0)
    safe_tau = np.where(tau > 0.0, tau, 1.0)  # placeholder where expired
    d1, d2 = _d1_d2(spot, strike, safe_tau, rate, volatility)
    price = spot * norm_cdf(d1) - strike * np.exp(-rate * safe_tau) * norm_cdf(d2)
    result = np.where(tau > 0.0, price, intrinsic)
    return float(result) if np.ndim(result) == 0 else result


def black_scholes_put(spot, strike, tau, rate, volatility):
    """European put price; at/past expiry returns intrinsic value."""
    spot = np.asarray(spot, dtype=float)
    tau = np.asarray(tau, dtype=float)
    intrinsic = np.maximum(strike - spot, 0.0)
    safe_tau = np.where(tau > 0.0, tau, 1.0)
    d1, d2 = _d1_d2(spot, strike, safe_tau, rate, volatility)
    price = strike * np.exp(-rate * safe_tau) * norm_cdf(-d2) - spot * norm_cdf(-d1)
    result = np.where(tau > 0.0, price, intrinsic)
    return float(result) if np.ndim(result) == 0 else result


def analytic_forward_expected_exposure(spot, strike, maturity, t, rate, volatility):
    """Discounted analytic EE of a long forward under GBM (risk-neutral drift).

    V_t = S_t - K * exp(-r (T - t)), and S_t is lognormal, so
    E[max(V_t, 0)] has the Black-style closed form used below. The result is
    discounted back to t=0, matching the simulated EE convention.
    """
    if t <= 0.0:
        return max(spot - strike * np.exp(-rate * maturity), 0.0)
    threshold = strike * np.exp(-rate * (maturity - t))
    vol_sqrt_t = volatility * np.sqrt(t)
    d1 = (np.log(spot / threshold) + (rate + 0.5 * volatility ** 2) * t) / vol_sqrt_t
    d2 = d1 - vol_sqrt_t
    undiscounted = spot * np.exp(rate * t) * norm_cdf(d1) - threshold * norm_cdf(d2)
    return float(np.exp(-rate * t) * undiscounted)
