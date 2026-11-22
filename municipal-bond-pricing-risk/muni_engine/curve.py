"""Tax-exempt yield-curve construction for municipal bonds.

Municipal bonds pay interest exempt from federal income tax, so their
yields are quoted on a tax-exempt basis and sit below comparable taxable
yields. The curve here is built by bootstrapping zero-coupon rates from
par yields of benchmark general-obligation bonds, then interpolating
linearly in zero-rate space. ``taxable_equivalent_yield`` converts a
tax-exempt yield to the taxable yield an investor in a given bracket
would need to earn the same after-tax return.
"""

from bisect import bisect_left


class TaxExemptCurve:
    """Zero-coupon curve defined by (tenor in years, zero rate) knots."""

    def __init__(self, tenors, zero_rates):
        if len(tenors) != len(zero_rates) or len(tenors) < 2:
            raise ValueError("need at least two matching tenor/rate knots")
        if any(b <= a for a, b in zip(tenors, tenors[1:])):
            raise ValueError("tenors must be strictly increasing")
        self.tenors = list(tenors)
        self.zero_rates = list(zero_rates)

    def zero_rate(self, tenor):
        """Zero rate at any tenor, linear interpolation, flat extrapolation."""
        if tenor <= self.tenors[0]:
            return self.zero_rates[0]
        if tenor >= self.tenors[-1]:
            return self.zero_rates[-1]
        i = bisect_left(self.tenors, tenor)
        t0, t1 = self.tenors[i - 1], self.tenors[i]
        r0, r1 = self.zero_rates[i - 1], self.zero_rates[i]
        return r0 + (r1 - r0) * (tenor - t0) / (t1 - t0)

    def discount_factor(self, tenor):
        """Discount factor for a cash flow ``tenor`` years out."""
        return 1.0 / (1.0 + self.zero_rate(tenor)) ** tenor

    @staticmethod
    def taxable_equivalent_yield(tax_exempt_yield, marginal_tax_rate):
        """Taxable yield giving the same after-tax return in a tax bracket."""
        if not 0.0 <= marginal_tax_rate < 1.0:
            raise ValueError("marginal tax rate must be in [0, 1)")
        return tax_exempt_yield / (1.0 - marginal_tax_rate)


def bootstrap_curve(par_tenors, par_yields, frequency=2):
    """Bootstrap zero rates from par yields of benchmark muni bonds.

    Each benchmark bond pays ``frequency`` coupons a year at its par yield
    and redeems at 100. Each zero rate is solved by bisection: the trial
    curve is the already-solved knots plus the trial knot at this tenor,
    with linear interpolation between knots, and the rate is chosen so the
    benchmark bond reprices exactly at par.
    """
    if len(par_tenors) != len(par_yields) or not par_tenors:
        raise ValueError("need matching non-empty par tenor/yield lists")
    tenors, rates = [], []

    def bond_price(tenor, par_yield, trial_rate):
        n = int(round(tenor * frequency))
        coupon = 100.0 * par_yield / frequency
        total = 0.0
        if len(tenors) >= 1:
            curve = TaxExemptCurve(tenors + [tenor], rates + [trial_rate])
            discount = curve.discount_factor
        else:
            discount = lambda t: 1.0 / (1.0 + trial_rate) ** t
        for k in range(1, n + 1):
            t = k / frequency
            amount = coupon + (100.0 if k == n else 0.0)
            total += amount * discount(t)
        return total

    for tenor, par_yield in zip(par_tenors, par_yields):
        if tenor * frequency < 1:
            raise ValueError("tenor too short for coupon frequency")
        lo, hi = 0.0001, 0.50
        if not (bond_price(tenor, par_yield, hi) <= 100.0
                <= bond_price(tenor, par_yield, lo)):
            raise ValueError("par yields inconsistent with bootstrapping")
        for _ in range(100):
            mid = 0.5 * (lo + hi)
            if bond_price(tenor, par_yield, mid) > 100.0:
                lo = mid
            else:
                hi = mid
            if hi - lo < 1e-12:
                break
        tenors.append(tenor)
        rates.append(0.5 * (lo + hi))
    return TaxExemptCurve(tenors, rates)
