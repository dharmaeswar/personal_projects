"""Gross-to-net computation: fee and carry leg selection.

Gross gain is split into legs the investor can audit: management fee
(a rate on NAV), carry (a share of gain above a hurdle rate), and the
net gain that remains. The bridge always explains: gross - fee - carry
= net, with no unexplained residual.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class FeeTerms:
    management_fee_rate: float  # per period, on beginning NAV
    carry_rate: float           # share of gain above the hurdle
    hurdle_rate: float          # per period; carry only above this


def gross_to_net(beginning_nav, gross_gain, terms):
    """Return a bridge dict for one period.

    gross_gain is the period's total gain (income + appreciation) before
    fees. Carry applies only to the gain above hurdle_rate * NAV.
    """
    if beginning_nav < 0:
        raise ValueError("beginning NAV must not be negative")
    management_fee = terms.management_fee_rate * beginning_nav
    hurdle_gain = terms.hurdle_rate * beginning_nav
    carry_base = max(0.0, gross_gain - hurdle_gain)
    carry = terms.carry_rate * carry_base
    net_gain = gross_gain - management_fee - carry
    return {
        "beginning_nav": beginning_nav,
        "gross_gain": gross_gain,
        "gross_return": gross_gain / beginning_nav if beginning_nav else 0.0,
        "management_fee": management_fee,
        "carry": carry,
        "net_gain": net_gain,
        "net_return": net_gain / beginning_nav if beginning_nav else 0.0,
        "residual": gross_gain - management_fee - carry - net_gain,
    }
