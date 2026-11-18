"""Exposure engine: exact checks on synthetic values plus profile properties."""

import numpy as np
import pytest

from xva_benchmark.exposure import compute_exposure, trapezoid_average


def test_exposure_on_constant_values_is_exact():
    times = np.array([0.0, 1.0, 2.0])
    values = np.full((4, 3), 10.0)
    profile = compute_exposure(values, times, rate=0.0, pfe_quantile=0.975)
    assert np.allclose(profile.ee, 10.0)
    assert np.allclose(profile.pfe, 10.0)
    assert profile.epe == pytest.approx(10.0)


def test_exposure_floors_negative_values_at_zero():
    times = np.array([0.0, 1.0])
    values = np.array([[-5.0, -5.0], [5.0, 5.0]])
    profile = compute_exposure(values, times, rate=0.0)
    assert np.allclose(profile.ee, [2.5, 2.5])
    assert np.all(profile.ee >= 0.0)
    assert np.all(profile.pfe >= 0.0)


def test_exposure_applies_discounting():
    times = np.array([0.0, 1.0])
    values = np.full((3, 2), 100.0)
    profile = compute_exposure(values, times, rate=0.05)
    assert profile.ee[0] == pytest.approx(100.0)
    assert profile.ee[1] == pytest.approx(100.0 * np.exp(-0.05), rel=1e-12)


def test_pfe_is_monotonic_in_quantile():
    rng = np.random.default_rng(3)
    times = np.array([0.0, 1.0, 2.0])
    values = rng.normal(5.0, 20.0, size=(2_000, 3))
    low = compute_exposure(values, times, 0.03, pfe_quantile=0.50)
    high = compute_exposure(values, times, 0.03, pfe_quantile=0.975)
    assert np.all(high.pfe >= low.pfe)


def test_epe_lies_within_ee_range():
    rng = np.random.default_rng(5)
    times = np.linspace(0.0, 5.0, 11)
    values = rng.normal(0.0, 30.0, size=(1_000, 11)) + np.linspace(0, 40, 11)
    profile = compute_exposure(values, times, 0.03)
    assert profile.ee.min() <= profile.epe <= profile.ee.max()
    assert trapezoid_average(profile.ee, times) == pytest.approx(profile.epe)
