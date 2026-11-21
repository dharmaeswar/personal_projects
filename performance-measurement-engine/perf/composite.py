"""GIPS-adjacent composite returns.

A composite groups portfolios managed to the same mandate. The composite
return is the asset-weighted return of its portfolios, weighted by each
portfolio's beginning-of-period market value; the equal-weighted return
and the equal-weighted dispersion (standard deviation of portfolio
returns around the equal-weighted mean) are reported alongside it so a
reader can see how much the composite return depends on its largest
portfolios.

This module computes composite figures from portfolio returns. It does
not claim GIPS verification work — verification is a separate, human
process; the code only implements the arithmetic a composite calculation
needs, with every input explicit.
"""

import math


def asset_weighted_return(portfolios):
    """Asset-weighted composite return.

    portfolios is a list of (beginning_value, period_return). Weights are
    beginning-of-period market values; portfolios with zero beginning
    value carry zero weight. Raises ValueError on negative values or an
    empty list.
    """
    if not portfolios:
        raise ValueError("no portfolios in composite")
    total = 0.0
    weighted = 0.0
    for beginning_value, period_return in portfolios:
        if beginning_value < 0:
            raise ValueError("beginning value must not be negative: %r"
                             % (beginning_value,))
        total += beginning_value
        weighted += beginning_value * period_return
    if total == 0:
        raise ValueError("composite has zero total beginning value")
    return weighted / total


def equal_weighted_return(returns):
    """Simple mean of portfolio returns."""
    if not returns:
        raise ValueError("no returns")
    return sum(returns) / len(returns)


def composite_dispersion(returns):
    """Equal-weighted standard deviation of portfolio returns.

    Population standard deviation around the equal-weighted mean — the
    dispersion measure GIPS asks composites to present. A single
    portfolio has zero dispersion.
    """
    if not returns:
        raise ValueError("no returns")
    mean = equal_weighted_return(returns)
    variance = sum((r - mean) ** 2 for r in returns) / len(returns)
    return math.sqrt(variance)


def composite_summary(portfolios):
    """One dict with asset-weighted, equal-weighted and dispersion figures.

    portfolios is a list of (beginning_value, period_return).
    """
    returns = [period_return for _, period_return in portfolios]
    return {
        "asset_weighted_return": asset_weighted_return(portfolios),
        "equal_weighted_return": equal_weighted_return(returns),
        "dispersion": composite_dispersion(returns),
        "portfolio_count": len(portfolios),
        "total_beginning_value": sum(v for v, _ in portfolios),
    }
