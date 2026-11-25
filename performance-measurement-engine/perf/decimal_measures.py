"""Time-weighted measures in exact decimal arithmetic.

Extends the float returns in perf/returns.py with Decimal versions of
the two time-weighted measures the index-calculation library needs:

- Modified Dietz with exact decimal day weights.
- Unitised / index-level chaining: chain-link sub-period returns into
  an index level series, so an index value is reproducible from its
  sub-period returns alone.
"""

from decimal import Decimal

from .decimal_solver import money


def decimal_modified_dietz(start_value, end_value, flows,
                           start_day=0, end_day=1):
    """Modified Dietz return in Decimal.

    flows is a list of (day, amount) from the fund's view: positive =
    contribution in, negative = distribution out. Each flow is weighted
    by the fraction of the period remaining after its day. Same-day
    flows are netted before weighting (canonical order), so splitting
    a flow across two same-day entries cannot change the result.
    """
    start_value, end_value = money(start_value), money(end_value)
    start_day, end_day = money(start_day), money(end_day)
    if end_day <= start_day:
        raise ValueError("end_day must be after start_day")
    period = end_day - start_day
    netted = {}
    for day, amount in flows:
        day, amount = money(day), money(amount)
        if not (start_day <= day <= end_day):
            raise ValueError("flow day %r outside period" % (day,))
        netted[day] = netted.get(day, Decimal(0)) + amount
    net_flow = sum(netted.values(), Decimal(0))
    weighted = sum((amount * (end_day - day) / period
                    for day, amount in netted.items()), Decimal(0))
    denominator = start_value + weighted
    if denominator == 0:
        raise ValueError("Modified Dietz denominator is zero")
    return (end_value - start_value - net_flow) / denominator


def chained_index(sub_period_returns, base_level="100"):
    """Chain-link sub-period returns into index levels.

    Returns a list of Decimal levels starting at base_level, one entry
    per sub-period end. The same returns always reproduce the same
    levels: chaining is the only operation, and it is exact decimal
    multiplication.
    """
    level = money(base_level)
    levels = [level]
    for ret in sub_period_returns:
        level = level * (Decimal(1) + money(ret))
        levels.append(level)
    return levels


def unitised_return(start_units, end_units, start_nav, end_nav):
    """Unitised (per-unit) return from unit counts and NAVs.

    A unitised index tracks value per unit, so flows change the unit
    count, not the per-unit price. Returns (end_nav / end_units) /
    (start_nav / start_units) - 1, in Decimal.
    """
    start_units, end_units = money(start_units), money(end_units)
    start_nav, end_nav = money(start_nav), money(end_nav)
    if start_units == 0 or end_units == 0:
        raise ValueError("unit count must be non-zero")
    if start_nav == 0:
        raise ValueError("starting NAV must be non-zero")
    return (end_nav / end_units) / (start_nav / start_units) - Decimal(1)
