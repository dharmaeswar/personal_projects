"""Demo: run the rating-model validation checks on synthetic data.

Builds a seeded synthetic rating book (grades AAA..CCC with implied PDs,
a prior-year and a current-year transition matrix, and criteria input
vintages), then runs the four rating checks and prints a validation
summary. All data is synthetic; no real ratings, obligors, or criteria.

Usage:
    PYTHONPATH=. python3 run_ratings_check.py
"""

import json
import random

from model_validation_toolkit.ratings import (
    check_pd_monotonicity,
    data_aging_check,
    grade_backtest_table,
    migration_summary,
    transition_matrix_stability,
)

GRADES = ["AAA", "AA", "A", "BBB", "BB", "B", "CCC"]
# Implied one-year default probabilities per grade (synthetic).
GRADE_PDS = [0.0002, 0.0005, 0.001, 0.004, 0.015, 0.05, 0.20]
N_PER_GRADE = [500, 800, 1200, 1500, 900, 600, 200]


def synthetic_defaults(seed=7):
    """Draw realised defaults per grade from the implied PDs (seeded)."""
    rng = random.Random(seed)
    rows = []
    for grade, pd, n in zip(GRADES, GRADE_PDS, N_PER_GRADE):
        observed = sum(1 for _ in range(n) if rng.random() < pd)
        rows.append((grade, pd, observed, n))
    return rows


def main():
    mono = check_pd_monotonicity(list(zip(GRADES, GRADE_PDS)))
    print(f"PD monotonicity: {'PASS' if mono['monotone'] else 'FAIL'} "
          f"({mono['n_grades']} grades, {len(mono['inversions'])} inversions)")

    table = grade_backtest_table(synthetic_defaults())
    print(f"Default back-test: {'PASS' if table['all_pass'] else 'FAIL'} "
          f"({table['n_grades']} grades, failing: "
          f"{table['failing_grades'] or 'none'})")
    for row in table["grades"]:
        print(f"  {row['grade']:>3}: PD={row['predicted_pd']:.4f} "
              f"expected={row['expected_defaults']:6.1f} "
              f"observed={row['observed_defaults']:3d} "
              f"z={row['z']:+.2f} p={row['p_value']:.3f} "
              f"{'PASS' if row['pass'] else 'FAIL'}")

    # Prior vs current transition matrices (rows sum to 1; last column
    # is Default). The current year shows more downgrades from BBB.
    prior = [
        [0.90, 0.08, 0.015, 0.004, 0.001, 0.0, 0.0, 0.0],
        [0.03, 0.88, 0.07, 0.015, 0.004, 0.001, 0.0, 0.0],
        [0.005, 0.04, 0.87, 0.07, 0.01, 0.004, 0.001, 0.0],
        [0.001, 0.005, 0.05, 0.84, 0.08, 0.015, 0.004, 0.001],
        [0.0, 0.001, 0.01, 0.06, 0.78, 0.11, 0.03, 0.009],
        [0.0, 0.0, 0.002, 0.01, 0.07, 0.72, 0.14, 0.048],
        [0.0, 0.0, 0.0, 0.002, 0.01, 0.08, 0.65, 0.258],
    ]
    current = [row[:] for row in prior]
    current[3] = [0.001, 0.005, 0.04, 0.80, 0.11, 0.03, 0.009, 0.005]
    stability = transition_matrix_stability(prior, current)
    print(f"Transition stability: {'PASS' if stability['stable'] else 'FAIL'} "
          f"(max move {stability['max_abs_diff']:.3f}, "
          f"{len(stability['breached_cells'])} cells over 0.05)")

    aging = data_aging_check(
        {"financials": "2026-10-01", "market_data": "2026-11-20",
         "criteria_text": "2026-08-01"},
        as_of="2026-11-23", max_age_days=90)
    print(f"Data aging: {'PASS' if aging['all_fresh'] else 'FAIL'} "
          f"(max age {aging['max_age_days']} days, stale: "
          f"{[s['input'] for s in aging['stale_inputs']] or 'none'})")

    counts = {
        ("AAA", "AAA"): 450, ("AAA", "AA"): 50,
        ("AA", "AAA"): 24, ("AA", "AA"): 704, ("AA", "A"): 72,
        ("A", "AA"): 48, ("A", "A"): 1044, ("A", "BBB"): 108,
        ("BBB", "A"): 60, ("BBB", "BBB"): 1260, ("BBB", "BB"): 165,
        ("BBB", "B"): 15,
        ("BB", "BBB"): 54, ("BB", "BB"): 702, ("BB", "B"): 99,
        ("BB", "CCC"): 27, ("BB", "Default"): 18,
        ("B", "BB"): 42, ("B", "B"): 432, ("B", "CCC"): 84,
        ("B", "Default"): 42,
        ("CCC", "B"): 16, ("CCC", "CCC"): 130, ("CCC", "Default"): 54,
    }
    summary = migration_summary(counts, GRADES)
    print("Migration summary (synthetic book of "
          f"{summary['total_obligors']} obligors): "
          f"upgrade {summary['upgrade_rate']:.1%}, "
          f"downgrade {summary['downgrade_rate']:.1%}, "
          f"default {summary['default_rate']:.1%}, "
          f"stable {summary['stable_rate']:.1%}")

    report = {"pd_monotonicity": mono, "default_backtest": table,
              "transition_stability": stability, "data_aging": aging,
              "migration_summary": summary}
    with open("ratings_validation_report.json", "w") as fh:
        json.dump(report, fh, indent=2, default=str)
    print("Report written to ratings_validation_report.json")


if __name__ == "__main__":
    main()
