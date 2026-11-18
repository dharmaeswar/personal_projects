"""XVA: CVA / FVA / KVA signs, monotonicity, and the tolerance-band checks."""

import numpy as np
import pytest

from xva_benchmark.benchmark import check_forward_ee, check_option_price
from xva_benchmark.config import AssetClass, XVAConfig
from xva_benchmark.exposure import ExposureProfile
from xva_benchmark.xva import (default_probability_increments, xva_ladder,
                               xva_totals)


def _profile(ee_level=10_000.0, pfe_level=40_000.0):
    times = np.linspace(0.0, 5.0, 51)
    return ExposureProfile(times=times,
                           ee=np.full(51, ee_level),
                           pfe=np.full(51, pfe_level),
                           epe=ee_level)


def test_default_probability_increments_sum_to_total_pd():
    times = np.linspace(0.0, 5.0, 51)
    increments = default_probability_increments(times, hazard_rate=0.02)
    assert np.all(increments >= 0.0)
    assert increments.sum() == pytest.approx(1.0 - np.exp(-0.02 * 5.0), rel=1e-9)


def test_cva_is_zero_without_default_risk():
    totals = xva_totals(_profile(), XVAConfig(hazard_rate=0.0))
    assert totals["cva"] == 0.0


def test_cva_increases_with_hazard_rate():
    low = xva_totals(_profile(), XVAConfig(hazard_rate=0.01))["cva"]
    high = xva_totals(_profile(), XVAConfig(hazard_rate=0.05))["cva"]
    assert 0.0 < low < high


def test_cva_is_linear_in_lgd():
    half = xva_totals(_profile(), XVAConfig(lgd=0.30))["cva"]
    full = xva_totals(_profile(), XVAConfig(lgd=0.60))["cva"]
    assert full == pytest.approx(2.0 * half, rel=1e-12)


def test_fva_zero_spread_and_linearity():
    assert xva_totals(_profile(), XVAConfig(funding_spread=0.0))["fva"] == 0.0
    small = xva_totals(_profile(), XVAConfig(funding_spread=0.01))["fva"]
    large = xva_totals(_profile(), XVAConfig(funding_spread=0.02))["fva"]
    assert large == pytest.approx(2.0 * small, rel=1e-12)


def test_kva_increases_with_cost_of_capital():
    assert xva_totals(_profile(), XVAConfig(cost_of_capital=0.0))["kva"] == 0.0
    low = xva_totals(_profile(), XVAConfig(cost_of_capital=0.05))["kva"]
    high = xva_totals(_profile(), XVAConfig(cost_of_capital=0.15))["kva"]
    assert 0.0 < low < high


def test_ladder_is_cumulative_and_reaches_totals():
    profile = _profile()
    cfg = XVAConfig()
    ladder = xva_ladder(profile, cfg)
    totals = xva_totals(profile, cfg)
    cumulative = [row["cum_total_xva"] for row in ladder]
    assert cumulative == sorted(cumulative)  # non-decreasing
    assert ladder[-1]["cum_cva"] == pytest.approx(totals["cva"], rel=1e-9)
    assert ladder[-1]["cum_fva"] == pytest.approx(totals["fva"], rel=1e-9)
    assert ladder[-1]["cum_kva"] == pytest.approx(totals["kva"], rel=1e-9)


def test_benchmark_option_price_within_tolerance():
    asset = AssetClass(name="equity_index", spot=100.0, volatility=0.20)
    check = check_option_price(asset, strike=100.0, maturity=5.0, rate=0.03,
                               tolerance=0.012, n_paths=100_000, seed=10_000)
    assert check.passed, check
    assert check.relative_error <= 0.012


def test_benchmark_forward_ee_within_tolerance():
    asset = AssetClass(name="equity_index", spot=100.0, volatility=0.20)
    check = check_forward_ee(asset, strike=100.0, maturity=5.0, t_star=2.5,
                             rate=0.03, tolerance=0.012, n_paths=100_000,
                             seed=20_000)
    assert check.passed, check
    assert check.relative_error <= 0.012
