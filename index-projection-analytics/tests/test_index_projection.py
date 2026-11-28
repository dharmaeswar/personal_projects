"""Tests for index-projection-analytics.

Every golden value below is hand-computed from the three-name test
universe: AAA 100m x $50 x 0.80 = $4,000m; BBB 200m x $25 x 0.90 =
$4,500m; CCC 50m x $100 x 1.00 = $5,000m; total $13,500m, divisor 13.5,
level 1000.
"""

import math

import pytest

from index_projection import (
    Constituent,
    IndexUniverse,
    apply_split,
    apply_cash_dividend,
    apply_spinoff,
    project_rebalance,
    project_level,
    excess_returns,
    tracking_error,
    information_ratio,
)


def test_universe():
    u = IndexUniverse(
        [
            Constituent("AAA", 100.0, 50.0, 0.80),
            Constituent("BBB", 200.0, 25.0, 0.90),
            Constituent("CCC", 50.0, 100.0, 1.00),
        ]
    )
    assert u.total_mcap() == pytest.approx(13500.0)
    assert u.divisor == pytest.approx(13.5)
    assert u.level() == pytest.approx(1000.0)
    w = u.weights()
    assert w["AAA"] == pytest.approx(4000.0 / 13500.0)
    assert w["BBB"] == pytest.approx(1.0 / 3.0)
    assert w["CCC"] == pytest.approx(5000.0 / 13500.0)


def test_split_leaves_level_unchanged():
    u = IndexUniverse(
        [
            Constituent("AAA", 100.0, 50.0, 0.80),
            Constituent("BBB", 200.0, 25.0, 0.90),
            Constituent("CCC", 50.0, 100.0, 1.00),
        ]
    )
    assert apply_split(u, "AAA", 2) == pytest.approx(1000.0)
    assert u.constituents["AAA"].shares_outstanding == pytest.approx(200.0)
    assert u.constituents["AAA"].price == pytest.approx(25.0)
    assert u.divisor == pytest.approx(13.5)


def test_cash_dividend_rescales_divisor():
    u = IndexUniverse(
        [
            Constituent("AAA", 100.0, 50.0, 0.80),
            Constituent("BBB", 200.0, 25.0, 0.90),
            Constituent("CCC", 50.0, 100.0, 1.00),
        ]
    )
    # BBB $25 -> $24: total $13,500m -> $13,320m; divisor 13.5 -> 13.32.
    assert apply_cash_dividend(u, "BBB", 1.0) == pytest.approx(1000.0)
    assert u.constituents["BBB"].price == pytest.approx(24.0)
    assert u.divisor == pytest.approx(13.32)
    assert u.total_mcap() == pytest.approx(13320.0)


def test_spinoff_keeps_level_and_adds_child():
    u = IndexUniverse(
        [
            Constituent("AAA", 100.0, 50.0, 0.80),
            Constituent("BBB", 200.0, 25.0, 0.90),
            Constituent("CCC", 50.0, 100.0, 1.00),
        ]
    )
    # CCC $100 -> $90 plus child CCCS 50m x $10 x 1.00 = $500m: total unchanged.
    assert apply_spinoff(u, "CCC", 10.0, "CCCS") == pytest.approx(1000.0)
    assert u.constituents["CCC"].price == pytest.approx(90.0)
    assert u.constituents["CCCS"].free_float_mcap == pytest.approx(500.0)
    assert u.total_mcap() == pytest.approx(13500.0)


def test_projected_rebalance():
    u = IndexUniverse(
        [
            Constituent("AAA", 100.0, 50.0, 0.80),
            Constituent("BBB", 200.0, 25.0, 0.90),
            Constituent("CCC", 50.0, 100.0, 1.00),
        ]
    )
    candidate = Constituent("DDD", 120.0, 50.0, 1.00)  # $6,000m: largest
    proj = project_rebalance(u, [candidate], target_count=3)
    assert proj.projected_tickers == ["DDD", "CCC", "BBB"]
    assert proj.additions == ["DDD"]
    assert proj.deletions == ["AAA"]
    assert proj.projected_weights["DDD"] == pytest.approx(6000.0 / 15500.0)
    # Turnover = (|0.3871-0| + |0.3226-0.3704| + |0.2903-0.3333| + |0-0.2963|) / 2
    #           = 0.7741935 / 2 = 0.3870968 (equals the incoming DDD weight).
    assert proj.turnover == pytest.approx(0.3870968, rel=1e-6)


def test_project_level_under_scenarios():
    u = IndexUniverse(
        [
            Constituent("AAA", 100.0, 50.0, 0.80),
            Constituent("BBB", 200.0, 25.0, 0.90),
            Constituent("CCC", 50.0, 100.0, 1.00),
        ]
    )
    # 4000*1.05 + 4500*0.98 + 5000*1.03 = 13,760; / 13.5 = 1019.259...
    assert project_level(u, {"AAA": 0.05, "BBB": -0.02, "CCC": 0.03}) == pytest.approx(
        13760.0 / 13.5
    )
    assert project_level(u, {}) == pytest.approx(1000.0)


def test_benchmark_analysis():
    exc = excess_returns(
        [0.001, -0.002, 0.003, 0.0, 0.001], [0.0, 0.0, 0.0, 0.0, 0.0]
    )
    assert exc == [0.001, -0.002, 0.003, 0.0, 0.001]
    # Population variance of [0.001, -0.002, 0.003, 0, 0.001] is 2.64e-6.
    assert tracking_error(exc, annualised=False) == pytest.approx(
        math.sqrt(2.64e-6), rel=1e-9
    )
    assert tracking_error(exc) == pytest.approx(math.sqrt(2.64e-6) * math.sqrt(252))
    assert information_ratio(exc) == pytest.approx(
        (0.0006 * 252) / (math.sqrt(2.64e-6) * math.sqrt(252)), rel=1e-9
    )


def test_excess_returns_length_mismatch():
    with pytest.raises(ValueError):
        excess_returns([0.01], [0.01, 0.02])
