"""CLI: benchmark the deterministic reference migration for every sample.

Usage:
    python run_evaluation.py [--sample NAME]

Prints a per-sample score table and exits 0 only when every sample passes
(all behaviour cases green and no invariant failures).
"""

from __future__ import annotations

import argparse
import sys

from migration_evaluator.evaluator import MigrationEvaluator
from migration_evaluator.samples import SAMPLES
from migration_evaluator.transforms import migrate_source


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample", default=None, help="evaluate one sample only")
    args = parser.parse_args(argv)

    names = [args.sample] if args.sample else sorted(SAMPLES)
    all_passed = True
    for name in names:
        sample = SAMPLES[name]
        migrated = migrate_source(sample.legacy_source)
        report = MigrationEvaluator(sample.legacy_source, sample.cases).evaluate(
            migrated, name
        )
        status = "PASS" if report.passed else "FAIL"
        print(
            f"{name:12s} {status}  behaviour {report.passed_cases}/"
            f"{report.total_cases}  overall {report.overall_score:.2f}  "
            f"lines changed {report.lines_changed}"
        )
        for failure in report.invariant_failures:
            print(f"    - {failure}")
        all_passed = all_passed and report.passed
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
