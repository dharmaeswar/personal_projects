"""CUPED variance reduction for experiment metrics.

CUPED (Controlled-experiment Using Pre-Experiment Data) adjusts a metric
with a pre-period covariate that is correlated with it, shrinking the
variance of the estimated treatment effect without biasing it (the
covariate is measured before randomisation, so it cannot be affected by
the treatment).
"""

import numpy as np


def cuped_theta(metric, covariate):
    """Optimal CUPED coefficient: cov(metric, covariate) / var(covariate)."""
    metric = np.asarray(metric, dtype=float)
    covariate = np.asarray(covariate, dtype=float)
    if metric.shape != covariate.shape:
        raise ValueError("metric and covariate must have the same shape")
    if metric.size < 3:
        raise ValueError("need at least 3 observations")
    var = float(np.var(covariate, ddof=1))
    if var == 0:
        raise ValueError("covariate has zero variance")
    return float(np.cov(metric, covariate, ddof=1)[0, 1] / var)


def cuped_adjust(metric, covariate, theta=None):
    """Return the CUPED-adjusted metric: Y - theta * (X - mean(X))."""
    metric = np.asarray(metric, dtype=float)
    covariate = np.asarray(covariate, dtype=float)
    if theta is None:
        theta = cuped_theta(metric, covariate)
    adjusted = metric - theta * (covariate - covariate.mean())
    return adjusted, float(theta)


def cuped_variance_reduction(metric, covariate):
    """Share of metric variance removed by CUPED (0..1), from the correlation."""
    metric = np.asarray(metric, dtype=float)
    covariate = np.asarray(covariate, dtype=float)
    corr = float(np.corrcoef(metric, covariate)[0, 1])
    return corr ** 2
