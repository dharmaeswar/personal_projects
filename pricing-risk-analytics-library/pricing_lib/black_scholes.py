"""Black-Scholes pricing and Greeks for European options.

Pure standard library. The normal CDF uses math.erf; implied volatility
is found by bisection on the pricing function.
"""

import math


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def bs_price(S: float, K: float, T: float, r: float, sigma: float,
             option: str = "call") -> float:
    """Black-Scholes price of a European call or put.

    S: spot, K: strike, T: time to expiry in years, r: risk-free rate,
    sigma: volatility. T == 0 returns intrinsic value.
    """
    if S <= 0 or K <= 0 or T < 0 or sigma < 0:
        raise ValueError("S, K must be positive; T, sigma non-negative")
    if option not in ("call", "put"):
        raise ValueError("option must be 'call' or 'put'")
    if T == 0:
        return max(S - K, 0.0) if option == "call" else max(K - S, 0.0)
    if sigma == 0:
        forward = S * math.exp(r * T)
        payoff = max(forward - K, 0.0) if option == "call" else max(K - forward, 0.0)
        return math.exp(-r * T) * payoff
    d1 = (math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    if option == "call":
        return S * _norm_cdf(d1) - K * math.exp(-r * T) * _norm_cdf(d2)
    return K * math.exp(-r * T) * _norm_cdf(-d2) - S * _norm_cdf(-d1)


def bs_greeks(S: float, K: float, T: float, r: float, sigma: float,
              option: str = "call") -> dict:
    """Delta, gamma, vega, theta (per year) and rho for a European option."""
    if T == 0 or sigma == 0:
        raise ValueError("Greeks need T > 0 and sigma > 0")
    if option not in ("call", "put"):
        raise ValueError("option must be 'call' or 'put'")
    d1 = (math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    pdf = _norm_pdf(d1)
    sqrt_t = math.sqrt(T)
    disc = math.exp(-r * T)
    if option == "call":
        delta = _norm_cdf(d1)
        theta = (-(S * pdf * sigma) / (2 * sqrt_t)
                 - r * K * disc * _norm_cdf(d2))
        rho = K * T * disc * _norm_cdf(d2)
    else:
        delta = _norm_cdf(d1) - 1.0
        theta = (-(S * pdf * sigma) / (2 * sqrt_t)
                 + r * K * disc * _norm_cdf(-d2))
        rho = -K * T * disc * _norm_cdf(-d2)
    gamma = pdf / (S * sigma * sqrt_t)
    vega = S * pdf * sqrt_t
    return {"delta": delta, "gamma": gamma, "vega": vega,
            "theta": theta, "rho": rho}


def implied_vol(price: float, S: float, K: float, T: float, r: float,
                option: str = "call", tol: float = 1e-6) -> float:
    """Implied volatility by bisection; raises if the price is not attainable."""
    intrinsic = max(S - K, 0.0) if option == "call" else max(K - S, 0.0)
    if price < intrinsic - 1e-12:
        raise ValueError("price is below intrinsic value")
    lo, hi = 1e-6, 5.0
    if bs_price(S, K, T, r, hi, option) < price:
        raise ValueError("price is above the maximum attainable value")
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if bs_price(S, K, T, r, mid, option) < price:
            lo = mid
        else:
            hi = mid
        if hi - lo < tol:
            return 0.5 * (lo + hi)
    return 0.5 * (lo + hi)
