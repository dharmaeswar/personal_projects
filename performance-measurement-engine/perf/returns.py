"""Return methodologies as pure, auditable functions over conserved flows.

A Flow is (day, amount): positive for a contribution into the fund,
negative for a distribution out. Days are counted from the period start
(day 0) to the period end (day N). Valuations are (day, value) marks.

Conventions (documented, not hidden):
- TWR splits the period at every flow day; each sub-period return is
  (end_value - start_value - flow) / (start_value + flow_if_at_start).
  A flow is applied at the END of its day, so the sub-period ending on
  that day excludes it and the next sub-period starts with it included.
- Modified Dietz weights each flow by the fraction of the period
  remaining after its day: weight = (N - day) / N.
- IRR solves NPV(r) = 0 by bisection; it is the money-weighted return.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Flow:
    day: float
    amount: float  # + contribution, - distribution


@dataclass(frozen=True)
class Valuation:
    day: float
    value: float


def _check_days(start_day, end_day, flows, valuations):
    if end_day <= start_day:
        raise ValueError("end_day must be after start_day")
    for flow in flows:
        if not (start_day <= flow.day <= end_day):
            raise ValueError("flow day %r outside period" % (flow.day,))
    for val in valuations:
        if not (start_day <= val.day <= end_day):
            raise ValueError("valuation day %r outside period" % (val.day,))


def time_weighted_return(start_value, end_value, flows, valuations,
                         start_day=0.0, end_day=1.0):
    """Chain-linked TWR. valuations must include start and end marks."""
    flows = sorted(flows, key=lambda f: f.day)
    marks = {v.day: v.value for v in valuations}
    _check_days(start_day, end_day, flows, valuations)
    if start_day not in marks or end_day not in marks:
        raise ValueError("valuations must include start and end marks")
    # Flows sharing a day are netted into one split: splitting twice on
    # the same mark would re-price the same sub-period.
    net_by_day = {}
    for flow in flows:
        net_by_day[flow.day] = net_by_day.get(flow.day, 0.0) + flow.amount
    for day in net_by_day:
        if day not in marks:
            raise ValueError("a valuation mark is required on every flow day")
    twr = 1.0
    prev_value = start_value
    for day in sorted(net_by_day):
        mark = marks[day]
        sub = (mark - prev_value) / prev_value if prev_value else 0.0
        twr *= (1.0 + sub)
        prev_value = mark + net_by_day[day]
    sub = (end_value - prev_value) / prev_value if prev_value else 0.0
    twr *= (1.0 + sub)
    return twr - 1.0


def modified_dietz(start_value, end_value, flows, start_day=0.0, end_day=1.0):
    """Modified Dietz return with day-weighted flows."""
    _check_days(start_day, end_day, flows, [])
    period = end_day - start_day
    net_flow = sum(f.amount for f in flows)
    weighted = sum(f.amount * (end_day - f.day) / period for f in flows)
    denominator = start_value + weighted
    if denominator == 0:
        raise ValueError("Modified Dietz denominator is zero")
    return (end_value - start_value - net_flow) / denominator


def irr(cash_flows, low=-0.9999, high=10.0, tol=1e-12, max_iter=200):
    """Money-weighted return: the rate r with NPV(r) = 0.

    cash_flows is a list of (day, amount) with day in years from the
    first flow; outflows from the investor are negative.
    """
    if not cash_flows:
        raise ValueError("no cash flows")
    times = [day for day, _ in cash_flows]
    if min(times) != 0:
        raise ValueError("first cash flow must be at day 0")

    def npv(rate):
        return sum(amount / (1.0 + rate) ** day for day, amount in cash_flows)

    lo, hi = low, high
    flo, fhi = npv(lo), npv(hi)
    if flo == 0:
        return lo
    if fhi == 0:
        return hi
    if (flo > 0) == (fhi > 0):
        raise ValueError("IRR not bracketed in [%r, %r]" % (low, high))
    for _ in range(max_iter):
        mid = (lo + hi) / 2.0
        fmid = npv(mid)
        if abs(fmid) < tol or (hi - lo) / 2.0 < tol:
            return mid
        if (fmid > 0) == (flo > 0):
            lo, flo = mid, fmid
        else:
            hi = mid
    return (lo + hi) / 2.0


def geometric_excess(portfolio_return, benchmark_return):
    """Geometric excess return: (1 + Rp) / (1 + Rb) - 1."""
    return (1.0 + portfolio_return) / (1.0 + benchmark_return) - 1.0
