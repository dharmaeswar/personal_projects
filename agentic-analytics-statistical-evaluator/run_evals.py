#!/usr/bin/env python3
"""Run the agentic evals benchmark and print the evals report.

Builds a seeded synthetic benchmark (clean trajectories plus known-bad
mutations), judges every case with the rubric judge, checks the current
run against a baseline run (different seed) for regressions, diagnoses
each failure, and writes evals_report.txt. Failed eval cases are
findings, not errors, so the exit code stays 0 when the run completes.
"""

import sys

from agentic_stats import evals


def main():
    cases = evals.generate_synthetic_cases(n=10, seed=11)
    benchmark = evals.run_benchmark(cases)
    baseline = evals.run_benchmark(
        evals.generate_synthetic_cases(n=10, seed=7))
    current_scores = [r["overall"] for r in benchmark["results"]]
    baseline_scores = [r["overall"] for r in baseline["results"]]
    regression = evals.detect_regression(current_scores, baseline_scores)
    diagnoses = evals.diagnose_failures(benchmark)
    text = evals.render_evals_report(benchmark, regression, diagnoses)
    print(text)
    with open("evals_report.txt", "w") as fh:
        fh.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
