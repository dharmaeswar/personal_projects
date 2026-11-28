"""Seeded synthetic experiment data with known ground truth.

The generator writes the true lift into the data so every estimator in
the package can be checked against a known answer. No real users, no
real product data.
"""

import numpy as np


def generate_ab_experiment(n_per_variant=20000, baseline_rate=0.10,
                           true_lift=0.008, pre_period_corr=0.6, seed=42):
    """Simulate a randomised A/B test on a binary conversion metric.

    Each user has a pre-period activity covariate correlated with the
    outcome (so CUPED has something to work with). Treatment adds
    true_lift to the conversion probability. Returns a dict of arrays.
    """
    rng = np.random.default_rng(seed)
    n = 2 * n_per_variant
    treatment = np.repeat([0, 1], n_per_variant)
    rng.shuffle(treatment)
    # Pre-period covariate: standardised activity score.
    pre = rng.normal(0, 1, size=n)
    # Latent propensity: baseline logit shifted by the covariate.
    logit = np.log(baseline_rate / (1 - baseline_rate)) + pre_period_corr * pre
    p = 1 / (1 + np.exp(-logit))
    p = p + treatment * true_lift
    p = np.clip(p, 0.001, 0.999)
    converted = (rng.random(n) < p).astype(int)
    return {
        "treatment": treatment,
        "pre_period": pre,
        "converted": converted,
        "baseline_rate": baseline_rate,
        "true_lift": true_lift,
    }


def generate_did_panel(n_units=200, periods_pre=4, periods_post=4,
                       true_effect=5.0, seed=7):
    """Simulate a panel for difference-in-differences: treated units get
    true_effect added after the rollout; control units do not."""
    rng = np.random.default_rng(seed)
    treated = np.repeat([0, 1], n_units // 2)
    unit_effect = rng.normal(0, 3, size=n_units)
    time_effect = np.linspace(0, 2, periods_pre + periods_post)
    pre = (unit_effect[:, None] + time_effect[:periods_pre][None, :]
           + rng.normal(0, 1, size=(n_units, periods_pre)))
    post = (unit_effect[:, None] + time_effect[periods_pre:][None, :]
            + treated[:, None] * true_effect
            + rng.normal(0, 1, size=(n_units, periods_post)))
    return {
        "treated": treated,
        "pre": pre,
        "post": post,
        "true_effect": true_effect,
    }
