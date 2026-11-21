"""Timing conventions, flow classification, and value-neutrality checks.

The value-neutrality property: moving a flow to a period boundary (or
re-timing it within the rules) must not change the period's return. A
flow classified as "beginning-of-day" belongs to the sub-period that
starts that day; "end-of-day" belongs to the sub-period that ends that
day. Misclassifying a flow breaks neutrality and silently drifts the
methodology — the exact failure mode this module guards against.
"""

from .returns import Flow, Valuation, time_weighted_return


def classify_flow(day, period_start, period_end, convention="end-of-day"):
    """Say which sub-period a flow's amount first appears in.

    Under "end-of-day", a flow lands after its day's mark, so it first
    appears in the sub-period starting on its day ("next-subperiod"); a
    flow on the period-end day lands in the ending value only
    ("ending-value"). Under "beginning-of-day", a flow lands before its
    day's mark, so it first appears in the sub-period ending on its day
    ("prior-subperiod"); a flow on the period-start day is in the
    starting value ("starting-value").
    """
    if convention not in ("end-of-day", "beginning-of-day"):
        raise ValueError("unknown convention: %r" % convention)
    if not (period_start <= day <= period_end):
        raise ValueError("flow day outside period")
    if convention == "end-of-day":
        return "ending-value" if day == period_end else "next-subperiod"
    return "starting-value" if day == period_start else "prior-subperiod"


def check_value_neutrality(start_value, end_value, flow_amount, flow_day,
                           period_start=0.0, period_end=1.0):
    """Verify a boundary-timed flow does not change the period return.

    A flow on the period-start boundary, valued at the start mark, must
    leave the TWR unchanged versus the same period with no flow; same
    for a flow on the period-end boundary. Returns (neutral, details).
    """
    base = time_weighted_return(
        start_value, end_value, [],
        [Valuation(period_start, start_value), Valuation(period_end, end_value)],
        start_day=period_start, end_day=period_end)
    details = {"base_twr": base}
    # Flow at the start boundary: mark at start, flow added, then growth.
    # End value must include the flow plus its growth for neutrality.
    growth = (end_value / start_value) if start_value else 1.0
    end_with_start_flow = (start_value + flow_amount) * growth
    twr_start = time_weighted_return(
        start_value, end_with_start_flow,
        [Flow(period_start, flow_amount)],
        [Valuation(period_start, start_value),
         Valuation(period_end, end_with_start_flow)],
        start_day=period_start, end_day=period_end)
    details["start_boundary_twr"] = twr_start
    # Flow at the end boundary: growth first, then the flow lands.
    twr_end = time_weighted_return(
        start_value, end_value + flow_amount,
        [Flow(period_end, flow_amount)],
        [Valuation(period_start, start_value), Valuation(period_end, end_value)],
        start_day=period_start, end_day=period_end)
    details["end_boundary_twr"] = twr_end
    neutral = (abs(twr_start - base) < 1e-9 and abs(twr_end - base) < 1e-9)
    return neutral, details


def adversarial_timing_cases():
    """Deliberately awkward timing cases a correct implementation must handle.

    Returns a list of dicts describing each case for golden-value tests.
    """
    return [
        {"name": "flow_on_period_start", "day": 0.0, "amount": 50.0},
        {"name": "flow_on_period_end", "day": 1.0, "amount": 50.0},
        {"name": "same_day_contribution_and_distribution",
         "flows": [Flow(0.5, 100.0), Flow(0.5, -40.0)]},
        {"name": "zero_start_nav_with_first_flow",
         "start_value": 0.0, "flows": [Flow(0.0, 100.0)]},
        {"name": "distribution_larger_than_gain",
         "flows": [Flow(0.5, -80.0)]},
    ]
