"""Municipal bond pricing: yield-to-maturity, yield-to-call, yield-to-worst.

Bonds pay semiannual coupons (the municipal market convention) and redeem
at par (100). Call schedules are the defining feature of munis: most new
issues are callable 10 years after issuance, so yield-to-worst — the
lowest yield across maturity and every call date — is the yield traders
actually quote, not yield-to-maturity.
"""

from dataclasses import dataclass, field


@dataclass
class MunicipalBond:
    """A fixed-rate municipal bond. All yields are annual, tax-exempt."""

    coupon: float          # annual coupon rate, e.g. 0.05 for 5%
    maturity_years: float  # years to maturity
    call_dates: list = field(default_factory=list)  # years to each call date
    call_prices: list = field(default_factory=list)  # redemption price at each call
    frequency: int = 2     # coupons per year (2 = semiannual)

    def __post_init__(self):
        if self.coupon < 0 or self.maturity_years <= 0:
            raise ValueError("coupon must be >= 0 and maturity > 0")
        if len(self.call_dates) != len(self.call_prices):
            raise ValueError("call dates and call prices must match")
        if any(c <= 0 or c >= self.maturity_years for c in self.call_dates):
            raise ValueError("call dates must fall strictly before maturity")
        if any(p <= 0 for p in self.call_prices):
            raise ValueError("call prices must be positive")

    def cashflows(self, horizon_years=None, redemption=100.0):
        """(time, amount) cash flows up to ``horizon_years`` (default maturity)."""
        horizon = horizon_years if horizon_years is not None else self.maturity_years
        n = int(round(horizon * self.frequency))
        coupon = 100.0 * self.coupon / self.frequency
        flows = [(k / self.frequency, coupon) for k in range(1, n + 1)]
        flows[-1] = (flows[-1][0], flows[-1][1] + redemption)
        return flows


def _present_value(flows, annual_yield, frequency=2):
    return sum(cf / (1.0 + annual_yield / frequency) ** (t * frequency)
               for t, cf in flows)


def price(bond, annual_yield, horizon_years=None, redemption=100.0):
    """Clean price per 100 par at a given annual yield."""
    return _present_value(bond.cashflows(horizon_years, redemption),
                          annual_yield, bond.frequency)


def _solve_yield(bond, target_price, horizon_years=None, redemption=100.0):
    """Bisection solve for the yield that reproduces ``target_price``."""
    lo, hi = -0.09, 1.0  # yields are monotone decreasing in price
    if not (price(bond, hi, horizon_years, redemption)
            <= target_price <= price(bond, lo, horizon_years, redemption)):
        raise ValueError("target price is outside the solvable yield range")
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if price(bond, mid, horizon_years, redemption) > target_price:
            lo = mid
        else:
            hi = mid
        if hi - lo < 1e-12:
            break
    return 0.5 * (lo + hi)


def yield_to_maturity(bond, market_price):
    """Yield assuming the bond is held to maturity."""
    return _solve_yield(bond, market_price)


def yield_to_call(bond, market_price, call_index=0):
    """Yield assuming redemption at one call date at its call price."""
    return _solve_yield(bond, market_price,
                        horizon_years=bond.call_dates[call_index],
                        redemption=bond.call_prices[call_index])


def yield_to_worst(bond, market_price):
    """Lowest yield across maturity and every call date — the quoted yield."""
    candidates = [("maturity", yield_to_maturity(bond, market_price))]
    for i in range(len(bond.call_dates)):
        candidates.append((f"call@{bond.call_dates[i]}y",
                           yield_to_call(bond, market_price, i)))
    worst_name, worst_yield = min(candidates, key=lambda c: c[1])
    return worst_yield, worst_name
