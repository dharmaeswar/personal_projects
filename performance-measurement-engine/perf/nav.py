"""NAV roll-forward: period-over-period decomposition that reconciles exactly.

ending NAV = beginning NAV + contributions - distributions + income + gains.
There is no plug or balancing entry: `reconcile` returns the residual,
which must be zero (within floating-point tolerance) for a clean ledger.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class NavPeriod:
    beginning_nav: float
    contributions: float
    distributions: float  # positive number: cash paid out
    income: float
    gains: float  # realised + unrealised gains (can be negative)
    ending_nav: float


def roll_forward(period):
    """Compute the ending NAV implied by the period's flows and marks."""
    return (period.beginning_nav + period.contributions
            - period.distributions + period.income + period.gains)


def reconcile(period, tol=1e-9):
    """Return (residual, ok): residual = reported ending NAV - computed NAV."""
    residual = period.ending_nav - roll_forward(period)
    return residual, abs(residual) <= tol


def chain_roll_forward(periods):
    """Roll a list of consecutive periods; each period's beginning NAV must
    equal the previous period's ending NAV. Returns the final ending NAV."""
    if not periods:
        raise ValueError("no periods")
    for prev, cur in zip(periods, periods[1:]):
        if abs(prev.ending_nav - cur.beginning_nav) > 1e-9:
            raise ValueError("NAV break between periods: %r != %r"
                             % (prev.ending_nav, cur.beginning_nav))
    for period in periods:
        residual, ok = reconcile(period)
        if not ok:
            raise ValueError("period does not reconcile (residual %r)" % (residual,))
    return periods[-1].ending_nav
