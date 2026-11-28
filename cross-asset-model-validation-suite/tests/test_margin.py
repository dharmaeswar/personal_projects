"""Tests for the clearing margin / stress testing / backtesting module.

Every golden value below is hand-computed from the input sample, not
copied from the implementation:

* The 10-observation loss sample, sorted ascending, is
  [-0.04, -0.03, -0.02, -0.01, 0.00, 0.01, 0.02, 0.03, 0.04, 0.05].
  VaR is the ceil(c*n)-th smallest loss, so VaR(90%) is the 9th value,
  0.04, and ES(90%) is the mean of the losses at or above it,
  (0.04 + 0.05) / 2 = 0.045. VaR(99%) is the 10th value, 0.05.
* Normal 99% VaR with mean 0 and std 0.02 is 0.02 * 2.3263478740408408
  = 0.046526957480816816 (NormalDist 99% quantile, standard value).
* Kupiec LR with 0 breaches in 250 days at p = 0.01 is the closed form
  -2 * 250 * ln(0.99) = 5.0251679...
* Stress P&L: delta 100,000 on A with shock -0.02 gives -2,000;
  delta -50,000 on B with shock +0.03 gives -1,500; total -3,500.
"""

import math

import pytest

from model_validation_suite.margin import (
    backtest_breaches,
    cornish_fisher_var,
    historical_expected_shortfall,
    historical_var,
    kupiec_pof_lr,
    kupiec_pof_pvalue,
    margin_report,
    margin_requirement,
    parametric_var,
    portfolio_losses,
    stress_pnl,
    worst_stress_loss,
)

RETURNS_10 = [-0.05, -0.04, -0.03, -0.02, -0.01, 0.0, 0.01, 0.02, 0.03, 0.04]
# These are RETURNS (negative = loss). Losses are their negation:
# sorted losses = [-0.04, ..., 0.05]; see the module docstring above.


def _loss_sample():
    return [-r for r in RETURNS_10]


def test_historical_var_order_statistic():
    losses = _loss_sample()
    assert historical_var(losses, 0.90) == pytest.approx(0.04)
    assert historical_var(losses, 0.99) == pytest.approx(0.05)
    assert historical_var(losses, 0.50) == pytest.approx(0.00)


def test_historical_expected_shortfall():
    losses = _loss_sample()
    assert historical_expected_shortfall(losses, 0.90) == pytest.approx(0.045)
    assert historical_expected_shortfall(losses, 0.99) == pytest.approx(0.05)


def test_historical_var_rejects_bad_confidence():
    with pytest.raises(ValueError):
        historical_var(_loss_sample(), 1.0)
    with pytest.raises(ValueError):
        historical_var([], 0.99)


def test_parametric_var_normal():
    assert parametric_var(0.0, 0.02, 0.99) == pytest.approx(0.046526957480816816)
    assert parametric_var(0.01, 0.02, 0.95) == pytest.approx(0.01 + 0.02 * 1.6448536269514722)


def test_cornish_fisher_reduces_to_normal_without_skew_or_kurtosis():
    assert cornish_fisher_var(0.0, 0.02, 0.0, 0.0, 0.99) == pytest.approx(
        parametric_var(0.0, 0.02, 0.99)
    )


def test_cornish_fisher_fat_tails_raise_var():
    base = parametric_var(0.0, 0.02, 0.99)
    fat = cornish_fisher_var(0.0, 0.02, 0.0, 3.0, 0.99)
    assert fat > base


def test_portfolio_losses_weighted_sum():
    returns_matrix = [
        [0.01, -0.02],   # pnl = 0.5*0.01 + 0.5*(-0.02) = -0.005 -> loss 0.005
        [-0.04, 0.02],   # pnl = 0.5*(-0.04) + 0.5*0.02 = -0.01 -> loss 0.01
        [0.02, 0.02],    # pnl = 0.02 -> loss -0.02
    ]
    assert portfolio_losses(returns_matrix, [0.5, 0.5]) == pytest.approx(
        [0.005, 0.01, -0.02]
    )


def test_portfolio_losses_rejects_mismatched_row():
    with pytest.raises(ValueError):
        portfolio_losses([[0.01]], [0.5, 0.5])


def test_stress_pnl_hand_computed():
    positions = [
        {"underlying": "SPX", "delta": 100_000.0},
        {"underlying": "CL", "delta": -50_000.0},
    ]
    assert stress_pnl(positions, {"SPX": -0.02, "CL": 0.03}) == pytest.approx(-3_500.0)
    # Unshocked underlyings contribute zero.
    assert stress_pnl(positions, {"SPX": -0.02}) == pytest.approx(-2_000.0)


def test_worst_stress_loss_picks_worst_scenario():
    positions = [
        {"underlying": "SPX", "delta": 100_000.0},
        {"underlying": "CL", "delta": -50_000.0},
    ]
    scenarios = [
        {"SPX": -0.02, "CL": 0.03},   # loss 3,500
        {"SPX": 0.05, "CL": -0.10},   # pnl 5,000 + 5,000 = 10,000 -> loss -10,000
        {"SPX": -0.10, "CL": 0.0},    # loss 10,000
    ]
    loss, index = worst_stress_loss(positions, scenarios)
    assert loss == pytest.approx(10_000.0)
    assert index == 2


def test_margin_requirement_is_max_of_legs():
    assert margin_requirement(100.0, 80.0, floor=50.0) == 100.0
    assert margin_requirement(100.0, 150.0, floor=50.0) == 150.0
    assert margin_requirement(10.0, 20.0, floor=30.0) == 30.0


def test_backtest_breaches_counts_strict_exceedances():
    losses = [0.01, 0.05, 0.03, 0.06]
    var_series = [0.04, 0.04, 0.04, 0.04]
    assert backtest_breaches(losses, var_series) == 2
    # A loss exactly equal to VaR is not a breach.
    assert backtest_breaches([0.04], [0.04]) == 0


def test_kupiec_zero_breaches_closed_form():
    lr = kupiec_pof_lr(0, 250, 0.01)
    assert lr == pytest.approx(-2.0 * 250 * math.log(0.99), abs=1e-9)
    assert lr == pytest.approx(5.0251679, abs=1e-6)


def test_kupiec_pvalue_zero_breaches():
    p = kupiec_pof_pvalue(0, 250, 0.01)
    assert 0.02 < p < 0.03


def test_kupiec_perfect_calibration_is_small():
    # 2 or 3 breaches in 250 days at p = 0.01 is close to expected (2.5).
    assert kupiec_pof_lr(2, 250, 0.01) < 1.0
    assert kupiec_pof_lr(3, 250, 0.01) < 1.0
    # 10 breaches is far off and must reject hard.
    assert kupiec_pof_lr(10, 250, 0.01) > 10.0


def test_margin_report_integration():
    losses = _loss_sample()
    positions = [{"underlying": "SPX", "delta": 100_000.0}]
    scenarios = [{"SPX": -0.02}, {"SPX": -0.06}]
    report = margin_report(losses, positions, scenarios, confidence=0.90, floor=0.0)
    assert report["var"] == pytest.approx(0.04)
    assert report["expected_shortfall"] == pytest.approx(0.045)
    assert report["worst_stress_loss"] == pytest.approx(6_000.0)
    assert report["worst_scenario"] == 1
    assert report["margin"] == pytest.approx(6_000.0)
