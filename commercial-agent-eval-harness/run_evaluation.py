#!/usr/bin/env python3
"""Run both agent eval suites, compare with the baseline, write the report.

Usage:
    python run_evaluation.py [--record-baseline]

Without --record-baseline, the run is compared with baseline.json and the
verdict is PASS or REGRESSION. With --record-baseline, the fresh results
overwrite baseline.json (use only when the behaviour change is intended).
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agent_eval import (INVOICE_CASES, TRIAGE_CASES, InvoiceAgent,
                        SupportTriageAgent, ToolServer, Tracer, build_report,
                        compare, load_baseline, render_text, run_suite,
                        write_json)

HERE = os.path.dirname(os.path.abspath(__file__))
BASELINE_PATH = os.path.join(HERE, "baseline.json")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--record-baseline", action="store_true")
    args = parser.parse_args()

    tools = ToolServer(Tracer())
    invoice_results, invoice_summary = run_suite(InvoiceAgent(tools), INVOICE_CASES)
    triage_results, triage_summary = run_suite(SupportTriageAgent(tools), TRIAGE_CASES)
    all_cases = [r.to_dict() for r in invoice_results + triage_results]
    total = len(all_cases)
    passed = sum(1 for c in all_cases if c["passed"])
    current = {"pass_rate": round(passed / total, 4) if total else 0.0,
               "total": total, "passed": passed, "cases": all_cases}

    if args.record_baseline or not os.path.exists(BASELINE_PATH):
        with open(BASELINE_PATH, "w") as fh:
            json.dump(current, fh, indent=2)
        regression = {"verdict": "BASELINE RECORDED",
                      "baseline_pass_rate": current["pass_rate"],
                      "current_pass_rate": current["pass_rate"],
                      "pass_rate_delta": 0.0, "regressions": [],
                      "improvements": []}
    else:
        baseline = load_baseline(BASELINE_PATH)
        regression = compare(baseline, current)

    report = build_report([invoice_summary, triage_summary], all_cases, regression)
    write_json(report, os.path.join(HERE, "evaluation_report.json"))
    with open(os.path.join(HERE, "evaluation_report.txt"), "w") as fh:
        fh.write(render_text(report))
    print(render_text(report))
    return 0 if regression["verdict"] in ("PASS", "BASELINE RECORDED") else 1


if __name__ == "__main__":
    raise SystemExit(main())
