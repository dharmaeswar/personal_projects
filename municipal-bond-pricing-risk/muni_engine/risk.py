"""Risk measures for municipal bonds: duration, convexity, DV01, key rates.

All measures are computed by repricing (finite differences on yield or
on individual key-rate tenors), which is how a desk measures the risk of
an inventory of bonds whose cash flows depend on yields — callable munis
in particular, where closed-form duration understates the effect of the
embedded call.
"""

from .bonds import price


def duration_convexity(bond, annual_yield, bump=0.0001):
    """Modified duration and convexity from central finite differences."""
    p0 = price(bond, annual_yield)
    p_up = price(bond, annual_yield + bump)
    p_dn = price(bond, annual_yield - bump)
    duration = (p_dn - p_up) / (2.0 * bump * p0)
    convexity = (p_up + p_dn - 2.0 * p0) / (bump ** 2 * p0)
    return duration, convexity


def dv01(bond, annual_yield):
    """Dollar value of one basis point per 100 par: P&L from a 1bp yield fall."""
    return price(bond, annual_yield - 0.0001) - price(bond, annual_yield)


def key_rate_durations(bond, curve, key_tenors=(2, 5, 10, 20, 30)):
    """Sensitivity of price to a 1bp move in each key-rate tenor.

    Each key tenor's zero rate is bumped in turn (neighbouring tenors
    untouched — a triangular bump is approximated by the single-knot bump
    here, which is the standard desk shortcut for a quick screen) and the
    bond is repriced off the bumped curve. Returns {tenor: duration}.
    """
    from .curve import TaxExemptCurve

    base = _price_off_curve(bond, curve)
    out = {}
    for tenor in key_tenors:
        bumped_rates = [r + (0.0001 if t == tenor else 0.0)
                        for t, r in zip(curve.tenors, curve.zero_rates)]
        if tenor not in curve.tenors:
            # extend the curve with the new knot at the interpolated rate
            tenors = sorted(curve.tenors + [tenor])
            rates = [curve.zero_rate(t) + (0.0001 if t == tenor else 0.0)
                     for t in tenors]
            bumped = TaxExemptCurve(tenors, rates)
        else:
            bumped = TaxExemptCurve(curve.tenors, bumped_rates)
        p_bumped = _price_off_curve(bond, bumped)
        out[tenor] = (base - p_bumped) / (0.0001 * base)
    return out


def _price_off_curve(bond, curve):
    """Price a bullet bond by discounting its cash flows on the curve."""
    return sum(cf * curve.discount_factor(t)
               for t, cf in bond.cashflows())


def spread_scenarios(bond, annual_yield, spreads_bp=(-100, -50, 50, 100, 200)):
    """Price and P&L of the bond under parallel credit-spread shifts (bp)."""
    base = price(bond, annual_yield)
    return {s: (price(bond, annual_yield + s / 10000.0) - base)
            for s in spreads_bp}
