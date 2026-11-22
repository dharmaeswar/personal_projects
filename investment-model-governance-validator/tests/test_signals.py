import numpy as np
import pytest

from investment_governance import signals


def test_pearson_ic_perfect_signal():
    s = np.arange(10, dtype=float)
    assert signals.pearson_ic(s, s) == pytest.approx(1.0)


def test_pearson_ic_inverse_signal():
    s = np.arange(10, dtype=float)
    assert signals.pearson_ic(s, -s) == pytest.approx(-1.0)


def test_pearson_ic_zero_variance_signal():
    assert signals.pearson_ic(np.ones(5), np.arange(5, dtype=float)) == 0.0


def test_pearson_ic_needs_pairs():
    with pytest.raises(ValueError):
        signals.pearson_ic([1.0, 2.0], [1.0, 2.0, 3.0])


def test_spearman_ic_monotone_but_nonlinear():
    s = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    r = np.array([1.0, 4.0, 9.0, 16.0, 25.0])
    assert signals.spearman_ic(s, r) == pytest.approx(1.0)
    assert signals.pearson_ic(s, r) < 1.0


def test_ic_decay_returns_all_horizons():
    rng = np.random.default_rng(7)
    s = rng.normal(size=200)
    fwd = {"1d": s + rng.normal(scale=2, size=200),
           "5d": s + rng.normal(scale=3, size=200)}
    out = signals.ic_decay(s, fwd)
    assert set(out) == {"1d", "5d"}
    assert out["1d"] > out["5d"]


def test_signal_turnover_no_change():
    assert signals.signal_turnover([0.5, 0.5], [0.5, 0.5]) == 0.0


def test_signal_turnover_full_rotation():
    assert signals.signal_turnover([0.0, 1.0], [1.0, 0.0]) == pytest.approx(1.0)


def test_signal_turnover_shape_mismatch():
    with pytest.raises(ValueError):
        signals.signal_turnover([0.5, 0.5], [1.0])


def test_hit_rate_perfect():
    assert signals.hit_rate([1, -1, 2], [0.5, -0.3, 1.0]) == pytest.approx(1.0)


def test_hit_rate_random_is_near_half():
    rng = np.random.default_rng(3)
    s = rng.normal(size=2000)
    r = rng.normal(size=2000)
    assert signals.hit_rate(s, r) == pytest.approx(0.5, abs=0.05)


def test_information_ratio_positive_for_stable_ic():
    assert signals.information_ratio([0.05] * 12) == 0.0  # zero variance
    assert signals.information_ratio([0.04, 0.06, 0.05, 0.05]) > 0
