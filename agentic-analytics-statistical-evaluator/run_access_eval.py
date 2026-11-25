#!/usr/bin/env python3
"""Run the Access propensity, wallet & attrition evaluation.

Usage:
    python run_access_eval.py

Prints the validation report and writes access_eval_report.json.
Exits 0 on PASS, 1 on FAIL.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agentic_stats.access import render_access_report, run_access_eval

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    result = run_access_eval()
    text = render_access_report(result)
    print(text, end="")
    with open(os.path.join(HERE, "access_eval_report.json"), "w") as fh:
        json.dump(result, fh, indent=2)
    return 0 if result["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
