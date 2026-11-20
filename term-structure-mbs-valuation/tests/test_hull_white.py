import numpy as np
import pytest

from term_structure_mbs import HullWhiteModel, NelsonSiegelCurve, flat_curve


def _curve():
    return NelsonSiegelCurve(0.045, -0.012, -0.008, lam=1.8)


def test_bond_price_at_time_zero_matches_market_curve():
    curve = _curve()
    model = HullWhiteModel(curve, a=0.10, sigma=0.010)
    r0 = model.short_rate_at_zero()
    for T in (1.0, 5.0, 10.0, 30.0):
        assert model.bond_price(0.0, T, r0) == pytest.approx(float(curve.discount(T)), rel=1e-4)


def test_bond_price_decreases_in_short_rate():
    model = HullWhiteModel(_curve(), a=0.10, sigma=0.010)
    p_low = model.bond_price(0.0, 10.0, 0.02)
    p_high = model.bond_price(0.0, 10.0, 0.06)
    assert p_high < p_low


def test_zero_vol_paths_discount_on_the_curve():
    curve = _curve()
    model = HullWhiteModel(curve, a=0.10, sigma=0.0)
    times = np.arange(0, 61) / 12.0
    paths = model.simulate(times, n_paths=3, seed=3)
    dfs = model.path_discount_factors(times, paths)
    market = curve.discount(times)
    assert np.allclose(dfs, market, atol=2e-3)


def test_simulation_mean_discount_matches_curve():
    curve = flat_curve(0.04)
    model = HullWhiteModel(curve, a=0.15, sigma=0.012)
    times = np.arange(0, 61) / 12.0
    paths = model.simulate(times, n_paths=4000, seed=5)
    dfs = model.path_discount_factors(times, paths)
    assert dfs[:, -1].mean() == pytest.approx(float(curve.discount(5.0)), rel=0.01)


def test_simulate_rejects_bad_grid():
    model = HullWhiteModel(_curve(), a=0.10, sigma=0.010)
    with pytest.raises(ValueError):
        model.simulate(np.array([0.5, 1.0]), n_paths=2)
