"""Tests for TOB / VMTP leverage and funding risk."""

import pytest

from muni_engine import (
    TobStructure, funding_shock_scenarios, leverage_risk_summary, vmtp_cost,
)


def _tob():
    # 100 par underlying at 4.5%, 75 par floaters at 3.0%,
    # 10bp liquidity + 5bp remarketing fees.
    return TobStructure(underlying_par=100.0, floater_par=75.0,
                        underlying_yield=0.045, floater_rate=0.030,
                        liquidity_fee_bps=10.0, remarketing_fee_bps=5.0)


def test_residual_par_and_leverage():
    tob = _tob()
    assert tob.residual_par == 25.0
    assert tob.leverage_ratio == 4.0


def test_funding_cost_includes_fees():
    # 75 * 3.0% = 2.25 remarketing + 75 * 15bp = 0.1125 fees
    assert _tob().funding_cost_annual() == pytest.approx(2.3625)


def test_residual_income_and_yield():
    tob = _tob()
    assert tob.residual_income_annual() == pytest.approx(2.1375)
    assert tob.residual_yield() == pytest.approx(0.0855)


def test_distribution_coverage():
    # 2.1375 income vs 1.50 target distribution
    assert _tob().distribution_coverage(1.50) == pytest.approx(1.425)


def test_distribution_coverage_bad_target_raises():
    with pytest.raises(ValueError):
        _tob().distribution_coverage(0.0)


def test_funding_shock_plus_100bp():
    scenarios = funding_shock_scenarios(_tob(), 1.50)
    plus_100 = scenarios[100]
    # floater 4.0%: funding 3.0 + 0.1125 = 3.1125; income 1.3875
    assert plus_100["floater_rate_pct"] == 4.0
    assert plus_100["funding_cost"] == pytest.approx(3.1125)
    assert plus_100["residual_yield_pct"] == pytest.approx(5.55)
    assert plus_100["distribution_coverage"] == pytest.approx(0.925)


def test_funding_shock_minus_50bp():
    scenarios = funding_shock_scenarios(_tob(), 1.50)
    assert scenarios[-50]["residual_yield_pct"] == pytest.approx(10.05)
    assert scenarios[-50]["distribution_coverage"] == pytest.approx(1.675)


def test_funding_shock_plus_200bp_erodes_distribution():
    scenarios = funding_shock_scenarios(_tob(), 1.50)
    # floater 5.0%: funding 3.8625; income 0.6375; coverage 0.425
    assert scenarios[200]["distribution_coverage"] == pytest.approx(0.425)


def test_vmtp_cost():
    # 50 par at 3.2% dividend + 25bp remarketing spread
    cost = vmtp_cost(50.0, 0.032, remarketing_spread_bps=25.0)
    assert cost["annual_cost"] == pytest.approx(1.725)
    assert cost["cost_per_100_par"] == pytest.approx(3.45)


def test_vmtp_cost_no_spread():
    cost = vmtp_cost(100.0, 0.03)
    assert cost["annual_cost"] == pytest.approx(3.0)


def test_leverage_risk_summary_funding_stress():
    summary = leverage_risk_summary(_tob(), 1.50)
    assert summary["leverage_ratio"] == 4.0
    assert summary["residual_yield_pct"] == pytest.approx(8.55)
    assert summary["coverage_at_plus_100bp"] == pytest.approx(0.925)
    assert summary["verdict"] == "FUNDING STRESS"


def test_leverage_risk_summary_covered():
    summary = leverage_risk_summary(_tob(), 1.00)
    assert summary["verdict"] == "COVERED AT +100BP"


def test_floater_must_be_below_underlying():
    with pytest.raises(ValueError):
        TobStructure(underlying_par=100.0, floater_par=100.0,
                     underlying_yield=0.045, floater_rate=0.030)


def test_negative_rate_raises():
    with pytest.raises(ValueError):
        TobStructure(underlying_par=100.0, floater_par=75.0,
                     underlying_yield=0.045, floater_rate=-0.01)
