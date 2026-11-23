"""Rating-model and criteria validation: the checks an Analytic Quality &
Validation team runs on credit rating models and the criteria behind them.

- Grade PDs must be monotone: a worse rating grade cannot carry a lower
  predicted default probability than a better grade.
- Realised defaults are back-tested against the PD each grade implies,
  grade by grade, with a binomial z-test.
- Year-on-year rating transition matrices are compared for stability.
- Criteria inputs are checked for data aging: an input vintage older than
  the allowed window cannot support a current rating decision.

Pure standard library. All functions take plain sequences/dicts and return
plain dicts/lists, so results drop straight into a validation document.
All data in the demo is synthetic; nothing here uses real ratings,
obligors, or criteria.
"""

import math
from datetime import date
from typing import Dict, List, Sequence, Tuple


# ---------------------------------------------------------------- PD monotonicity
def check_pd_monotonicity(grade_pds: Sequence[Tuple[str, float]]) -> Dict:
    """Check predicted default probabilities rise (never fall) as grades worsen.

    ``grade_pds`` is ordered best grade first, e.g.
    [("AAA", 0.0002), ("AA", 0.0005), ("A", 0.001), ...].
    Returns whether the curve is monotone and every inversion found.
    """
    pairs = [(str(g), float(p)) for g, p in grade_pds]
    if len(pairs) < 2:
        raise ValueError("need at least two grades to check monotonicity")
    for _, p in pairs:
        if not 0.0 <= p <= 1.0:
            raise ValueError("PDs must be between 0 and 1")
    inversions = []
    for (g1, p1), (g2, p2) in zip(pairs, pairs[1:]):
        if p2 < p1:
            inversions.append({"better_grade": g1, "worse_grade": g2,
                               "better_pd": p1, "worse_pd": p2})
    return {"monotone": not inversions, "inversions": inversions,
            "n_grades": len(pairs)}


# ---------------------------------------------------------------- default back-test
def _normal_two_sided_p(z: float) -> float:
    return 1.0 - math.erf(abs(z) / math.sqrt(2.0))


def default_rate_backtest(predicted_pd: float, observed_defaults: int,
                          n_obligors: int, alpha: float = 0.05) -> Dict:
    """Binomial z-test of realised defaults against the grade's implied PD.

    Returns expected defaults, the z-statistic, a two-sided p-value, and
    whether the grade passes at the ``alpha`` level. A failing grade means
    realised defaults are statistically inconsistent with the PD the
    rating criteria imply — the criteria or the PD mapping needs review.
    """
    p = float(predicted_pd)
    n = int(n_obligors)
    obs = int(observed_defaults)
    if not 0.0 < p < 1.0:
        raise ValueError("predicted_pd must be strictly between 0 and 1")
    if n <= 0:
        raise ValueError("n_obligors must be positive")
    if not 0 <= obs <= n:
        raise ValueError("observed_defaults must be between 0 and n_obligors")
    expected = n * p
    sd = math.sqrt(n * p * (1.0 - p))
    z = (obs - expected) / sd
    p_value = _normal_two_sided_p(z)
    return {"predicted_pd": p, "n_obligors": n, "observed_defaults": obs,
            "expected_defaults": expected, "z": z, "p_value": p_value,
            "pass": p_value >= alpha}


def grade_backtest_table(rows: Sequence[Tuple[str, float, int, int]],
                        alpha: float = 0.05) -> Dict:
    """Back-test every grade; ``rows`` are (grade, predicted_pd, observed, n)."""
    results = []
    for grade, pd, observed, n in rows:
        result = default_rate_backtest(pd, observed, n, alpha=alpha)
        result["grade"] = grade
        results.append(result)
    failing = [r["grade"] for r in results if not r["pass"]]
    return {"grades": results, "n_grades": len(results),
            "failing_grades": failing, "all_pass": not failing}


# ---------------------------------------------------------------- transition stability
def transition_matrix_stability(prior: Sequence[Sequence[float]],
                                current: Sequence[Sequence[float]],
                                threshold: float = 0.05) -> Dict:
    """Compare two yearly rating transition matrices over the same grades.

    Rows are from-grades, columns are to-grades (same order in both).
    Returns the largest absolute cell move, the mean absolute move, and
    every cell whose move exceeds ``threshold`` — a large move means the
    migration behaviour the criteria assume no longer matches reality.
    """
    if len(prior) != len(current) or not prior:
        raise ValueError("matrices must be non-empty and the same shape")
    breached = []
    total = 0.0
    count = 0
    max_diff = 0.0
    for i, (prow, crow) in enumerate(zip(prior, current)):
        if len(prow) != len(crow):
            raise ValueError("matrices must be non-empty and the same shape")
        for j, (a, b) in enumerate(zip(prow, crow)):
            diff = abs(float(b) - float(a))
            total += diff
            count += 1
            max_diff = max(max_diff, diff)
            if diff > threshold:
                breached.append({"from_index": i, "to_index": j,
                                 "prior": float(a), "current": float(b),
                                 "diff": float(b) - float(a)})
    return {"max_abs_diff": max_diff, "mean_abs_diff": total / count,
            "breached_cells": breached, "stable": not breached}


# ---------------------------------------------------------------- data aging
def data_aging_check(vintages: Dict[str, str], as_of: str,
                     max_age_days: int = 90) -> Dict:
    """Flag criteria inputs whose vintage is older than ``max_age_days``.

    ``vintages`` maps input name -> ISO date string (YYYY-MM-DD);
    ``as_of`` is the validation date. Stale inputs cannot support a
    current rating decision and must be refreshed before sign-off.
    """
    as_of_date = date.fromisoformat(as_of)
    stale = []
    max_age = 0
    for name, vintage in sorted(vintages.items()):
        age = (as_of_date - date.fromisoformat(vintage)).days
        if age < 0:
            raise ValueError(f"vintage for {name} is after the as-of date")
        max_age = max(max_age, age)
        if age > max_age_days:
            stale.append({"input": name, "vintage": vintage, "age_days": age})
    return {"stale_inputs": stale, "max_age_days": max_age,
            "all_fresh": not stale}


# ---------------------------------------------------------------- migration summary
def migration_summary(counts: Dict[Tuple[str, str], int],
                      grades: Sequence[str]) -> Dict:
    """Upgrade / downgrade / default rates from (from_grade, to_grade) counts.

    ``grades`` is ordered best first; "Default" is treated as the worst
    outcome. Counts are numbers of obligors moving between grades.
    """
    order = {g: i for i, g in enumerate(grades)}
    worst = len(grades)
    total = 0
    upgrades = 0
    downgrades = 0
    defaults = 0
    for (frm, to), count in counts.items():
        if count < 0:
            raise ValueError("counts cannot be negative")
        if frm not in order:
            raise ValueError(f"unknown from-grade: {frm}")
        to_idx = worst if to == "Default" else order.get(to)
        if to_idx is None:
            raise ValueError(f"unknown to-grade: {to}")
        total += count
        if to == "Default":
            defaults += count
        elif to_idx < order[frm]:
            upgrades += count
        elif to_idx > order[frm]:
            downgrades += count
    if total == 0:
        raise ValueError("no migrations counted")
    return {"total_obligors": total,
            "upgrade_rate": upgrades / total,
            "downgrade_rate": downgrades / total,
            "default_rate": defaults / total,
            "stable_rate": (total - upgrades - downgrades - defaults) / total}
