"""Causal-inference estimators: difference-in-differences, uplift, Bayesian A/B.

Each estimator is for a different question an experimentation platform
has to answer: DiD when randomisation was not possible (e.g. a staged
rollout), uplift when the treatment should go only to users it helps,
and a Bayesian rule when the decision is "ship or not" rather than a
p-value.
"""

import numpy as np
from scipy import stats


def difference_in_differences(y_treat_pre, y_treat_post, y_ctrl_pre, y_ctrl_post):
    """DiD estimate with a two-sided p-value (Welch t-test on the changes).

    Assumes parallel trends: without the treatment, the treated group
    would have moved the same as the control group.
    """
    d_treat = np.asarray(y_treat_post, dtype=float) - np.asarray(y_treat_pre, dtype=float)
    d_ctrl = np.asarray(y_ctrl_post, dtype=float) - np.asarray(y_ctrl_pre, dtype=float)
    est = float(d_treat.mean() - d_ctrl.mean())
    t_stat, p_value = stats.ttest_ind(d_treat, d_ctrl, equal_var=False)
    se = float(np.sqrt(d_treat.var(ddof=1) / len(d_treat)
                       + d_ctrl.var(ddof=1) / len(d_ctrl)))
    return {
        "estimate": est,
        "se": se,
        "ci_95": (est - 1.96 * se, est + 1.96 * se),
        "p_value": float(p_value),
    }


def bayesian_ab_test(conv_a, n_a, conv_b, n_b, prior_alpha=1.0, prior_beta=1.0,
                     n_samples=20000, seed=0):
    """Beta-Binomial Bayesian A/B test on conversion rates.

    Returns P(B > A), the expected loss of shipping B, the expected loss
    of shipping A, and the posterior means. Expected loss is the decision
    rule: ship B only when its expected loss is small (e.g. < 0.0005).
    """
    rng = np.random.default_rng(seed)
    post_a = rng.beta(prior_alpha + conv_a, prior_beta + n_a - conv_a,
                      size=n_samples)
    post_b = rng.beta(prior_alpha + conv_b, prior_beta + n_b - conv_b,
                      size=n_samples)
    diff = post_b - post_a
    return {
        "prob_b_beats_a": float((diff > 0).mean()),
        "expected_loss_ship_b": float(np.maximum(-diff, 0).mean()),
        "expected_loss_ship_a": float(np.maximum(diff, 0).mean()),
        "posterior_mean_a": float(post_a.mean()),
        "posterior_mean_b": float(post_b.mean()),
    }


def uplift_t_learner(features, treatment, outcome):
    """T-learner uplift model: one linear model per arm, uplift = mu1 - mu0.

    Fits two ordinary-least-squares models (treatment / control) with an
    intercept and returns per-user uplift estimates plus the average
    treatment effect. Linear models keep the estimator transparent and
    fast; the point is the uplift workflow, not a tuned ML model.
    """
    X = np.asarray(features, dtype=float)
    t = np.asarray(treatment, dtype=int)
    y = np.asarray(outcome, dtype=float)
    if X.ndim == 1:
        X = X.reshape(-1, 1)
    X_aug = np.column_stack([np.ones(len(X)), X])

    def _fit(mask):
        coef, *_ = np.linalg.lstsq(X_aug[mask], y[mask], rcond=None)
        return coef

    coef_t = _fit(t == 1)
    coef_c = _fit(t == 0)
    mu1 = X_aug @ coef_t
    mu0 = X_aug @ coef_c
    uplift = mu1 - mu0
    return {
        "uplift": uplift,
        "ate": float(uplift.mean()),
        "coef_treatment": coef_t,
        "coef_control": coef_c,
    }
