"""GBM simulation: shape, moments, reproducibility."""

import numpy as np
import pytest

from xva_benchmark.simulation import simulate_gbm, simulate_terminal, time_grid


def test_paths_start_at_spot_and_shape():
    times = time_grid(5.0, 50)
    rng = np.random.default_rng(7)
    paths = simulate_gbm(100.0, 0.20, 0.03, times, 500, rng)
    assert paths.shape == (500, 51)
    assert np.all(paths[:, 0] == 100.0)
    assert np.all(paths > 0.0)


def test_gbm_terminal_mean_matches_lognormal():
    # E[S_T] = S0 * exp(drift * T); fixed seed, tolerance is >6 standard errors.
    rng = np.random.default_rng(11)
    terminal = simulate_terminal(100.0, 0.20, 0.03, 5.0, 20_000, rng,
                                 antithetic=False)
    expected = 100.0 * np.exp(0.03 * 5.0)
    assert terminal.mean() == pytest.approx(expected, rel=0.02)


def test_gbm_log_return_variance_matches():
    # Var[log S_T] = sigma^2 * T.
    rng = np.random.default_rng(13)
    terminal = simulate_terminal(100.0, 0.20, 0.03, 5.0, 40_000, rng,
                                 antithetic=False)
    log_var = np.log(terminal / 100.0).var(ddof=1)
    assert log_var == pytest.approx(0.20 ** 2 * 5.0, rel=0.05)


def test_reproducibility_with_fixed_seed():
    times = time_grid(2.0, 10)
    a = simulate_gbm(75.0, 0.30, 0.03, times, 200, np.random.default_rng(99))
    b = simulate_gbm(75.0, 0.30, 0.03, times, 200, np.random.default_rng(99))
    assert np.array_equal(a, b)


def test_different_seed_gives_different_paths():
    times = time_grid(2.0, 10)
    a = simulate_gbm(75.0, 0.30, 0.03, times, 200, np.random.default_rng(1))
    b = simulate_gbm(75.0, 0.30, 0.03, times, 200, np.random.default_rng(2))
    assert not np.array_equal(a, b)
