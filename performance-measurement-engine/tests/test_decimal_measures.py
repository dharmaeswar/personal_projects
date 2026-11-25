"""Tests for Decimal time-weighted measures.

Golden values are hand-computed, not fitted to the implementation:
- Modified Dietz: (130 - 100 - 20) / (100 + 20 * 0.5) = 10 / 110.
- Chained index: 100 * 1.1 * 1.1 = 121.
- Unitised: (121000 / 1100) / (100000 / 1000) - 1 = 110/100 - 1 = 10%.
"""

import pytest
from decimal import Decimal

from perf.decimal_measures import (
    decimal_modified_dietz, chained_index, unitised_return,
)

D = Decimal


def test_decimal_modified_dietz_golden():
    result = decimal_modified_dietz("100", "130", [("0.5", "20")])
    assert result == D("10") / D("110")
    assert abs(result - D("0.09090909090909090909090909091")) < D("1e-25")


def test_decimal_modified_dietz_no_flows():
    assert decimal_modified_dietz("100", "115", []) == D("0.15")


def test_decimal_modified_dietz_same_day_split_nets():
    split = decimal_modified_dietz("100", "130", [("0.5", "12"), ("0.5", "8")])
    netted = decimal_modified_dietz("100", "130", [("0.5", "20")])
    assert split == netted


def test_decimal_modified_dietz_rejects_floats():
    with pytest.raises(TypeError):
        decimal_modified_dietz(100.0, 130.0, [(0.5, 20.0)])


def test_chained_index_golden():
    levels = chained_index(["0.1", "0.1"])
    assert levels == [D("100"), D("110"), D("121")]


def test_chained_index_reproduces_from_returns():
    returns = ["0.05", "-0.02", "0.08"]
    levels = chained_index(returns)
    assert levels[0] == D("100")
    assert levels[-1] == D("100") * D("1.05") * D("0.98") * D("1.08")


def test_unitised_return_golden():
    result = unitised_return("1000", "1100", "100000", "121000")
    assert result == D("0.1")


def test_unitised_return_no_flow_change():
    # Same unit count, NAV up 5%: per-unit return is 5%.
    assert unitised_return("1000", "1000", "100000", "105000") == D("0.05")
