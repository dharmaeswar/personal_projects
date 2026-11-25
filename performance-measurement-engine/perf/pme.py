"""Public-market equivalents (PMEs) for private-capital funds.

All money, index levels and rates are ``decimal.Decimal`` — no floats
for money or IRR solves (see perf/decimal_solver.py).

Conventions (documented, not hidden):
- A flow is (day, amount): positive for a contribution into the fund,
  negative for a distribution out. Days are in years from the first
  flow; index_levels maps each flow day to the public-index level on
  that day. Index levels must be positive.
- KS-PME (Kaplan-Schoar): the ratio of distributions to contributions,
  each discounted by public-index growth from its own day back to day
  0: discount factor for day t is I_0 / I_t. Above 1 means the fund
  beat the public market.
- Direct Alpha: the alpha that makes the index-adjusted NPV zero,
  discounting each flow by (I_t / I_0) * (1 + alpha) ** t. Solved
  with the safeguarded bracketing solver, never by iterating on an
  unbracketed root.
- Long-Nickels PME: the ratio of the future values of distributions
  to contributions, each compounded forward by index growth to the
  end day T: factor I_T / I_t.
"""

from decimal import Decimal

from .decimal_solver import money, solve_root_decimal


def _check(flows, index_levels):
    flows = [(money(day), money(amount)) for day, amount in flows]
    levels = {money(day): money(level)
              for day, level in index_levels.items()}
    if not flows:
        raise ValueError("no cash flows")
    if min(day for day, _ in flows) != 0:
        raise ValueError("first cash flow must be at day 0")
    for day, _ in flows:
        if day not in levels:
            raise ValueError("no index level for day %s" % (day,))
        if levels[day] <= 0:
            raise ValueError("index level must be positive, got %s"
                             % (levels[day],))
    return flows, levels


def discounted_weights(flows, index_levels):
    """Each flow's share of total discounted contributions+distributions.

    Weights are computed on absolute discounted amounts and sum to 1;
    the invariant test pins that property.
    """
    flows, levels = _check(flows, index_levels)
    base = levels[Decimal(0)]
    discounted = [(day, abs(amount) * base / levels[day])
                  for day, amount in flows]
    total = sum(amount for _, amount in discounted)
    if total == 0:
        raise ValueError("discounted flow total is zero")
    return [(day, amount / total) for day, amount in discounted]


def ks_pme(flows, index_levels):
    """Kaplan-Schoar PME: discounted distributions / discounted contributions."""
    flows, levels = _check(flows, index_levels)
    base = levels[Decimal(0)]
    contributions = Decimal(0)
    distributions = Decimal(0)
    for day, amount in flows:
        discounted = amount * base / levels[day]
        if amount > 0:
            contributions += discounted
        elif amount < 0:
            distributions += -discounted
    if contributions == 0:
        raise ValueError("KS-PME needs at least one contribution")
    if distributions == 0:
        raise ValueError("KS-PME needs at least one distribution")
    return distributions / contributions


def direct_alpha(flows, index_levels, low="-0.9999", high="10"):
    """Direct Alpha: the alpha with index-adjusted NPV equal to zero.

    Returns (alpha, diagnostics) from the safeguarded solver.
    """
    flows, levels = _check(flows, index_levels)
    base = levels[Decimal(0)]

    def adjusted_npv(alpha):
        total = Decimal(0)
        for day, amount in flows:
            growth = levels[day] / base
            total += amount / (growth * (Decimal(1) + alpha) ** day)
        return total

    return solve_root_decimal(adjusted_npv, low, high)


def long_nickels_pme(flows, index_levels, end_day, terminal_nav="0"):
    """Long-Nickels PME: (future-valued distributions + terminal NAV)
    / future-valued contributions at end_day. Value still held in the
    fund counts, so a fund that has not liquidated is not penalised
    for the NAV it still holds. terminal_nav defaults to 0, which is
    the fully liquidated case."""
    flows, levels = _check(flows, index_levels)
    end_day = money(end_day)
    terminal_nav = money(terminal_nav)
    if end_day not in levels:
        raise ValueError("no index level for end day %s" % (end_day,))
    terminal = levels[end_day]
    contributions = Decimal(0)
    distributions = Decimal(0)
    for day, amount in flows:
        future = amount * terminal / levels[day]
        if amount > 0:
            contributions += future
        elif amount < 0:
            distributions += -future
    if contributions == 0:
        raise ValueError("Long-Nickels PME needs at least one contribution")
    if distributions == 0 and terminal_nav == 0:
        raise ValueError("Long-Nickels PME needs at least one distribution")
    return (distributions + terminal_nav) / contributions
