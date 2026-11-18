"""Equity (Black-Scholes) invariants.

Context keys: ``spot``, ``rate``, ``vol``, ``tenor``, ``strikes``,
``tolerances``.
"""

from __future__ import annotations

import math

from ..models.equity import black_scholes, black_scholes_delta
from .framework import Outcome, invariant


@invariant("equity", "put_call_parity",
           "Black-Scholes put-call parity: C - P = S - K e^{-rT}.")
def put_call_parity(ctx: dict) -> Outcome:
    tol = ctx["tolerances"].get("parity", 1e-9)
    s, r, vol, t = ctx["spot"], ctx["rate"], ctx["vol"], ctx["tenor"]
    disc = math.exp(-r * t)
    worst = 0.0
    for k in ctx["strikes"]:
        call = black_scholes(s, k, r, vol, t, is_call=True)
        put = black_scholes(s, k, r, vol, t, is_call=False)
        worst = max(worst, abs((call - put) - (s - k * disc)))
    return Outcome(worst <= tol, worst, tol,
                   f"max parity error over {len(ctx['strikes'])} strikes: {worst:.3e}")


@invariant("equity", "call_no_arbitrage_bounds",
           "max(S - K e^{-rT}, 0) <= call <= S for every strike.")
def call_bounds(ctx: dict) -> Outcome:
    s, r, vol, t = ctx["spot"], ctx["rate"], ctx["vol"], ctx["tenor"]
    disc = math.exp(-r * t)
    worst = 0.0
    for k in ctx["strikes"]:
        call = black_scholes(s, k, r, vol, t, is_call=True)
        lower = max(s - k * disc, 0.0)
        worst = max(worst, lower - call, call - s)
    return Outcome(worst <= 0.0, worst, 0.0,
                   f"largest bound violation over {len(ctx['strikes'])} strikes: {worst:.3e}")


@invariant("equity", "put_no_arbitrage_bounds",
           "max(K e^{-rT} - S, 0) <= put <= K e^{-rT} for every strike.")
def put_bounds(ctx: dict) -> Outcome:
    s, r, vol, t = ctx["spot"], ctx["rate"], ctx["vol"], ctx["tenor"]
    disc = math.exp(-r * t)
    worst = 0.0
    for k in ctx["strikes"]:
        put = black_scholes(s, k, r, vol, t, is_call=False)
        lower = max(k * disc - s, 0.0)
        worst = max(worst, lower - put, put - k * disc)
    return Outcome(worst <= 0.0, worst, 0.0,
                   f"largest bound violation over {len(ctx['strikes'])} strikes: {worst:.3e}")


@invariant("equity", "call_monotonicity",
           "Calls decrease in strike and increase in spot.")
def call_monotonicity(ctx: dict) -> Outcome:
    s, r, vol, t = ctx["spot"], ctx["rate"], ctx["vol"], ctx["tenor"]
    strikes = sorted(ctx["strikes"])
    worst = 0.0
    prices = [black_scholes(s, k, r, vol, t, is_call=True) for k in strikes]
    for i in range(len(prices) - 1):
        worst = max(worst, prices[i + 1] - prices[i])  # must be <= 0 in strike
    bumped = black_scholes(s * 1.01, strikes[len(strikes) // 2], r, vol, t, is_call=True)
    base = prices[len(strikes) // 2]
    worst = max(worst, base - bumped)  # must be <= 0: price rises with spot
    return Outcome(worst <= 0.0, worst, 0.0,
                   f"largest monotonicity violation: {worst:.3e}")


@invariant("equity", "delta_bounds",
           "Call delta in [0, 1] and put delta in [-1, 0] for every strike.")
def delta_bounds(ctx: dict) -> Outcome:
    s, r, vol, t = ctx["spot"], ctx["rate"], ctx["vol"], ctx["tenor"]
    worst = 0.0
    for k in ctx["strikes"]:
        d_call = black_scholes_delta(s, k, r, vol, t, is_call=True)
        d_put = black_scholes_delta(s, k, r, vol, t, is_call=False)
        worst = max(worst, -d_call, d_call - 1.0, d_put, -1.0 - d_put)
    return Outcome(worst <= 0.0, worst, 0.0,
                   f"largest delta bound violation over {len(ctx['strikes'])} strikes: {worst:.3e}")
