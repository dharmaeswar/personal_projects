"""Validation checks for the pricing and risk analytics.

Three independent checks, the way a model-validation team would run
them: put-call parity (an arbitrage identity the model must satisfy
exactly), Monte Carlo convergence (the simulation must agree with the
closed form within its own standard error), and Greeks versus finite
differences (the closed-form sensitivities must match bumped prices).
"""

from __future__ import annotations

import math

from .pricing import (
    black76_call,
    black76_greeks,
    black76_put,
    monte_carlo_price,
)


def check_put_call_parity(
    F: float, K: float, T: float, r: float, sigma: float, tol: float = 1e-8
) -> dict:
    """C - P must equal e^(-rT) (F - K) for Black-76."""
    lhs = black76_call(F, K, T, r, sigma) - black76_put(F, K, T, r, sigma)
    rhs = math.exp(-r * T) * (F - K)
    diff = abs(lhs - rhs)
    return {
        "check": "put_call_parity",
        "passed": diff < tol,
        "difference": diff,
        "call_minus_put": lhs,
        "discounted_forward": rhs,
    }


def check_mc_convergence(
    F: float, K: float, T: float, r: float, sigma: float,
    kind: str = "call", n_paths: int = 200_000, seed: int = 42,
    z_tol: float = 3.0,
) -> dict:
    """Monte Carlo price must agree with Black-76 within z standard errors."""
    closed = black76_call(F, K, T, r, sigma) if kind == "call" else black76_put(F, K, T, r, sigma)
    mc, se = monte_carlo_price(F, K, T, r, sigma, kind, n_paths, seed)
    z = abs(mc - closed) / se if se > 0 else float("inf")
    return {
        "check": "mc_convergence",
        "passed": z < z_tol,
        "closed_form": closed,
        "monte_carlo": mc,
        "std_error": se,
        "z_score": z,
    }


def check_greeks_finite_difference(
    F: float, K: float, T: float, r: float, sigma: float,
    kind: str = "call", tol: float = 1e-3,
) -> dict:
    """Closed-form delta/gamma/vega must match bumped Black-76 prices."""
    price = black76_call if kind == "call" else black76_put
    greeks = black76_greeks(F, K, T, r, sigma, kind)
    dF = F * 1e-4
    fd_delta = (price(F + dF, K, T, r, sigma) - price(F - dF, K, T, r, sigma)) / (2 * dF)
    fd_gamma = (
        price(F + dF, K, T, r, sigma)
        - 2 * price(F, K, T, r, sigma)
        + price(F - dF, K, T, r, sigma)
    ) / (dF * dF)
    dvol = 1e-4
    fd_vega = (price(F, K, T, r, sigma + dvol) - price(F, K, T, r, sigma - dvol)) / (2 * dvol)
    diffs = {
        "delta": abs(greeks["delta"] - fd_delta),
        "gamma": abs(greeks["gamma"] - fd_gamma),
        "vega": abs(greeks["vega"] - fd_vega),
    }
    return {
        "check": "greeks_finite_difference",
        "passed": all(v < tol for v in diffs.values()),
        "closed_form": {k: round(v, 6) for k, v in greeks.items()},
        "finite_difference": {
            "delta": round(fd_delta, 6),
            "gamma": round(fd_gamma, 6),
            "vega": round(fd_vega, 6),
        },
        "differences": {k: round(v, 8) for k, v in diffs.items()},
    }
