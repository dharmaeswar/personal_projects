"""Golden-vector and invariant tests for public-market equivalents.

Golden values are hand-computed, not fitted to the implementation.
Index levels are in the same units throughout; all money is Decimal.

- KS-PME: contribution 100 at t=0, distribution 121 at t=1, index
  100 -> 110. Discounted distribution = 121 * 100/110 = 110, so
  KS-PME = 110 / 100 = 1.10 exactly.
- Direct Alpha: flows -100 at t=0, +121 at t=1, index 100 -> 110.
  Adjusted NPV = -100 + 121 / (1.1 * (1 + alpha)) = 0 gives
  1 + alpha = 121/110 = 1.1, so alpha = 0.10 exactly.
- Long-Nickels: contribution 100 at t=0, distribution 121 at t=1,
  index 100, 110, 121 at t=0, 1, 2, end day 2. Future values:
  100 * 121/100 = 121 and 121 * 121/110 = 133.1, so LN-PME =
  133.1 / 121 = 1.10 exactly.
"""

import pytest
from decimal import Decimal

from perf.pme import ks_pme, direct_alpha, long_nickels_pme, discounted_weights

D = Decimal


def test_ks_pme_golden():
    result = ks_pme([(D(0), D(100)), (D(1), D(-121))],
                    {D(0): D(100), D(1): D(110)})
    assert result == D("1.1")


def test_direct_alpha_golden():
    alpha, diag = direct_alpha([(D(0), D(-100)), (D(1), D(121))],
                               {D(0): D(100), D(1): D(110)})
    assert abs(alpha - D("0.1")) < D("1e-15")
    assert diag["multiple_roots"] is False


def test_long_nickels_pme_golden():
    result = long_nickels_pme(
        [(D(0), D(100)), (D(1), D(-121))],
        {D(0): D(100), D(1): D(110), D(2): D(121)}, end_day=D(2))
    assert result == D("1.1")


def test_ks_pme_date_shift_invariant():
    # Moving the distribution from day 1 to day 2 while the index
    # level on its new day is the same (110) must not change KS-PME:
    # only the index ratio I_t / I_0 matters, not the calendar day.
    base = ks_pme([(D(0), D(100)), (D(1), D(-121))],
                  {D(0): D(100), D(1): D(110)})
    shifted = ks_pme([(D(0), D(100)), (D(2), D(-121))],
                     {D(0): D(100), D(2): D(110)})
    assert base == shifted == D("1.1")


def test_ks_pme_netting_invariant():
    # Two same-day distributions net to one flow with the same KS-PME.
    split = ks_pme([(D(0), D(100)), (D(1), D(-60)), (D(1), D(-61))],
                   {D(0): D(100), D(1): D(110)})
    netted = ks_pme([(D(0), D(100)), (D(1), D(-121))],
                    {D(0): D(100), D(1): D(110)})
    assert split == netted == D("1.1")


def test_discounted_weights_sum_to_one():
    weights = discounted_weights(
        [(D(0), D(100)), (D(1), D(-121))],
        {D(0): D(100), D(1): D(110)})
    assert sum(w for _, w in weights) == D(1)


def test_ks_pme_monotonic_in_distribution():
    index = {D(0): D(100), D(1): D(110)}
    small = ks_pme([(D(0), D(100)), (D(1), D(-110))], index)
    large = ks_pme([(D(0), D(100)), (D(1), D(-121))], index)
    assert small < large
    assert small == D(1)  # 110 * 100/110 = 100, so KS = 1 exactly


def test_pme_rejects_float_money():
    with pytest.raises(TypeError):
        ks_pme([(0, 100.0), (1, -121.0)], {0: 100, 1: 110})


def test_pme_requires_index_level_for_every_flow_day():
    with pytest.raises(ValueError, match="no index level"):
        ks_pme([(D(0), D(100)), (D(1), D(-121))], {D(0): D(100)})
