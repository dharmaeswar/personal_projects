"""Run the education AI evaluation harness from the command line.

Usage:
    python run_evaluation.py [--log evaluation_log.jsonl]
                             [--min-overall 0.75] [--min-correctness 0.70]

Prints a per-subject summary and the release-gate decision. Exits
with code 0 when the gate passes and 1 when it fails.
"""

import argparse
import sys

from edu_ai_evaluation_guardrails.data import load_cases
from edu_ai_evaluation_guardrails.gates import GateThresholds, evaluate_gate
from edu_ai_evaluation_guardrails.harness import run_evaluation


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Evaluate an AI tutor on synthetic education cases.")
    parser.add_argument("--log", default="evaluation_log.jsonl",
                        help="JSONL observability log path")
    parser.add_argument("--min-overall", type=float, default=0.75)
    parser.add_argument("--min-correctness", type=float, default=0.70)
    args = parser.parse_args(argv)

    cases = load_cases()
    results, summary = run_evaluation(
        cases, known_names=("Maya Chen",), log_path=args.log)
    decision = evaluate_gate(
        {
            "mean_overall": summary.mean_overall,
            "mean_correctness": summary.mean_correctness,
            "safety_failures": summary.safety_failures,
            "pii_leaks": summary.pii_leaks,
        },
        GateThresholds(min_mean_overall=args.min_overall,
                       min_mean_correctness=args.min_correctness))

    print(f"Run {summary.run_id}: {summary.cases} cases evaluated")
    print(f"Mean overall score:     {summary.mean_overall:.3f}")
    print(f"Mean correctness:       {summary.mean_correctness:.3f}")
    print(f"Safety failures:        {summary.safety_failures}")
    print(f"PII leaks:              {summary.pii_leaks}")
    print(f"Total redactions:       {summary.total_redactions}")
    for subject, score in sorted(summary.per_subject.items()):
        print(f"  {subject:<10} mean overall {score:.3f}")
    print(f"Release gate: {'PASS' if decision.passed else 'FAIL'}")
    for reason in decision.reasons:
        print(f"  - {reason}")
    return 0 if decision.passed else 1


if __name__ == "__main__":
    sys.exit(main())
