from perf.validation import (
    classify_flow, check_value_neutrality, adversarial_timing_cases,
)
from perf.returns import Flow, Valuation, time_weighted_return


def test_classify_flow_conventions():
    assert classify_flow(0.0, 0.0, 1.0, "end-of-day") == "next-subperiod"
    assert classify_flow(1.0, 0.0, 1.0, "end-of-day") == "ending-value"
    assert classify_flow(0.5, 0.0, 1.0, "end-of-day") == "next-subperiod"
    assert classify_flow(0.0, 0.0, 1.0, "beginning-of-day") == "starting-value"
    assert classify_flow(0.5, 0.0, 1.0, "beginning-of-day") == "prior-subperiod"
    assert classify_flow(1.0, 0.0, 1.0, "beginning-of-day") == "prior-subperiod"


def test_value_neutrality_boundary_flows():
    # A 50 flow on either boundary of a 100 -> 110 period leaves TWR at 10%.
    neutral, details = check_value_neutrality(100.0, 110.0, 50.0, 0.0)
    assert neutral is True
    assert abs(details["base_twr"] - 0.10) < 1e-12
    assert abs(details["start_boundary_twr"] - 0.10) < 1e-12
    assert abs(details["end_boundary_twr"] - 0.10) < 1e-12


def test_adversarial_cases_are_described():
    cases = adversarial_timing_cases()
    names = {c["name"] for c in cases}
    assert {"flow_on_period_start", "flow_on_period_end",
            "same_day_contribution_and_distribution",
            "zero_start_nav_with_first_flow",
            "distribution_larger_than_gain"} <= names


def test_zero_start_nav_with_first_flow():
    # Starting from zero NAV, a first contribution seeds the fund; the
    # sub-period before the flow has no base, so TWR is the post-flow return.
    result = time_weighted_return(
        0.0, 110.0, [Flow(0.0, 100.0)],
        [Valuation(0.0, 0.0), Valuation(1.0, 110.0)])
    assert abs(result - 0.10) < 1e-12
