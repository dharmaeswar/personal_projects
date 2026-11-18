"""Interest-rate models: discount curve, bootstrapping, Vasicek bond pricing.

Conventions: rates are continuously compounded unless stated otherwise;
times are in years.
"""

from __future__ import annotations

import math
from bisect import bisect_right


class DiscountCurve:
    """Discount curve built from zero-coupon (spot) rates at node maturities.

    Discount factors at the nodes are DF(t) = exp(-r(t) * t). Between nodes the
    log discount factor is linearly interpolated (piecewise-constant forward
    rates), which preserves monotonicity of DF whenever node DFs decrease.
    Beyond the last node the final forward rate is held flat.
    """

    def __init__(self, maturities: list[float], zero_rates: list[float]):
        if len(maturities) != len(zero_rates):
            raise ValueError("maturities and zero_rates must have equal length")
        if not maturities:
            raise ValueError("curve needs at least one node")
        if any(t <= 0 for t in maturities):
            raise ValueError("maturities must be positive")
        if list(maturities) != sorted(maturities):
            raise ValueError("maturities must be increasing")
        self.maturities = [float(t) for t in maturities]
        self.zero_rates = [float(r) for r in zero_rates]
        self._times = [0.0] + self.maturities
        self._log_dfs = [0.0] + [-r * t for t, r in zip(self.maturities, self.zero_rates)]

    def discount(self, t: float) -> float:
        """Discount factor for maturity ``t`` (years)."""
        if t <= 0:
            return 1.0
        times, log_dfs = self._times, self._log_dfs
        if t >= times[-1]:
            # Flat forward extrapolation using the last segment's slope.
            slope = (log_dfs[-1] - log_dfs[-2]) / (times[-1] - times[-2])
            return math.exp(log_dfs[-1] + slope * (t - times[-1]))
        i = bisect_right(times, t) - 1
        w = (t - times[i]) / (times[i + 1] - times[i])
        return math.exp(log_dfs[i] + w * (log_dfs[i + 1] - log_dfs[i]))

    def zero_rate(self, t: float) -> float:
        """Continuously compounded zero rate implied by the curve at ``t``."""
        if t <= 0:
            raise ValueError("t must be positive")
        return -math.log(self.discount(t)) / t

    def zero_coupon_bond_price(self, maturity: float, face: float = 100.0) -> float:
        """Price of a zero-coupon bond paying ``face`` at ``maturity``."""
        return face * self.discount(maturity)


def bootstrap_discount_factors(par_yields: list[float],
                               maturities: list[float]) -> list[float]:
    """Bootstrap discount factors from annual-pay par yields.

    ``maturities`` must be consecutive annual maturities [1, 2, ..., N] so the
    standard recursion applies: with DF_1 = 1 / (1 + y_1),

        DF_n = (1 - y_n * sum_{i<n} DF_i) / (1 + y_n).
    """
    if [float(m) for m in maturities] != [float(i + 1) for i in range(len(maturities))]:
        raise ValueError("bootstrap requires consecutive annual maturities 1..N")
    dfs: list[float] = []
    for y in par_yields:
        df_n = (1.0 - y * sum(dfs)) / (1.0 + y)
        dfs.append(df_n)
    return dfs


def par_bond_price(par_yield: float, discount_factors: list[float]) -> float:
    """Price (per unit notional) of an annual-pay par bond.

    Uses the first ``len(discount_factors)`` discount factors; a correctly
    bootstrapped curve reprices every par bond to exactly 1.0.
    """
    return par_yield * sum(discount_factors) + discount_factors[-1]


def vasicek_bond_price(r0: float, tau: float, a: float, theta: float,
                       sigma: float, face: float = 100.0) -> float:
    """Zero-coupon bond price under the Vasicek short-rate model.

    dr = a (theta - r) dt + sigma dW. Closed form:
        P = A(tau) * exp(-B(tau) * r0),
        B = (1 - exp(-a tau)) / a,
        ln A = (B - tau) * (a^2 theta - sigma^2 / 2) / a^2 - sigma^2 B^2 / (4a).
    """
    if tau <= 0:
        return float(face)
    if a < 1e-12:  # degenerate no-mean-reversion limit: B -> tau
        b = tau
        log_a = -0.5 * sigma ** 2 * tau ** 2 / 2.0 * 0.0  # A -> 1 in this limit to O(sigma^2 tau^3)
        return face * math.exp(log_a - b * r0)
    b = (1.0 - math.exp(-a * tau)) / a
    log_a = ((b - tau) * (a * a * theta - 0.5 * sigma * sigma) / (a * a)
             - sigma * sigma * b * b / (4.0 * a))
    return face * math.exp(log_a - b * r0)
