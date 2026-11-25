"""Golden-vector and invariant tests for the exact-decimal solver.

Golden values are hand-computed, not fitted to the implementation:
- IRR of -100 at t=0, +110 at t=1 is exactly 10%.
- IRR of -1000 at t=0, +100 at t=0.5, +1100 at t=1 is exactly 21%:
  -1000 + 100/sqrt(1.21) + 1100/1.21 = -1000 + 100/1.1 + 909.0909... = 0.
- The multiple-root case -100, +250, -150 has NPV zero at r = 0 and
  r = 0.5 (substitute x = 1/(1+r): -100 + 250x - 150x^2 = 0 gives
  x = 1 and x = 2/3).
"""

import pytest
from decimal import Decimal

from perf.decimal_solver import (
    money, canonical_sum, decimal_npv, solve_irr_decimal,
)


def test_money_rejects_floats():
    with pytest.raises(TypeError):
        money(0.1)
    assert money("0.1") == Decimal("0.1")
    assert money(100) == Decimal(100)
    assert money(Decimal("3.5")) == Decimal("3.5")


def test_canonical_sum_order_independent():
    flows = [(Decimal(1), Decimal("10.5")), (Decimal(0), Decimal("-3.25")),
             (Decimal(1), Decimal("2.75"))]
    assert canonical_sum(flows) == canonical_sum(list(reversed(flows)))
    assert canonical_sum(flows) == Decimal("10.0")


def test_decimal_npv_exact_at_known_root():
    # -100 + 110/1.1 = 0 exactly in decimal arithmetic.
    flows = [(Decimal(0), Decimal(-100)), (Decimal(1), Decimal(110))]
    assert decimal_npv(flows, Decimal("0.1")) == Decimal(0)


def test_irr_simple_case_exact():
    rate, diag = solve_irr_decimal(
        [(Decimal(0), Decimal(-100)), (Decimal(1), Decimal(110))])
    assert rate == Decimal("0.1")
    assert diag["residual"] == 0
    assert diag["ill_conditioned"] is False
    assert diag["multiple_roots"] is False


def test_irr_multi_flow_case_exact():
    rate, diag = solve_irr_decimal([
        (Decimal(0), Decimal(-1000)), (Decimal("0.5"), Decimal(100)),
        (Decimal(1), Decimal(1100))])
    assert abs(rate - Decimal("0.21")) < Decimal("1e-15")
    assert abs(decimal_npv(
        [(Decimal(0), Decimal(-1000)), (Decimal("0.5"), Decimal(100)),
         (Decimal(1), Decimal(1100))], rate)) < Decimal("1e-12")


def test_irr_rejects_unbracketed():
    with pytest.raises(ValueError, match="not bracketed"):
        solve_irr_decimal([(Decimal(0), Decimal(-100)),
                           (Decimal(1), Decimal(-50))])


def test_irr_flags_multiple_roots():
    # NPV is zero at r = 0 and r = 0.5; the solver must say so.
    rate, diag = solve_irr_decimal([
        (Decimal(0), Decimal(-100)), (Decimal(1), Decimal(250)),
        (Decimal(2), Decimal(-150))])
    assert diag["multiple_roots"] is True
    assert abs(rate - Decimal(0)) < Decimal("1e-12") or \
        abs(rate - Decimal("0.5")) < Decimal("1e-12")
    assert abs(decimal_npv(
        [(Decimal(0), Decimal(-100)), (Decimal(1), Decimal(250)),
         (Decimal(2), Decimal(-150))], rate)) < Decimal("1e-12")


def test_irr_rejects_float_amounts():
    with pytest.raises(TypeError):
        solve_irr_decimal([(0, -100.0), (1, 110.0)])
