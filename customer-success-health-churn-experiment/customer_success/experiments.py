"""Experimentation and causal inference: A/B, CUPED, DiD, synthetic control.

All estimators are implemented from scratch (standard library only) and the
tests check each one against a planted effect of known size, so a broken
estimator fails loudly instead of shipping a confident wrong number.
"""
import math


def _norm_cdf(z):
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def welch_ttest(a, b):
    """Welch two-sample t-test with a normal approximation (large n)."""
    n1, n2 = len(a), len(b)
    m1, m2 = sum(a) / n1, sum(b) / n2
    v1 = sum((x - m1) ** 2 for x in a) / (n1 - 1)
    v2 = sum((x - m2) ** 2 for x in b) / (n2 - 1)
    se = math.sqrt(v1 / n1 + v2 / n2)
    t = (m1 - m2) / se if se else 0.0
    p = 2 * (1 - _norm_cdf(abs(t)))
    return {
        "mean_treat": round(m1, 3),
        "mean_control": round(m2, 3),
        "diff": round(m1 - m2, 3),
        "t": round(t, 2),
        "p": round(p, 4),
        "ci95": (round(m1 - m2 - 1.96 * se, 3), round(m1 - m2 + 1.96 * se, 3)),
    }


def srm_chi2(n_treat, n_control, expected_frac=0.5):
    """Sample-ratio-mismatch check on the randomized split (1-df chi-square)."""
    n = n_treat + n_control
    e_t, e_c = n * expected_frac, n * (1 - expected_frac)
    chi2 = (n_treat - e_t) ** 2 / e_t + (n_control - e_c) ** 2 / e_c
    # chi-square(1) survival: P(X > chi2) = 2 * (1 - Phi(sqrt(chi2)))
    p = max(0.0, 2 * (1 - _norm_cdf(math.sqrt(chi2))))
    return {"chi2": round(chi2, 2), "p": round(p, 4)}


def cuped_theta(outcome, covariate):
    """CUPED coefficient: Cov(outcome, covariate) / Var(covariate)."""
    n = len(outcome)
    mo, mc = sum(outcome) / n, sum(covariate) / n
    cov = sum((o - mo) * (c - mc) for o, c in zip(outcome, covariate)) / n
    var_c = sum((c - mc) ** 2 for c in covariate) / n
    return cov / var_c if var_c else 0.0


def cuped_adjust(outcome, covariate, theta=None):
    """CUPED variance reduction: subtract theta * (covariate - mean).

    Pass one pooled theta for both arms of a test; fitting a separate theta
    per arm would shift the arm means and bias the comparison.
    """
    if theta is None:
        theta = cuped_theta(outcome, covariate)
    mc = sum(covariate) / len(covariate)
    return [o - theta * (c - mc) for o, c in zip(outcome, covariate)], round(theta, 3)


def difference_in_differences(treat_pre, treat_post, control_pre, control_post):
    """DiD: (treat post - treat pre) - (control post - control pre)."""
    dt = sum(treat_post) / len(treat_post) - sum(treat_pre) / len(treat_pre)
    dc = sum(control_post) / len(control_post) - sum(control_pre) / len(control_pre)
    return round(dt - dc, 4)


def _project_simplex(v):
    """Euclidean projection of v onto the probability simplex."""
    u = sorted(v, reverse=True)
    css = 0.0
    rho = 0
    for j, uj in enumerate(u, start=1):
        css += uj
        if uj - (css - 1.0) / j > 0:
            rho = j
    theta = (sum(u[:rho]) - 1.0) / rho
    return [max(0.0, x - theta) for x in v]


def synthetic_control(treated_pre, donors_pre, treated_post, donors_post,
                      iters=2000, lr=0.05):
    """Ridge-free synthetic control: weights on donors (simplex) fit pre-period.

    donors_pre/post are lists of donor series (one list per donor). Returns
    weights, pre-period RMSPE and the post-period effect (treated - synthetic).
    """
    k = len(donors_pre)
    w = [1.0 / k] * k
    t = len(treated_pre)
    for _ in range(iters):
        grad = [0.0] * k
        for s in range(t):
            synth = sum(wj * donors_pre[j][s] for j, wj in enumerate(w))
            err = synth - treated_pre[s]
            for j in range(k):
                grad[j] += 2 * err * donors_pre[j][s] / t
        w = _project_simplex([wj - lr * g for wj, g in zip(w, grad)])
    pre_rmse = math.sqrt(
        sum((sum(wj * donors_pre[j][s] for j, wj in enumerate(w)) - treated_pre[s]) ** 2
            for s in range(t)) / t
    )
    post_t = sum(treated_post) / len(treated_post)
    post_s = sum(
        sum(wj * donors_post[j][s] for j, wj in enumerate(w))
        for s in range(len(treated_post))
    ) / len(treated_post)
    return {
        "weights": [round(x, 3) for x in w],
        "pre_rmse": round(pre_rmse, 4),
        "effect": round(post_t - post_s, 4),
    }


def mde(std, n_per_arm, alpha=0.05, power=0.80):
    """Minimum detectable effect for a two-arm test (normal approximation)."""
    z_a = 1.96 if alpha == 0.05 else 1.645
    z_b = 0.84 if power == 0.80 else 1.28
    return round((z_a + z_b) * std * math.sqrt(2.0 / n_per_arm), 4)
