"""Golden-value regression tests for the gross-to-net fee bridge."""

import pytest

from perf.fees import FeeTerms, gross_to_net


def test_gross_to_net_hand_computed():
    # NAV 1000, gross gain 120, fee 2% of NAV = 20, hurdle 8% = 80,
    # carry base 120 - 80 = 40, carry 20% = 8, net = 120 - 20 - 8 = 92.
    bridge = gross_to_net(1000.0, 120.0,
                          FeeTerms(management_fee_rate=0.02, carry_rate=0.20,
                                   hurdle_rate=0.08))
    assert bridge["management_fee"] == pytest.approx(20.0)
    assert bridge["carry"] == pytest.approx(8.0)
    assert bridge["net_gain"] == pytest.approx(92.0)
    assert bridge["gross_return"] == pytest.approx(0.12)
    assert bridge["net_return"] == pytest.approx(0.092)
    assert bridge["residual"] == pytest.approx(0.0, abs=1e-12)


def test_no_carry_below_hurdle():
    # Gross gain 50 is below the 8% hurdle on 1000 NAV, so carry is zero.
    bridge = gross_to_net(1000.0, 50.0,
                          FeeTerms(management_fee_rate=0.02, carry_rate=0.20,
                                   hurdle_rate=0.08))
    assert bridge["carry"] == pytest.approx(0.0)
    assert bridge["net_gain"] == pytest.approx(30.0)


def test_negative_gain_still_bridges():
    bridge = gross_to_net(1000.0, -40.0,
                          FeeTerms(management_fee_rate=0.02, carry_rate=0.20,
                                   hurdle_rate=0.08))
    assert bridge["carry"] == pytest.approx(0.0)
    assert bridge["net_gain"] == pytest.approx(-60.0)
    assert bridge["residual"] == pytest.approx(0.0, abs=1e-12)


def test_negative_nav_rejected():
    with pytest.raises(ValueError):
        gross_to_net(-100.0, 10.0,
                     FeeTerms(management_fee_rate=0.02, carry_rate=0.20,
                              hurdle_rate=0.08))
