import pytest

from perf.returns import (
    Flow, Valuation, time_weighted_return, modified_dietz, irr,
    geometric_excess,
)


def test_twr_no_flows():
    result = time_weighted_return(
        100.0, 110.0, [],
        [Valuation(0.0, 100.0), Valuation(1.0, 110.0)])
    assert abs(result - 0.10) < 1e-12


def test_twr_with_mid_period_flow():
    # 100 -> 110, +20 contribution, 130 -> 143: 10% then 10% = 21% chain-linked.
    result = time_weighted_return(
        100.0, 143.0, [Flow(0.5, 20.0)],
        [Valuation(0.0, 100.0), Valuation(0.5, 110.0), Valuation(1.0, 130.0)],
        start_day=0.0, end_day=1.0)
    assert abs(result - 0.21) < 1e-12


def test_twr_same_day_contribution_and_distribution():
    # 100 -> 120, +100 then -40 same day, 180 -> 150: 20% then -16.67% = 0%.
    result = time_weighted_return(
        100.0, 150.0, [Flow(0.5, 100.0), Flow(0.5, -40.0)],
        [Valuation(0.0, 100.0), Valuation(0.5, 120.0), Valuation(1.0, 150.0)],
        start_day=0.0, end_day=1.0)
    assert abs(result - 0.0) < 1e-12


def test_twr_requires_mark_on_flow_day():
    with pytest.raises(ValueError):
        time_weighted_return(
            100.0, 110.0, [Flow(0.5, 20.0)],
            [Valuation(0.0, 100.0), Valuation(1.0, 110.0)])


def test_modified_dietz_mid_period_flow():
    # (130 - 100 - 20) / (100 + 20 * 0.5) = 10 / 110.
    result = modified_dietz(100.0, 130.0, [Flow(0.5, 20.0)])
    assert abs(result - 10.0 / 110.0) < 1e-12


def test_modified_dietz_no_flows_matches_simple_return():
    result = modified_dietz(100.0, 115.0, [])
    assert abs(result - 0.15) < 1e-12


def test_irr_simple_case():
    # -100 at t=0, +110 at t=1 -> exactly 10%.
    result = irr([(0.0, -100.0), (1.0, 110.0)])
    assert abs(result - 0.10) < 1e-9


def test_irr_multi_flow_case():
    # -1000 at 0, +100 at 0.5, +1100 at 1: IRR solves NPV = 0.
    result = irr([(0.0, -1000.0), (0.5, 100.0), (1.0, 1100.0)])
    npv = (-1000.0 + 100.0 / (1 + result) ** 0.5
           + 1100.0 / (1 + result) ** 1.0)
    assert abs(npv) < 1e-6


def test_irr_rejects_unbracketed():
    with pytest.raises(ValueError):
        irr([(0.0, -100.0), (1.0, -50.0)])  # never breaks even


def test_geometric_excess():
    assert abs(geometric_excess(0.12, 0.10) - (1.12 / 1.10 - 1.0)) < 1e-12
