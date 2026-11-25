#!/usr/bin/env python3
"""Run the full GenAI model validation and write the validation report.

Usage: python3 run_validation.py [--out validation_report.json]
Exit code 0 when the model passes all gates, 1 when it fails any gate.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from genai_validation import run_validation


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="validation_report.json")
    args = parser.parse_args()
    results = run_validation()
    report = results["report"]
    Path(args.out).write_text(json.dumps(results, indent=2), encoding="utf-8")
    lines = [
        "GenAI Model Validation Report",
        f"Cases validated: {results['cases']}",
        f"Hallucination rate: {results['hallucination']['rate']} "
        f"({results['hallucination']['flagged']} of {results['hallucination']['cases']} cases)",
        f"Champion accuracy: {results['benchmark']['models']['candidate-genai-v1']['accuracy']} "
        f"vs challenger {results['benchmark']['models']['challenger-rule-v1']['accuracy']} "
        f"vs benchmark {results['benchmark']['models']['benchmark-base-rate-v1']['accuracy']}",
        f"Mean decision agreement: {results['reliability']['mean_decision_agreement']}",
        f"Sensitivity flip rate: {results['sensitivity']['flip_rate']}",
        f"Drift PSI: {results['drift']['psi']}",
        f"Explainability coverage: {results['explainability']['mean_coverage']}",
        f"Prompt-injection success rate: {results['prompt_injection']['success_rate']} "
        f"({results['prompt_injection']['compromised']} of {results['prompt_injection']['attempts']} attempts)",
        f"Disparate-impact ratio: {results['fairness']['disparate_impact_ratio']} "
        f"(equal-opportunity gap {results['fairness']['equal_opportunity_gap']})",
        f"Findings: {len(report['findings'])}",
        f"Verdict: {report['verdict']}",
    ]
    for finding in report["findings"]:
        lines.append(f"  {finding['id']} [{finding['severity']}] {finding['title']}")
    Path("validation_report.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
