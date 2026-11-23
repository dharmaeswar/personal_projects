"""Black-76 pricing for options on commodity futures.

Commodity options settle against futures, so the Black-76 model (the
futures-option version of Black-Scholes) is the market standard: the
futures price is driftless under the risk-neutral measure, and the
option value is the discounted expected payoff. Only the standard
library is used — ``math.erf`` supplies the normal CDF, so there is
no SciPy dependency.

Greeks: delta, gamma and vega are closed-form. Theta is a finite
difference on time to expiry (documented as such), because the
closed-form time derivative of Black-76 is easy to get wrong and the
finite difference is the check the validation module runs anyway.
"""

from __future__ import annotations

import math


def norm_cdf(x: float) -> float:
    """Standard normal CDF via erf."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def norm_pdf(x: float) -> float:
    """Standard normal PDF."""
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def _d1_d2(F: float, K: float, T: float, sigma: float) -> tuple[float, float]:
    if T <= 0 or sigma <= 0:
        raise ValueError("T and sigma must be positive for Black-76")
    d1 = (math.log(F / K) + 0.5 * sigma * sigma * T) / (sigma * math.sqrt(T))
    return d1, d1 - sigma * math.sqrt(T)


def black76_call(F: float, K: float, T: float, r: float, sigma: float) -> float:
    """European call on a futures contract (Black-76)."""
    d1, d2 = _d1_d2(F, K, T, sigma)
    return math.exp(-r * T) * (F * norm_cdf(d1) - K * norm_cdf(d2))


def black76_put(F: float, K: float, T: float, r: float, sigma: float) -> float:
    """European put on a futures contract (Black-76)."""
    d1, d2 = _d1_d2(F, K, T, sigma)
    return math.exp(-r * T) * (K * norm_cdf(-d2) - F * norm_cdf(-d1))


def black76_greeks(
    F: float, K: float, T: float, r: float, sigma: float, kind: str = "call"
) -> dict[str, float]:
    """Delta, gamma, vega (closed-form) and theta (finite difference).

    Delta is per unit move in the futures price. Gamma is per unit
    move squared. Vega is per 1.0 (100%) move in volatility — divide
    by 100 for the usual per-point quote. Theta is per calendar year,
    computed by bumping T down by one day; it is negative for a long
    option, as time decay requires.
    """
    if kind not in ("call", "put"):
        raise ValueError("kind must be 'call' or 'put'")
    price = black76_call if kind == "call" else black76_put
    d1, _ = _d1_d2(F, K, T, sigma)
    disc = math.exp(-r * T)
    if kind == "call":
        delta = disc * norm_cdf(d1)
    else:
        delta = disc * (norm_cdf(d1) - 1.0)
    gamma = disc * norm_pdf(d1) / (F * sigma * math.sqrt(T))
    vega = disc * F * norm_pdf(d1) * math.sqrt(T)
    # Theta by finite difference: one-day bump, per-year figure.
    bump = 1.0 / 365.0
    t_down = max(T - bump, 1e-6)
    theta = (price(F, K, t_down, r, sigma) - price(F, K, T, r, sigma)) / bump
    return {"delta": delta, "gamma": gamma, "vega": vega, "theta": theta}


def implied_vol(
    market_price: float,
    F: float,
    K: float,
    T: float,
    r: float,
    kind: str = "call",
    tol: float = 1e-8,
) -> float:
    """Implied volatility by bisection on the Black-76 price."""
    price = black76_call if kind == "call" else black76_put
    lo, hi = 1e-6, 5.0
    if not (price(F, K, T, r, lo) <= market_price <= price(F, K, T, r, hi)):
        raise ValueError("market price outside the attainable range")
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if price(F, K, T, r, mid) < market_price:
            lo = mid
        else:
            hi = mid
        if hi - lo < tol:
            break
    return 0.5 * (lo + hi)


def monte_carlo_price(
    F: float,
    K: float,
    T: float,
    r: float,
    sigma: float,
    kind: str = "call",
    n_paths: int = 200_000,
    seed: int = 42,
) -> tuple[float, float]:
    """Monte Carlo price of the same option (driftless futures measure).

    Returns (price, standard error). The futures price is a martingale
    under the pricing measure, so F_T = F * exp(-0.5 sigma^2 T +
    sigma sqrt(T) Z). The validation module checks this converges to
    Black-76.
    """
    import numpy as np

    rng = np.random.default_rng(seed)
    z = rng.standard_normal(n_paths)
    fwd = F * np.exp(-0.5 * sigma * sigma * T + sigma * math.sqrt(T) * z)
    if kind == "call":
        payoff = np.maximum(fwd - K, 0.0)
    elif kind == "put":
        payoff = np.maximum(K - fwd, 0.0)
    else:
        raise ValueError("kind must be 'call' or 'put'")
    disc_payoff = math.exp(-r * T) * payoff
    return float(disc_payoff.mean()), float(disc_payoff.std(ddof=1) / math.sqrt(n_paths))
