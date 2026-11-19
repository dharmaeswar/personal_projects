"""Report writer: JSON + human-readable text summary of an eval run."""

from __future__ import annotations

import json


def build_report(summaries, case_dicts, regression_verdict):
    return {"summaries": summaries, "cases": case_dicts,
            "regression": regression_verdict}


def write_json(report, path):
    with open(path, "w") as fh:
        json.dump(report, fh, indent=2)


def render_text(report):
    lines = ["Commercial Agent Eval Harness — evaluation report", ""]
    for summary in report["summaries"]:
        lines.append(
            f"{summary['agent']}: {summary['passed']}/{summary['total']} passed "
            f"(pass rate {summary['pass_rate']:.0%}, "
            f"latency {summary['total_latency_ms']}ms, "
            f"cost ${summary['total_cost_usd']:.6f})")
    lines.append("")
    for case in report["cases"]:
        mark = "PASS" if case["passed"] else "FAIL"
        lines.append(f"[{mark}] {case['case_id']} ({case['agent']}): "
                     f"expected {case['expected']}, got {case['actual']}, "
                     f"{case['latency_ms']}ms, ${case['cost_usd']:.6f}")
        for failure in case["failures"]:
            lines.append(f"       - {failure}")
    reg = report["regression"]
    lines.append("")
    lines.append(f"Regression vs baseline: {reg['verdict']} "
                 f"(pass rate {reg['baseline_pass_rate']:.0%} -> "
                 f"{reg['current_pass_rate']:.0%})")
    for item in reg["regressions"]:
        lines.append(f"  REGRESSION: {item}")
    for item in reg["improvements"]:
        lines.append(f"  IMPROVED: {item}")
    return "\n".join(lines) + "\n"
