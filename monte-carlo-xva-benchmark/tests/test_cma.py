"""Capital market assumptions and private-market stochastic projection."""

import numpy as np
import pytest

from xva_benchmark.cma import (
    bayesian_posterior_mean,
    building_block_expected_return,
    cma_from_history,
    project_cash_flows,
    shrinkage_correlation,
    simulate_private_nav,
    tail_risk,
)
from xva_benchmark.simulation import time_grid


def test_building_block_return_is_additive():
    assert building_block_expected_return(0.02, 0.025, 0.015, 0.04) == pytest.approx(0.10)
    assert building_block_expected_return(0.0, 0.0, 0.0, 0.0) == pytest.approx(0.0)


def test_bayesian_posterior_between_prior_and_sample():
    post_mean, post_var = bayesian_posterior_mean(
        prior_mean=0.05, prior_var=0.02 ** 2,
        sample_mean=0.09, sample_var=0.15 ** 2, n_obs=60)
    assert 0.05 < post_mean < 0.09
    assert post_var < 0.02 ** 2
    assert post_var < 0.15 ** 2 / 60


def test_bayesian_more_data_moves_toward_sample():
    near_prior, _ = bayesian_posterior_mean(0.05, 0.02 ** 2, 0.09, 0.15 ** 2, 5)
    near_sample, _ = bayesian_posterior_mean(0.05, 0.02 ** 2, 0.09, 0.15 ** 2, 600)
    assert abs(near_sample - 0.09) < abs(near_prior - 0.09)
    assert abs(near_prior - 0.05) < abs(near_sample - 0.05)


def test_bayesian_rejects_bad_inputs():
    with pytest.raises(ValueError):
        bayesian_posterior_mean(0.05, 0.02 ** 2, 0.09, 0.15 ** 2, 0)
    with pytest.raises(ValueError):
        bayesian_posterior_mean(0.05, -1.0, 0.09, 0.15 ** 2, 60)


def test_shrinkage_keeps_unit_diagonal_and_moves_toward_target():
    rng = np.random.default_rng(3)
    x = rng.standard_normal((200, 3))
    sample = np.corrcoef(x, rowvar=False)
    shrunk = shrinkage_correlation(sample, shrinkage=0.5, target="identity")
    assert np.allclose(np.diag(shrunk), 1.0)
    assert np.allclose(shrunk, 0.5 * sample + 0.5 * np.eye(3))
    # Shrunk off-diagonals are closer to zero (the identity target) than raw.
    assert np.abs(shrunk[0, 1]) < np.abs(sample[0, 1]) or sample[0, 1] == 0.0


def test_shrinkage_constant_target_uses_average_correlation():
    sample = np.array([[1.0, 0.6, 0.3],
                       [0.6, 1.0, 0.4],
                       [0.3, 0.4, 1.0]])
    shrunk = shrinkage_correlation(sample, shrinkage=1.0, target="constant")
    avg = (0.6 + 0.3 + 0.4) / 3.0
    assert shrunk[0, 1] == pytest.approx(avg)
    assert shrunk[0, 2] == pytest.approx(avg)
    assert np.allclose(np.diag(shrunk), 1.0)


def test_cma_from_history_shapes_and_psd_covariance():
    rng = np.random.default_rng(5)
    returns = rng.normal(loc=[0.006, 0.004], scale=[0.04, 0.03],
                         size=(120, 2))
    cma = cma_from_history(returns, prior_means=[0.05 / 12, 0.04 / 12],
                           prior_vols=[0.01, 0.01], shrinkage=0.25)
    assert cma["expected_returns"].shape == (2,)
    assert cma["correlation"].shape == (2, 2)
    assert cma["covariance"].shape == (2, 2)
    assert np.allclose(np.diag(cma["correlation"]), 1.0)
    eig = np.linalg.eigvalsh(cma["covariance"])
    assert np.all(eig >= -1e-12)
    # Posterior means sit between prior and sample means.
    assert np.all(cma["expected_returns"] > np.minimum([0.05 / 12, 0.04 / 12],
                                                        returns.mean(axis=0)) - 1e-12)


def test_private_nav_shape_positive_and_reproducible():
    times = time_grid(5.0, 10)
    a = project_cash_flows(100.0, 0.08, 0.15, times, 500, seed=7)
    b = project_cash_flows(100.0, 0.08, 0.15, times, 500, seed=7)
    assert a["nav"].shape == (500, 11)
    assert np.all(a["nav"][:, 0] == 100.0)
    assert np.all(a["nav"] >= 0.0)
    assert np.array_equal(a["nav"], b["nav"])


def test_private_nav_calls_raise_and_distributions_lower_nav():
    times = time_grid(5.0, 5)
    base = project_cash_flows(100.0, 0.0, 0.0, times, 50, seed=1)
    assert np.allclose(base["nav"][:, -1], 100.0)
    called = project_cash_flows(100.0, 0.0, 0.0, times, 50, seed=1,
                                capital_calls={3: 20.0})
    assert np.allclose(called["nav"][:, -1], 120.0)
    assert called["total_calls"] == pytest.approx(20.0)
    assert np.allclose(called["net_cash_flow"][:, 3], -20.0)
    paid = project_cash_flows(100.0, 0.0, 0.0, times, 50, seed=1,
                              capital_calls={3: 20.0},
                              distributions={5: 30.0})
    assert np.allclose(paid["nav"][:, -1], 90.0)
    assert np.allclose(paid["net_cash_flow"][:, 5], 30.0)
    # A distribution can never take NAV below zero.
    drained = project_cash_flows(100.0, 0.0, 0.0, times, 50, seed=1,
                                 distributions={5: 500.0})
    assert np.allclose(drained["nav"][:, -1], 0.0)
    assert np.allclose(drained["net_cash_flow"][:, 5], 100.0)


def test_private_nav_terminal_mean_matches_gbm():
    times = time_grid(5.0, 50)
    out = project_cash_flows(100.0, 0.08, 0.15, times, 20_000, seed=9)
    expected = 100.0 * np.exp(0.08 * 5.0)
    assert out["nav"][:, -1].mean() == pytest.approx(expected, rel=0.02)


def test_tail_risk_ordering_and_determinism():
    rng = np.random.default_rng(4)
    terminal = rng.normal(loc=100.0, scale=15.0, size=20_000)
    risk = tail_risk(terminal, confidence=0.95)
    assert risk["cvar"] >= risk["var"] >= 0.0
    assert risk["mean_value"] == pytest.approx(100.0, rel=0.02)
    # A tighter distribution has smaller tail risk than a wider one.
    narrow = tail_risk(rng.normal(loc=100.0, scale=2.0, size=20_000))
    assert narrow["var"] < risk["var"]
    with pytest.raises(ValueError):
        tail_risk([])
