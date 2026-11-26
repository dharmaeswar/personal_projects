"""Champion/challenger experiment design.

An Applied Scientist does not just fit a better model — they prove the
improvement is real before it ships. This module gives the validator three
experiment tools, all in pure Python:

- bootstrap confidence interval for the AUC difference between two models
  on the same validation sample (paired resampling, so the comparison is
  apples-to-apples);
- a paired test on per-loan log-loss, which is more sensitive than AUC to
  small calibration changes;
- a sample-size calculation for a champion/challenger rollout experiment,
  so a launch plan can state how many loans it needs to detect a given
  change in the default rate.
"""

import math
import random
from statistics import NormalDist

from sb_credit_validator.outcomes import roc_auc

_NORM = NormalDist()


def log_loss(y_true, scores, eps=1e-15):
    """Mean binary log-loss, with clipping so a 0/1 score cannot explode it."""
    total = 0.0
    for y, s in zip(y_true, scores):
        p = min(max(s, eps), 1.0 - eps)
        total += -(y * math.log(p) + (1 - y) * math.log(1 - p))
    return total / len(y_true) if y_true else 0.0


def paired_logloss_test(y_true, scores_a, scores_b):
    """Paired comparison of two models' per-loan log-loss.

    Returns the mean log-loss difference (B minus A, so negative means B is
    better), a z-statistic, and a two-sided p-value from a normal
    approximation. Identical score lists give a difference of 0 and p = 1.
    """
    diffs = []
    for y, sa, sb in zip(y_true, scores_a, scores_b):
        pa = min(max(sa, 1e-15), 1 - 1e-15)
        pb = min(max(sb, 1e-15), 1 - 1e-15)
        la = -(y * math.log(pa) + (1 - y) * math.log(1 - pa))
        lb = -(y * math.log(pb) + (1 - y) * math.log(1 - pb))
        diffs.append(lb - la)
    n = len(diffs)
    mean = sum(diffs) / n if n else 0.0
    var = sum((d - mean) ** 2 for d in diffs) / (n - 1) if n > 1 else 0.0
    se = math.sqrt(var / n) if n else 0.0
    if se == 0.0:
        return {"mean_diff": round(mean, 4), "z": 0.0, "p_value": 1.0}
    z = mean / se
    p_value = 2.0 * (1.0 - _NORM.cdf(abs(z)))
    return {"mean_diff": round(mean, 4), "z": round(z, 3),
            "p_value": round(p_value, 4)}


def bootstrap_auc_diff(y_true, scores_a, scores_b, n_boot=200, seed=123):
    """Bootstrap 95% CI for (AUC of B) minus (AUC of A) on the same sample.

    Each bootstrap draw resamples loans with replacement and scores both
    models on the same draw, so the interval reflects the paired
    comparison, not two independent samples.
    """
    rng = random.Random(seed)
    n = len(y_true)
    diffs = []
    for _ in range(n_boot):
        idx = [rng.randrange(n) for _ in range(n)]
        y_b = [y_true[i] for i in idx]
        if len(set(y_b)) < 2:
            continue
        a = roc_auc(y_b, [scores_a[i] for i in idx])
        b = roc_auc(y_b, [scores_b[i] for i in idx])
        diffs.append(b - a)
    diffs.sort()
    if not diffs:
        return {"mean_diff": 0.0, "ci_lo": 0.0, "ci_hi": 0.0, "n_boot": 0}
    lo = diffs[int(0.025 * len(diffs))]
    hi = diffs[min(len(diffs) - 1, int(0.975 * len(diffs)))]
    return {"mean_diff": round(sum(diffs) / len(diffs), 4),
            "ci_lo": round(lo, 4), "ci_hi": round(hi, 4),
            "n_boot": len(diffs)}


def min_sample_size(baseline_rate, mde, alpha=0.05, power=0.80):
    """Loans needed per arm to detect an absolute change `mde` in a rate.

    Two-proportion z-test sizing: baseline_rate is the champion arm's
    default rate, mde is the minimum detectable effect (absolute, e.g.
    0.01 = 1 percentage point). Returns the per-arm sample size, rounded
    up to a whole loan.
    """
    if not (0.0 < baseline_rate < 1.0):
        raise ValueError("baseline_rate must be between 0 and 1")
    if mde <= 0:
        raise ValueError("mde must be positive")
    z_alpha = _NORM.inv_cdf(1.0 - alpha / 2.0)
    z_beta = _NORM.inv_cdf(power)
    p1 = baseline_rate
    p2 = baseline_rate + mde
    if not (0.0 < p2 < 1.0):
        raise ValueError("baseline_rate + mde must stay between 0 and 1")
    p_bar = (p1 + p2) / 2.0
    n = ((z_alpha * math.sqrt(2 * p_bar * (1 - p_bar))
          + z_beta * math.sqrt(p1 * (1 - p1) + p2 * (1 - p2))) ** 2
         / mde ** 2)
    return int(math.ceil(n))
