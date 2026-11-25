"""Run the harness-improvement loop: baseline vs prompt-fixed model.

Usage:
    python run_improvement_loop.py

Runs the full suite against the baseline model and the improved model,
then prints the paired comparison, the regression check and the
ship/no-ship recommendation. Writes improvement_report.json.
"""

import json
import os

from behavior_eval.improve import run_loop
from behavior_eval.responses import baseline_model, improved_model

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    result = run_loop(baseline_model, improved_model)
    comp = result["comparison"]
    print("Harness-improvement loop: baseline -> prompt-fixed model")
    print(f"Pass rate: {comp['rate_before']:.3f} -> {comp['rate_after']:.3f} "
          f"(delta {comp['delta']:+.3f}, McNemar p={comp['mcnemar_p']})")
    print(f"Paired verdict: {comp['verdict']}")
    print(f"Fixed cases: {result['fixed_cases'] or 'none'}")
    print(f"Broken cases: {result['broken_cases'] or 'none'}")
    print(f"Recommendation: {result['recommendation']}")
    out = {"comparison": comp,
           "fixed_cases": result["fixed_cases"],
           "broken_cases": result["broken_cases"],
           "recommendation": result["recommendation"],
           "regression_verdict": result["regression"]["verdict"]}
    with open(os.path.join(HERE, "improvement_report.json"), "w") as f:
        json.dump(out, f, indent=2)


if __name__ == "__main__":
    main()
