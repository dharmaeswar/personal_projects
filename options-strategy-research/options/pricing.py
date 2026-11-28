"""Black-Scholes pricing, Greeks, and implied volatility.

Standard-library only. Used to price the synthetic option chains in
``options.data`` and to drive the strategy simulations in
``options.strategies`` and ``options.backtest``.
"""

import math

SQRT_2PI = math.sqrt(2.0 * math.pi)


def norm_cdf(x):
    """Standard normal CDF via the error function."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def norm_pdf(x):
    """Standard normal PDF."""
    return math.exp(-0.5 * x * x) / SQRT_2PI


def _d1_d2(spot, strike, time_to_expiry, rate, vol):
    """Black-Scholes d1 and d2. All inputs are plain floats; time in years."""
    if time_to_expiry <= 0 or vol <= 0:
        raise ValueError("time_to_expiry and vol must be positive")
    if spot <= 0 or strike <= 0:
        raise ValueError("spot and strike must be positive")
    sqrt_t = math.sqrt(time_to_expiry)
    d1 = (math.log(spot / strike) + (rate + 0.5 * vol * vol) * time_to_expiry) / (vol * sqrt_t)
    d2 = d1 - vol * sqrt_t
    return d1, d2


def call_price(spot, strike, time_to_expiry, rate, vol):
    """European call price under Black-Scholes."""
    d1, d2 = _d1_d2(spot, strike, time_to_expiry, rate, vol)
    return spot * norm_cdf(d1) - strike * math.exp(-rate * time_to_expiry) * norm_cdf(d2)


def put_price(spot, strike, time_to_expiry, rate, vol):
    """European put price under Black-Scholes."""
    d1, d2 = _d1_d2(spot, strike, time_to_expiry, rate, vol)
    return strike * math.exp(-rate * time_to_expiry) * norm_cdf(-d2) - spot * norm_cdf(-d1)


def greeks(spot, strike, time_to_expiry, rate, vol, kind="call"):
    """Delta, gamma, vega, theta (per year), and rho for one option.

    Returns a dict with keys delta, gamma, vega, theta, rho. Vega is the
    price change per 1.0 (100 vol points) of volatility; theta is per year
    (divide by 365 for a per-day figure).
    """
    if kind not in ("call", "put"):
        raise ValueError("kind must be 'call' or 'put'")
    d1, d2 = _d1_d2(spot, strike, time_to_expiry, rate, vol)
    sqrt_t = math.sqrt(time_to_expiry)
    disc = math.exp(-rate * time_to_expiry)
    gamma = norm_pdf(d1) / (spot * vol * sqrt_t)
    vega = spot * norm_pdf(d1) * sqrt_t
    if kind == "call":
        delta = norm_cdf(d1)
        theta = (-spot * norm_pdf(d1) * vol / (2.0 * sqrt_t)
                 - rate * strike * disc * norm_cdf(d2))
        rho = strike * time_to_expiry * disc * norm_cdf(d2)
    else:
        delta = norm_cdf(d1) - 1.0
        theta = (-spot * norm_pdf(d1) * vol / (2.0 * sqrt_t)
                 + rate * strike * disc * norm_cdf(-d2))
        rho = -strike * time_to_expiry * disc * norm_cdf(-d2)
    return {"delta": delta, "gamma": gamma, "vega": vega,
            "theta": theta, "rho": rho}


def implied_vol(price, spot, strike, time_to_expiry, rate, kind="call",
                low=1e-4, high=5.0, tol=1e-6, max_iter=200):
    """Implied volatility by bisection. Returns None if no root in range."""
    if kind == "call":
        pricer = call_price
    elif kind == "put":
        pricer = put_price
    else:
        raise ValueError("kind must be 'call' or 'put'")
    intrinsic = max(spot - strike, 0.0) if kind == "call" else max(strike - spot, 0.0)
    if price < intrinsic:
        return None  # arbitrage: price below intrinsic value
    if pricer(spot, strike, time_to_expiry, rate, low) > price:
        return None
    if pricer(spot, strike, time_to_expiry, rate, high) < price:
        return None
    for _ in range(max_iter):
        mid = 0.5 * (low + high)
        if pricer(spot, strike, time_to_expiry, rate, mid) < price:
            low = mid
        else:
            high = mid
        if high - low < tol:
            return 0.5 * (low + high)
    return 0.5 * (low + high)
