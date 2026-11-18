"""Evaluation harness for LLM-generated analyst notes.

Two checks a model-validation team runs on LLM output:
1. Grounding — every number the note cites must match a computed value
   (within tolerance); unsupported numbers are flagged.
2. Completeness — the note must mention each required topic term.

Plus a paired baseline-vs-tuned comparison: per-prompt score pairs,
win rate, a seeded bootstrap confidence interval on the mean
difference, and a Bonferroni correction when several metric families
are tested at once (guards against false findings).
"""

import math
import random
import re

_NUMBER_RE = re.compile(r"\d+\.\d+|\d+")


def _numbers_in(text):
    return [float(m) for m in _NUMBER_RE.findall(text)]


def score_grounding(text, computed, tolerance=0.05):
    """computed: {label: value}. Returns grounding report dict.

    A cited number is grounded when it is within `tolerance` (relative,
    default 5%) of some computed value. Rates are on a 0-1 scale, so a
    cited number is also checked on the 0-100 percent scale. A flat
    absolute tolerance would be meaningless here: typical MAE values
    are ~0.01, so a 0.01 absolute window would "ground" any small
    invented number.
    """
    cited = _numbers_in(text)
    computed_values = list(computed.values())
    supported = 0
    unsupported = []
    for num in cited:
        ok = any(
            abs(num - v) <= tolerance * abs(v) + 1e-9
            or abs(num - v * 100.0) <= tolerance * abs(v * 100.0) + 1e-9
            for v in computed_values
        )
        if ok:
            supported += 1
        else:
            unsupported.append(num)
    return {
        "cited": len(cited),
        "supported": supported,
        "unsupported": unsupported,
        "grounding_rate": (supported / len(cited)) if cited else 1.0,
    }


def score_completeness(text, required_terms):
    """Fraction of required terms (case-insensitive) present in text."""
    lowered = text.lower()
    found = [t for t in required_terms if t.lower() in lowered]
    missing = [t for t in required_terms if t.lower() not in lowered]
    return {
        "required": len(required_terms),
        "found": found,
        "missing": missing,
        "completeness": (len(found) / len(required_terms)) if required_terms else 1.0,
    }


def _sign_test_p(wins, n):
    """Two-sided exact binomial p-value for `wins` successes in `n` trials."""
    if n == 0:
        return 1.0
    p = 0.0
    for k in range(n + 1):
        prob = math.comb(n, k) * (0.5 ** n)
        if prob <= math.comb(n, wins) * (0.5 ** n) + 1e-12:
            p += prob
    return min(p, 1.0)


def paired_comparison(baseline_scores, tuned_scores, n_bootstrap=2000, seed=11):
    """Compare paired per-prompt scores; returns win rate, CI, p-value."""
    if len(baseline_scores) != len(tuned_scores) or not baseline_scores:
        raise ValueError("score lists must be non-empty and equal length")
    diffs = [t - b for b, t in zip(baseline_scores, tuned_scores)]
    n = len(diffs)
    wins = sum(1 for d in diffs if d > 0)
    ties = sum(1 for d in diffs if d == 0)
    mean_diff = sum(diffs) / n
    rng = random.Random(seed)
    boot_means = []
    for _ in range(n_bootstrap):
        sample = [rng.choice(diffs) for _ in range(n)]
        boot_means.append(sum(sample) / n)
    boot_means.sort()
    lo = boot_means[int(0.025 * n_bootstrap)]
    hi = boot_means[int(0.975 * n_bootstrap) - 1]
    return {
        "n": n,
        "wins": wins,
        "ties": ties,
        "win_rate": wins / n,
        "mean_diff": mean_diff,
        "ci_95": [lo, hi],
        "p_value": _sign_test_p(wins, n - ties),
    }


def bonferroni(p_values):
    """Bonferroni-adjusted p-values, capped at 1.0."""
    m = len(p_values)
    return [min(p * m, 1.0) for p in p_values]
