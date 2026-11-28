"""Group-sequential monitoring: O'Brien-Fleming alpha spending.

Peeking at an experiment every day and testing at alpha = 0.05 each time
inflates the false-positive rate. Group-sequential boundaries spend the
alpha budget across looks, so the overall Type I error stays at the
nominal level while still allowing early stopping for a real effect.
"""

import math

from scipy import stats


def obf_boundaries(n_looks, alpha=0.05):
    """O'Brien-Fleming critical z-values for each look (1..n_looks).

    Uses the Lan-DeMets O'Brien-Fleming spending function at equally
    spaced information fractions. The final boundary is close to 1.96;
    early boundaries are much stricter.
    """
    if n_looks < 1:
        raise ValueError("n_looks must be >= 1")
    z_alpha = stats.norm.ppf(1 - alpha / 2)
    bounds = []
    for k in range(1, n_looks + 1):
        t = k / n_looks
        # O'Brien-Fleming spending: alpha(t) = 2 * (1 - Phi(z_{a/2} / sqrt(t)))
        spent = 2 * (1 - stats.norm.cdf(z_alpha / math.sqrt(t)))
        bounds.append(float(stats.norm.ppf(1 - spent / 2)))
    return bounds


def sequential_decision(z_stat, look, n_looks, alpha=0.05):
    """Decide at a given look: stop (significant) or continue.

    Returns a dict with the boundary, whether the boundary was crossed,
    and the naive (unadjusted) two-sided p-value for reference.
    """
    bounds = obf_boundaries(n_looks, alpha)
    if not 1 <= look <= n_looks:
        raise ValueError("look must be between 1 and n_looks")
    boundary = bounds[look - 1]
    return {
        "boundary": boundary,
        "crossed": abs(z_stat) >= boundary,
        "naive_p_value": float(2 * (1 - stats.norm.cdf(abs(z_stat)))),
    }
