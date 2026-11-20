"""Prepayment model: PSA benchmark speeds scaled by a refinancing incentive.

The incentive multiplier is a capped exponential of the rate incentive
(WAC minus the prevailing mortgage rate): borrowers prepay faster when
their note rate sits above current mortgage rates, slower when it sits
below.  Speeds are capped so CPR stays in a sane range for agency pools.
"""

from __future__ import annotations

import numpy as np

MAX_CPR = 0.50
MIN_MULTIPLIER = 0.30
MAX_MULTIPLIER = 3.00
INCENTIVE_SENSITIVITY = 55.0


def cpr_to_smm(cpr: float) -> float:
    """Convert an annual conditional prepayment rate to a monthly SMM."""
    if not 0.0 <= cpr < 1.0:
        raise ValueError("CPR must be in [0, 1)")
    return 1.0 - (1.0 - cpr) ** (1.0 / 12.0)


def smm_to_cpr(smm: float) -> float:
    """Convert a monthly single monthly mortality rate to an annual CPR."""
    if not 0.0 <= smm < 1.0:
        raise ValueError("SMM must be in [0, 1)")
    return 1.0 - (1.0 - smm) ** 12


def psa_cpr(month: int, psa: float = 100.0) -> float:
    """CPR under the PSA benchmark: ramps 0.2%/month to 6% at month 30."""
    if month < 1:
        raise ValueError("month is 1-based")
    ramp = min(month, 30) * 0.002
    return ramp * (psa / 100.0)


def incentive_multiplier(wac: float, mortgage_rate: float) -> float:
    """Prepayment speed multiplier from the refinancing incentive.

    incentive = WAC - mortgage_rate (decimals).  exp(55 * incentive),
    floored at 0.30 and capped at 3.00.
    """
    incentive = wac - mortgage_rate
    mult = float(np.exp(INCENTIVE_SENSITIVITY * incentive))
    return min(max(mult, MIN_MULTIPLIER), MAX_MULTIPLIER)


def monthly_cpr(month: int, wac: float, mortgage_rate: float, psa: float = 100.0) -> float:
    """CPR for a pool month: PSA base speed times the incentive multiplier."""
    base = psa_cpr(month, psa)
    return min(base * incentive_multiplier(wac, mortgage_rate), MAX_CPR)


def monthly_smm(month: int, wac: float, mortgage_rate: float, psa: float = 100.0) -> float:
    return cpr_to_smm(monthly_cpr(month, wac, mortgage_rate, psa))
