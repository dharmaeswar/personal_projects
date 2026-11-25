"""Run the full behavior-eval suite against a model and write reports.

Usage:
    python run_evaluation.py [--model baseline|improved] [--record-baseline]

Writes evaluation_report.json and evaluation_report.txt. With
--record-baseline, also writes baseline.json, the reference the
regression check compares later runs against.
"""

import argparse
import json
import os

from behavior_eval.dataset import load_cases
from behavior_eval.graders import grade_case
from behavior_eval.metrics import summarize
from behavior_eval.regression import save_baseline
from behavior_eval.responses import baseline_model, improved_model

HERE = os.path.dirname(os.path.abspath(__file__))
MODELS = {"baseline": baseline_model, "improved": improved_model}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="baseline", choices=list(MODELS))
    parser.add_argument("--record-baseline", action="store_true")
    args = parser.parse_args()

    model = MODELS[args.model]
    results = [grade_case(c, model(c)) for c in load_cases()]
    summary = summarize(results)
    gate = "PASS" if summary["pass_rate"] >= 0.9 else "FAIL"

    report = {"model": args.model, "summary": summary, "results": results}
    with open(os.path.join(HERE, "evaluation_report.json"), "w") as f:
        json.dump(report, f, indent=2)

    lines = [f"Model-behavior eval harness -- model: {args.model}",
             f"Gate (min pass rate 0.90): {gate}",
             f"Overall: {summary['n']} cases, pass rate "
             f"{summary['pass_rate']:.3f}, 95% CI {summary['ci_95']}"]
    for surface, s in sorted(summary["surfaces"].items()):
        lines.append(f"  {surface}: {s['n']} cases, pass rate "
                     f"{s['pass_rate']:.3f}, CI {s['ci_95']}, "
                     f"failed: {s['failed'] or 'none'}")
    with open(os.path.join(HERE, "evaluation_report.txt"), "w") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))

    if args.record_baseline:
        save_baseline(os.path.join(HERE, "baseline.json"), results, summary)
        print("Baseline recorded to baseline.json")


if __name__ == "__main__":
    main()
