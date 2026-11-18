"""Rare-event statistics: Poisson intervals and release comparisons.

Interventions are rare events, so a raw rate is not evidence on its
own. These helpers give an exact Poisson confidence interval for a
rate per 1,000 miles and a two-sample Poisson rate comparison, so a
release-over-release change can be judged as real improvement or
noise. Implemented with the standard library only (math.gamma based
chi-square quantiles via the Wilson-Hilferty approximation are avoided;
the exact interval uses the chi-square / Poisson identity with a
bisection search on the regularised gamma CDF).
"""
from __future__ import annotations

import math


def _gammainc_reg(a: float, x: float) -> float:
    """Regularised lower incomplete gamma P(a, x), series / continued fraction."""
    if x <= 0:
        return 0.0
    if x < a + 1.0:
        # Series representation.
        term = 1.0 / a
        total = term
        n = 1
        while True:
            term *= x / (a + n)
            total += term
            if abs(term) < abs(total) * 1e-12 or n > 1000:
                break
            n += 1
        return total * math.exp(-x + a * math.log(x) - math.lgamma(a))
    # Continued fraction for Q(a, x), then P = 1 - Q.
    b = x + 1.0 - a
    c = 1e300
    d = 1.0 / b
    h = d
    for i in range(1, 1000):
        an = -i * (i - a)
        b += 2.0
        d = an * d + b
        if abs(d) < 1e-300:
            d = 1e-300
        c = b + an / c
        if abs(c) < 1e-300:
            c = 1e-300
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 1e-12:
            break
    q = math.exp(-x + a * math.log(x) - math.lgamma(a)) * h
    return 1.0 - q


def _poisson_cdf(k: int, lam: float) -> float:
    """P(X <= k) for X ~ Poisson(lam), via the gamma identity."""
    if lam <= 0:
        return 1.0 if k >= 0 else 0.0
    return 1.0 - _gammainc_reg(k + 1, lam)


def poisson_rate_ci(count: int, exposure: float, level: float = 0.95) -> tuple:
    """Exact two-sided CI for a rate per unit exposure.

    Returns (lower, upper) rates per unit of exposure. For count == 0
    the lower bound is 0.
    """
    alpha = 1.0 - level
    if exposure <= 0:
        raise ValueError("exposure must be positive")
    if count == 0:
        upper = -math.log(alpha / 2.0) / exposure
        return (0.0, upper)
    lo_target = alpha / 2.0
    hi_target = 1.0 - alpha / 2.0
    # Lower bound: lam such that P(X >= count) = alpha/2, i.e. CDF(count-1) = 1 - alpha/2.
    lo, hi = 0.0, float(count) * 4.0 + 10.0
    for _ in range(200):
        mid = (lo + hi) / 2.0
        if _poisson_cdf(count - 1, mid) > hi_target:
            lo = mid
        else:
            hi = mid
    lower = (lo + hi) / 2.0 / exposure
    # Upper bound: lam such that P(X <= count) = alpha/2.
    lo, hi = 0.0, float(count) * 4.0 + 10.0
    for _ in range(200):
        mid = (lo + hi) / 2.0
        if _poisson_cdf(count, mid) > lo_target:
            lo = mid
        else:
            hi = mid
    upper = (lo + hi) / 2.0 / exposure
    return (lower, upper)


def poisson_rate_ci_per_1k(count: int, miles: float, level: float = 0.95) -> tuple:
    lo, hi = poisson_rate_ci(count, miles / 1000.0, level)
    return (lo, hi)


def compare_rates(count1: int, miles1: float, count2: int, miles2: float) -> dict:
    """Two-sample Poisson rate comparison (conditional binomial test).

    Given the total count, the split between two exposures is Binomial
    under the null of equal rates. Returns the two-sided p-value and
    the rate ratio (release 2 vs release 1) per 1,000 miles.
    """
    total = count1 + count2
    if total == 0 or miles1 <= 0 or miles2 <= 0:
        return {"p_value": 1.0, "rate_ratio": 1.0, "significant_95": False}
    p = miles2 / (miles1 + miles2)
    # Two-sided binomial p-value: sum of probabilities <= P(X == count2).
    from math import comb

    def pmf(k):
        return comb(total, k) * (p ** k) * ((1 - p) ** (total - k))

    observed = pmf(count2)
    p_value = sum(pmf(k) for k in range(total + 1) if pmf(k) <= observed + 1e-15)
    rate1 = 1000.0 * count1 / miles1
    rate2 = 1000.0 * count2 / miles2
    ratio = rate2 / rate1 if rate1 > 0 else float("inf")
    return {
        "p_value": round(min(p_value, 1.0), 4),
        "rate_ratio": round(ratio, 3),
        "rate1_per_1k": round(rate1, 3),
        "rate2_per_1k": round(rate2, 3),
        "significant_95": p_value < 0.05,
    }
