"""Run the AI-generated-code change gate over the seeded sample changes.

Writes change_gate_report.json and prints a per-change verdict.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agent_eval.change_gate import build_sample_changes, run_change_gate_eval


def main():
    report = run_change_gate_eval(build_sample_changes())
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "change_gate_report.json")
    with open(out, "w") as fh:
        json.dump(report, fh, indent=2)
    for change in report["changes"]:
        status = "PASS" if change["passed"] else "FAIL"
        print(f"{change['change_id']} ({change['author']}): {status} "
              f"score {change['score']}")
        for failure in change["failures"]:
            print(f"  - {failure}")
    print(f"Overall: {report['passed']}/{report['total']} changes pass "
          f"(verdict {report['verdict']})")
    print(f"Report written to {out}")
    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
