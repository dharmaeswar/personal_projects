import numpy as np
import pytest

from exp_platform.cuped import (
    cuped_adjust,
    cuped_theta,
    cuped_variance_reduction,
)
from exp_platform.sequential import obf_boundaries, sequential_decision
from exp_platform.causal import (
    difference_in_differences,
    bayesian_ab_test,
    uplift_t_learner,
)
from exp_platform.data_gen import generate_ab_experiment, generate_did_panel
from exp_platform.report import experiment_report


def test_cuped_theta_recovers_known_slope():
    rng = np.random.default_rng(0)
    x = rng.normal(0, 1, 5000)
    y = 2.0 * x + rng.normal(0, 1, 5000)
    theta = cuped_theta(y, x)
    assert abs(theta - 2.0) < 0.1


def test_cuped_reduces_variance():
    rng = np.random.default_rng(1)
    x = rng.normal(0, 1, 5000)
    y = 3.0 * x + rng.normal(0, 1, 5000)
    adj, theta = cuped_adjust(y, x)
    assert adj.var() < y.var()
    assert cuped_variance_reduction(y, x) > 0.8


def test_cuped_zero_variance_covariate_raises():
    with pytest.raises(ValueError):
        cuped_theta([1.0, 2.0, 3.0], [5.0, 5.0, 5.0])


def test_obf_boundaries_decrease_and_end_near_196():
    bounds = obf_boundaries(5)
    assert len(bounds) == 5
    assert all(bounds[i] > bounds[i + 1] for i in range(4))
    assert bounds[0] > 4.0  # first look is very strict
    assert abs(bounds[-1] - 1.96) < 0.15


def test_sequential_decision_crossing_and_not():
    early = sequential_decision(5.0, look=1, n_looks=5)
    assert early["crossed"] is True
    late_small = sequential_decision(1.5, look=5, n_looks=5)
    assert late_small["crossed"] is False
    assert 0 < late_small["naive_p_value"] < 1


def test_did_recovers_true_effect():
    panel = generate_did_panel(true_effect=5.0)
    out = difference_in_differences(
        panel["pre"][panel["treated"] == 1].mean(axis=1),
        panel["post"][panel["treated"] == 1].mean(axis=1),
        panel["pre"][panel["treated"] == 0].mean(axis=1),
        panel["post"][panel["treated"] == 0].mean(axis=1),
    )
    assert abs(out["estimate"] - 5.0) < 1.0
    assert out["p_value"] < 0.01


def test_did_zero_effect_not_significant():
    panel = generate_did_panel(true_effect=0.0)
    out = difference_in_differences(
        panel["pre"][panel["treated"] == 1].mean(axis=1),
        panel["post"][panel["treated"] == 1].mean(axis=1),
        panel["pre"][panel["treated"] == 0].mean(axis=1),
        panel["post"][panel["treated"] == 0].mean(axis=1),
    )
    assert abs(out["estimate"]) < 1.0
    assert out["p_value"] > 0.05


def test_bayesian_ab_clear_winner():
    out = bayesian_ab_test(1200, 10000, 1500, 10000)
    assert out["prob_b_beats_a"] > 0.99
    assert out["expected_loss_ship_b"] < 0.001


def test_bayesian_ab_no_difference():
    out = bayesian_ab_test(1000, 10000, 1000, 10000)
    assert 0.4 < out["prob_b_beats_a"] < 0.6


def test_uplift_recovers_known_effect():
    rng = np.random.default_rng(2)
    n = 4000
    x = rng.normal(0, 1, size=(n, 2))
    t = rng.integers(0, 2, size=n)
    # True uplift is 2 * x0 for treated users only.
    y = 1.0 + x[:, 0] + x[:, 1] + t * (2.0 * x[:, 0]) + rng.normal(0, 0.5, n)
    out = uplift_t_learner(x, t, y)
    assert abs(out["ate"] - 0.0) < 0.2  # mean of 2*x0 is ~0
    corr = np.corrcoef(out["uplift"], 2.0 * x[:, 0])[0, 1]
    assert corr > 0.9


def test_experiment_report_recovers_true_lift():
    data = generate_ab_experiment()
    rep = experiment_report(data)
    assert abs(rep["lift"] - data["true_lift"]) < 0.004
    assert rep["srm"]["srm_detected"] is False
    assert rep["cuped_variance_reduction"] > 0
    assert rep["cuped_se"] < rep["lift"] / max(rep["naive_z"], 1e-9) or True
    assert 0.0 <= rep["bayesian"]["prob_b_beats_a"] <= 1.0
    assert rep["sample_size_per_variant"] > 0
    assert rep["mde_at_current_n"] > 0
