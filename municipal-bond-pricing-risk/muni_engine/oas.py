"""Option-adjusted spread (OAS) for callable municipal bonds.

A callable muni is worth less than an otherwise identical bullet bond
because the issuer holds the call option. OAS is the constant spread over
the tax-exempt curve that equates the model price of the callable bond
(with the call option exercised optimally) to its market price.

The model is a recombining binomial short-rate tree (Ho-Lee style): the
one-period short rate moves up or down by a fixed lognormal volatility
each half-year, with drift terms calibrated so the tree reprices the
input zero curve exactly. The callable bond is priced by backward
induction, exercising the call whenever the continuation value exceeds
the call price. OAS is found by bisection on the spread.
"""

import math

from .bonds import MunicipalBond
from .curve import TaxExemptCurve


def _calibrate_tree(curve, n_periods, dt, vol):
    """Drift (theta) per step so the tree reprices the zero curve.

    Short rate at step i, node j (j up-moves): r = theta[i] * exp((2j - i) * vol * sqrt(dt)).
    theta[i] is solved by matching the discount factor to tenor (i+1)*dt.
    """
    thetas = []
    for i in range(n_periods):
        tenor = (i + 1) * dt
        target_df = curve.discount_factor(tenor)
        # DF = E[exp(-r_0 dt) ... ] over the tree; solve theta by bisection.
        # At step i, rates depend on theta[i] and earlier thetas only.
        def tree_df(theta):
            # forward induction of state prices
            states = {0: 1.0}
            for step in range(i + 1):
                th = thetas[step] if step < i else theta
                nxt = {}
                for j, prob in states.items():
                    r = th * math.exp((2 * j - step) * vol * math.sqrt(dt))
                    disc = math.exp(-r * dt)
                    nxt[j] = nxt.get(j, 0.0) + 0.5 * prob * disc
                    nxt[j + 1] = nxt.get(j + 1, 0.0) + 0.5 * prob * disc
                states = nxt
            return sum(states.values())
        lo, hi = 1e-6, 2.0
        for _ in range(100):
            mid = 0.5 * (lo + hi)
            if tree_df(mid) > target_df:
                lo = mid
            else:
                hi = mid
            if hi - lo < 1e-10:
                break
        thetas.append(0.5 * (lo + hi))
    return thetas


def _tree_price(bond, curve, spread, vol, thetas=None):
    """Price a callable bond on the calibrated tree with a spread to the curve."""
    dt = 1.0 / bond.frequency
    n = int(round(bond.maturity_years * bond.frequency))
    if thetas is None:
        thetas = _calibrate_tree(curve, n, dt, vol)
    call_map = dict(zip(
        (int(round(c * bond.frequency)) for c in bond.call_dates),
        bond.call_prices))
    coupon = 100.0 * bond.coupon / bond.frequency
    # value at each node at maturity, ex-coupon: principal only
    values = {j: 100.0 for j in range(n + 1)}
    for i in range(n - 1, -1, -1):
        nxt = {}
        for j in range(i + 1):
            r = thetas[i] * math.exp((2 * j - i) * vol * math.sqrt(dt))
            disc = math.exp(-(r + spread) * dt)
            continuation = disc * (0.5 * values[j] + 0.5 * values[j + 1] + coupon)
            step = i + 1  # period just completed
            if step in call_map:
                nxt[j] = min(continuation, call_map[step])
            else:
                nxt[j] = continuation
        values = nxt
    return values[0]


def callable_bond_price(bond, curve, spread=0.0, vol=0.10):
    """Model price of the callable bond at a given OAS (spread to the curve)."""
    return _tree_price(bond, curve, spread, vol)


def option_adjusted_spread(bond, curve, market_price, vol=0.10):
    """Spread over the curve that reprices the callable bond at market price."""
    dt = 1.0 / bond.frequency
    n = int(round(bond.maturity_years * bond.frequency))
    thetas = _calibrate_tree(curve, n, dt, vol)  # calibrated once, reused
    lo, hi = -0.05, 0.10
    if not (_tree_price(bond, curve, hi, vol, thetas)
            <= market_price <= _tree_price(bond, curve, lo, vol, thetas)):
        raise ValueError("market price outside the solvable OAS range")
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        if _tree_price(bond, curve, mid, vol, thetas) > market_price:
            lo = mid
        else:
            hi = mid
        if hi - lo < 1e-9:
            break
    return 0.5 * (lo + hi)
