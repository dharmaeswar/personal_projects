import numpy as np
import pytest

from term_structure_mbs import NelsonSiegelCurve, fit_nelson_siegel, flat_curve

MAT = np.array([0.25, 0.5, 1, 2, 3, 5, 7, 10, 20, 30], dtype=float)


def test_fit_recovers_known_nelson_siegel_curve():
    truth = NelsonSiegelCurve(0.045, -0.012, -0.008, lam=1.8)
    yields = truth.zero_rate(MAT)
    fitted, rmse = fit_nelson_siegel(MAT, yields)
    assert rmse < 2e-4
    assert np.allclose(fitted.zero_rate(MAT), yields, atol=5e-4)


def test_discount_factor_properties():
    curve, _ = fit_nelson_siegel(MAT, np.array(
        [0.052, 0.051, 0.049, 0.046, 0.044, 0.0425, 0.0425, 0.0435, 0.046, 0.0455]))
    assert float(curve.discount(0.0)) == pytest.approx(1.0)
    dfs = curve.discount(np.array([1.0, 5.0, 10.0, 30.0]))
    assert np.all(np.diff(dfs) < 0)  # positive rates -> decreasing discounts
    assert np.all((dfs > 0) & (dfs < 1))


def test_flat_curve_forward_equals_rate():
    curve = flat_curve(0.04)
    assert curve.forward(2.0, 7.0) == pytest.approx(0.04)
    assert float(curve.instantaneous_forward(3.0)) == pytest.approx(0.04, abs=1e-6)


def test_bumped_curve_shifts_rates():
    curve = flat_curve(0.04)
    up = curve.bumped(0.01)
    assert float(up.zero_rate(5.0)) == pytest.approx(0.05)
    assert float(curve.zero_rate(5.0)) == pytest.approx(0.04)  # original untouched


def test_svensson_fit_on_humped_yields():
    truth = NelsonSiegelCurve(0.045, -0.010, 0.006, lam=1.2, beta3=0.010, lam2=6.0)
    yields = truth.zero_rate(MAT)
    fitted, rmse = fit_nelson_siegel(MAT, yields, svensson=True)
    assert rmse < 5e-4
