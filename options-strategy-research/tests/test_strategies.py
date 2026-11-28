from options.strategies import (build_straddle, build_covered_call,
                                build_iron_condor, strategy_payoff,
                                payoff_curve, max_loss, max_gain)
from options.pricing import call_price, put_price


def test_straddle_payoff_is_v_shaped():
    legs = build_straddle(100.0, 30, 0.05, 0.25)
    atm = strategy_payoff(legs, 100.0)
    low = strategy_payoff(legs, 80.0)
    high = strategy_payoff(legs, 120.0)
    assert atm < 0  # at the strike the straddle loses its premium
    assert low > 0 and high > 0
    # Symmetric: equal distance from the strike gives equal payoff.
    assert abs(strategy_payoff(legs, 90.0) - strategy_payoff(legs, 110.0)) < 1e-9


def test_straddle_breakevens():
    legs = build_straddle(100.0, 30, 0.05, 0.25)
    premium = call_price(100.0, 100.0, 30 / 365.0, 0.05, 0.25) + \
        put_price(100.0, 100.0, 30 / 365.0, 0.05, 0.25)
    assert abs(strategy_payoff(legs, 100.0 + premium)) < 1e-6
    assert abs(strategy_payoff(legs, 100.0 - premium)) < 1e-6


def test_covered_call_capped_upside():
    legs = build_covered_call(100.0, 105.0, 0.05, 0.25, 30)
    at_strike = strategy_payoff(legs, 105.0)
    far_above = strategy_payoff(legs, 150.0)
    assert abs(at_strike - far_above) < 1e-9  # gains stop at the strike
    assert strategy_payoff(legs, 90.0) < 0  # downside still hurts


def test_iron_condor_max_profit_inside_range():
    legs = build_iron_condor(100.0, 90, 95, 105, 110, 30, 0.05, 0.25)
    inside = strategy_payoff(legs, 100.0)
    outside_low = strategy_payoff(legs, 80.0)
    outside_high = strategy_payoff(legs, 120.0)
    assert inside > 0  # net credit collected, kept if spot stays between wings
    assert outside_low < 0 and outside_high < 0
    assert abs(outside_low - outside_high) < 1e-6  # symmetric wings


def test_payoff_curve_and_extremes():
    legs = build_straddle(100.0, 30, 0.05, 0.25)
    spots = [80.0, 90.0, 100.0, 110.0, 120.0]
    curve = payoff_curve(legs, spots)
    assert len(curve) == 5
    assert max_loss(legs, spots) < 0
    assert max_gain(legs, spots) > 0
