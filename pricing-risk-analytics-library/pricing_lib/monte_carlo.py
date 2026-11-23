"""Monte Carlo pricers for European and arithmetic Asian options.

Geometric Brownian motion under the risk-neutral measure, with antithetic
variates. Every run is seeded, so results are reproducible. Pure standard
library (random.gauss).
"""

import math
import random


def _gbm_terminal(S: float, r: float, sigma: float, T: float, z: float) -> float:
    return S * math.exp((r - 0.5 * sigma * sigma) * T + sigma * math.sqrt(T) * z)


def european_mc(S: float, K: float, T: float, r: float, sigma: float,
                option: str = "call", n_paths: int = 20000,
                seed: int = 7, antithetic: bool = True) -> dict:
    """Monte Carlo price of a European option with standard error and 95% CI."""
    if S <= 0 or K <= 0 or T <= 0 or sigma < 0:
        raise ValueError("S, K, T must be positive; sigma non-negative")
    if option not in ("call", "put"):
        raise ValueError("option must be 'call' or 'put'")
    if n_paths < 100:
        raise ValueError("need at least 100 paths")
    rng = random.Random(seed)
    disc = math.exp(-r * T)
    payoffs = []
    step = 2 if antithetic else 1
    for _ in range(0, n_paths, step):
        z = rng.gauss(0.0, 1.0)
        for zz in ((z, -z) if antithetic else (z,)):
            s_t = _gbm_terminal(S, r, sigma, T, zz)
            payoff = max(s_t - K, 0.0) if option == "call" else max(K - s_t, 0.0)
            payoffs.append(disc * payoff)
    n = len(payoffs)
    mean = sum(payoffs) / n
    var = sum((p - mean) ** 2 for p in payoffs) / (n - 1)
    stderr = math.sqrt(var / n)
    return {"price": mean, "stderr": stderr, "n_paths": n,
            "ci_low": mean - 1.96 * stderr, "ci_high": mean + 1.96 * stderr}


def asian_mc(S: float, K: float, T: float, r: float, sigma: float,
             option: str = "call", n_paths: int = 20000, n_fixings: int = 12,
             seed: int = 7) -> dict:
    """Monte Carlo price of an arithmetic-average Asian option.

    The average is taken over ``n_fixings`` equally spaced dates including
    expiry. Antithetic variates are applied per path.
    """
    if S <= 0 or K <= 0 or T <= 0 or sigma < 0:
        raise ValueError("S, K, T must be positive; sigma non-negative")
    if option not in ("call", "put"):
        raise ValueError("option must be 'call' or 'put'")
    if n_paths < 100 or n_fixings < 1:
        raise ValueError("need at least 100 paths and 1 fixing")
    rng = random.Random(seed)
    disc = math.exp(-r * T)
    dt = T / n_fixings
    drift = (r - 0.5 * sigma * sigma) * dt
    vol = sigma * math.sqrt(dt)
    payoffs = []
    for _ in range(0, n_paths, 2):
        for sign in (1.0, -1.0):
            s = S
            total = 0.0
            for _ in range(n_fixings):
                s *= math.exp(drift + vol * sign * rng.gauss(0.0, 1.0))
                total += s
            avg = total / n_fixings
            payoff = max(avg - K, 0.0) if option == "call" else max(K - avg, 0.0)
            payoffs.append(disc * payoff)
    n = len(payoffs)
    mean = sum(payoffs) / n
    var = sum((p - mean) ** 2 for p in payoffs) / (n - 1)
    stderr = math.sqrt(var / n)
    return {"price": mean, "stderr": stderr, "n_paths": n,
            "ci_low": mean - 1.96 * stderr, "ci_high": mean + 1.96 * stderr}
