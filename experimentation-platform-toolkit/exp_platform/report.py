"""One-call experiment report: design check, CUPED, sequential look, Bayesian call.

Runs the full platform workflow on a synthetic experiment and returns a
plain dict a reviewer can read without running each module by hand.
"""

import numpy as np
from scipy import stats

from exp_platform.design import (
    check_srm,
    minimum_detectable_effect,
    sample_size_proportion,
)
from exp_platform.cuped import cuped_adjust, cuped_variance_reduction
from exp_platform.sequential import sequential_decision
from exp_platform.causal import bayesian_ab_test


def experiment_report(data, alpha=0.05, n_looks=5, look=5):
    """Analyse one experiment dict from data_gen.generate_ab_experiment."""
    t = data["treatment"]
    y = data["converted"]
    pre = data["pre_period"]
    n_c = int((t == 0).sum())
    n_t = int((t == 1).sum())
    conv_c = int(y[t == 0].sum())
    conv_t = int(y[t == 1].sum())
    rate_c = conv_c / n_c
    rate_t = conv_t / n_t
    lift = rate_t - rate_c

    # Naive two-proportion z-test.
    p_pool = (conv_c + conv_t) / (n_c + n_t)
    se = float(np.sqrt(p_pool * (1 - p_pool) * (1 / n_c + 1 / n_t)))
    z_stat = lift / se
    p_value = float(2 * (1 - stats.norm.cdf(abs(z_stat))))

    # CUPED on the binary outcome using the pre-period covariate.
    adj, theta = cuped_adjust(y.astype(float), pre)
    adj_c = adj[t == 0].mean()
    adj_t = adj[t == 1].mean()
    se_cuped = float(np.sqrt(adj[t == 0].var(ddof=1) / n_c
                             + adj[t == 1].var(ddof=1) / n_t))
    z_cuped = (adj_t - adj_c) / se_cuped

    bayes = bayesian_ab_test(conv_c, n_c, conv_t, n_t)
    seq = sequential_decision(z_stat, look=look, n_looks=n_looks, alpha=alpha)
    return {
        "n_control": n_c,
        "n_treatment": n_t,
        "rate_control": rate_c,
        "rate_treatment": rate_t,
        "lift": lift,
        "true_lift": data["true_lift"],
        "naive_z": float(z_stat),
        "naive_p_value": p_value,
        "srm": check_srm(n_c, n_t),
        "cuped_theta": theta,
        "cuped_variance_reduction": cuped_variance_reduction(
            y.astype(float), pre),
        "cuped_lift": float(adj_t - adj_c),
        "cuped_z": float(z_cuped),
        "cuped_se": se_cuped,
        "bayesian": bayes,
        "sequential": seq,
        "sample_size_per_variant": sample_size_proportion(
            data["baseline_rate"], data["true_lift"], alpha=alpha),
        "mde_at_current_n": minimum_detectable_effect(
            data["baseline_rate"], min(n_c, n_t), alpha=alpha),
    }
