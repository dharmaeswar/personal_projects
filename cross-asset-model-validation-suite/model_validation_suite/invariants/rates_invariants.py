"""Interest-rate invariants.

Context keys: ``curve`` (DiscountCurve), ``par_yields``, ``par_maturities``,
``vasicek`` (dict with a/theta/sigma/r0), ``tolerances`` (dict).
"""

from __future__ import annotations

import numpy as np

from ..models.rates import bootstrap_discount_factors, par_bond_price, vasicek_bond_price
from .framework import Outcome, invariant


def _sample_times(curve, extra=(0.25, 0.75, 1.5, 4.0, 6.0, 8.0, 9.0, 12.0, 15.0)):
    times = sorted(set([float(t) for t in curve.maturities] + [float(t) for t in extra]))
    return [t for t in times if t > 0]


@invariant("rates", "discount_factors_in_unit_interval",
           "All discount factors lie in (0, 1].")
def df_in_unit_interval(ctx: dict) -> Outcome:
    curve = ctx["curve"]
    dfs = [curve.discount(t) for t in _sample_times(curve)]
    worst = max(dfs)
    ok = all(0.0 < df <= 1.0 + 1e-15 for df in dfs)
    return Outcome(ok, worst, 1.0,
                   f"max DF={worst:.6f} over {len(dfs)} sampled maturities")


@invariant("rates", "discount_factors_monotonic_decreasing",
           "Discount factors strictly decrease with maturity.")
def df_monotonic(ctx: dict) -> Outcome:
    curve = ctx["curve"]
    times = _sample_times(curve)
    dfs = [curve.discount(t) for t in times]
    increases = [dfs[i + 1] - dfs[i] for i in range(len(dfs) - 1)]
    worst = max(increases) if increases else 0.0
    return Outcome(worst <= 0.0, worst, 0.0,
                   f"largest DF increase between adjacent maturities: {worst:.3e}")


@invariant("rates", "par_bond_repricing",
           "Bootstrapped curve reprices every par bond to par (1.0).")
def par_repricing(ctx: dict) -> Outcome:
    tol = ctx["tolerances"].get("parity", 1e-9)
    dfs = bootstrap_discount_factors(ctx["par_yields"], ctx["par_maturities"])
    errors = []
    for n, y in enumerate(ctx["par_yields"]):
        price = par_bond_price(y, dfs[: n + 1])
        errors.append(abs(price - 1.0))
    worst = max(errors) if errors else 0.0
    return Outcome(worst <= tol, worst, tol,
                   f"max |repriced - par| over {len(errors)} par bonds: {worst:.3e}")


@invariant("rates", "zero_bond_price_bounds",
           "Zero-coupon bond prices are positive and do not exceed face.")
def zcb_bounds(ctx: dict) -> Outcome:
    curve = ctx["curve"]
    face = 100.0
    prices = [curve.zero_coupon_bond_price(t, face) for t in _sample_times(curve)]
    worst = max(prices) / face
    ok = all(0.0 < p <= face + 1e-12 for p in prices)
    return Outcome(ok, worst, 1.0,
                   f"max price/face={worst:.6f} over {len(prices)} maturities")


@invariant("rates", "vasicek_short_end_limit",
           "Vasicek bond price tends to face value as maturity tends to zero.")
def vasicek_short_end(ctx: dict) -> Outcome:
    v = ctx["vasicek"]
    tol = ctx["tolerances"].get("short_end", 1e-3)
    price = vasicek_bond_price(v["r0"], 1e-4, v["a"], v["theta"], v["sigma"], face=100.0)
    err = abs(price - 100.0)
    return Outcome(err <= tol, err, tol,
                   f"|P(tau=1e-4) - face| = {err:.3e}")


@invariant("rates", "vasicek_price_decreases_in_short_rate",
           "Vasicek bond price strictly decreases as the short rate rises.")
def vasicek_monotonic(ctx: dict) -> Outcome:
    v = ctx["vasicek"]
    taus = (0.5, 1.0, 2.0, 5.0, 10.0)
    worst = -np.inf
    for tau in taus:
        p_low = vasicek_bond_price(v["r0"], tau, v["a"], v["theta"], v["sigma"])
        p_high = vasicek_bond_price(v["r0"] + 0.01, tau, v["a"], v["theta"], v["sigma"])
        worst = max(worst, p_high - p_low)
    return Outcome(worst < 0.0, float(worst), 0.0,
                   f"largest P(r0+1%) - P(r0) over {len(taus)} tenors: {worst:.3e}")
