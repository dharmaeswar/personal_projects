"""Discount-curve bootstrapping from par swap rates.

Given par swap rates at increasing tenors (e.g. 1, 2, 3, 5, 10 years),
solve sequentially for the discount factor at each tenor. A par swap's
fixed leg must equal its floating leg (1 - DF(T_N)), so at each tenor
    R_N * sum_{i=1}^{T_N} DF(i) = 1 - DF(T_N).
Discount factors at payment dates between knots are log-linearly
interpolated, so each tenor's equation has one unknown, DF(T_N), and is
solved by bisection. Pure standard library.
"""

import math


class DiscountCurve:
    """Discount curve bootstrapped from par swap rates (annual fixed leg)."""

    def __init__(self, par_rates):
        """``par_rates``: list of (tenor_years, par_rate), tenors increasing."""
        rates = sorted((float(t), float(r)) for t, r in par_rates)
        if not rates or rates[0][0] < 1.0:
            raise ValueError("par rates must start at tenor >= 1 year")
        for (t1, _), (t2, _) in zip(rates, rates[1:]):
            if t2 <= t1:
                raise ValueError("tenors must be strictly increasing")
        for t, r in rates:
            if t != int(t):
                raise ValueError("tenors must be whole years")
            if r <= -1.0:
                raise ValueError("par rate must be above -100%")
        self.tenors = [int(t) for t, _ in rates]
        self.discount_factors = []
        for tenor, rate in rates:
            df = self._solve_tenor(int(tenor), rate)
            self.discount_factors.append(df)

    def _df_between(self, t: float, knots, values) -> float:
        """Log-linear interpolation of DF at t, given solved knots."""
        if t <= 0:
            return 1.0
        for i, knot in enumerate(knots):
            if t == knot:
                return values[i]
            if t < knot:
                t0 = knots[i - 1] if i else 0.0
                df0 = values[i - 1] if i else 1.0
                w = (t - t0) / (knot - t0)
                return math.exp((1 - w) * math.log(df0) + w * math.log(values[i]))
        return values[-1]

    def _solve_tenor(self, tenor: int, rate: float) -> float:
        """Bisection for DF(tenor) given all earlier knots."""
        knots = self.tenors
        values = self.discount_factors

        def fixed_leg_pv(df_new: float) -> float:
            trial_knots = knots + [tenor]
            trial_values = values + [df_new]
            return sum(self._df_between(float(i), trial_knots, trial_values)
                       for i in range(1, tenor + 1))

        def f(df_new: float) -> float:
            return rate * fixed_leg_pv(df_new) + df_new - 1.0

        hi = values[-1] if values else 1.0
        if f(hi) <= 0:
            raise ValueError("bootstrapping failed: par rate inconsistent "
                             "with earlier tenors")
        lo = 1e-12
        if f(lo) >= 0:
            raise ValueError("bootstrapping failed: par rate inconsistent "
                             "with earlier tenors")
        for _ in range(200):
            mid = 0.5 * (lo + hi)
            if f(mid) < 0:
                lo = mid
            else:
                hi = mid
            if hi - lo < 1e-14:
                break
        return 0.5 * (lo + hi)

    def discount_factor(self, t: float) -> float:
        """Discount factor at time t (years), log-linear between tenors."""
        if t < 0:
            raise ValueError("t must be non-negative")
        if t == 0:
            return 1.0
        if t <= self.tenors[-1]:
            return self._df_between(t, self.tenors, self.discount_factors)
        last_t = self.tenors[-1]
        last_df = self.discount_factors[-1]
        prev_df = self.discount_factors[-2] if len(self.tenors) > 1 else 1.0
        prev_t = self.tenors[-2] if len(self.tenors) > 1 else 0.0
        fwd = -math.log(last_df / prev_df) / (last_t - prev_t)
        return last_df * math.exp(-fwd * (t - last_t))

    def zero_rate(self, t: float) -> float:
        """Continuously compounded zero rate at time t (years)."""
        if t <= 0:
            raise ValueError("t must be positive for a zero rate")
        return -math.log(self.discount_factor(t)) / t

    def forward_rate(self, t1: float, t2: float) -> float:
        """Simple forward rate between t1 and t2 (years)."""
        if not 0 <= t1 < t2:
            raise ValueError("need 0 <= t1 < t2")
        return (self.discount_factor(t1) / self.discount_factor(t2) - 1.0) / (t2 - t1)

    def par_swap_rate(self, tenor: int) -> float:
        """Recompute the par swap rate for a whole-year tenor (repricing check)."""
        if tenor < 1 or tenor > self.tenors[-1]:
            raise ValueError("tenor outside the bootstrapped curve")
        acc = sum(self.discount_factor(float(i)) for i in range(1, tenor + 1))
        return (1.0 - self.discount_factor(float(tenor))) / acc
