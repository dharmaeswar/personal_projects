"""Regression reports and release gates over eval runs.

A fresh eval run is compared with the stored baseline (baseline.json):
a newly failing case, a missing case, or latency/cost growth over 10%
is a REGRESSION. The release gate blocks a rollout when the pass rate
falls below the threshold, any human-reviewed case newly fails, or the
failure-handling case stops declining to answer.
"""

from __future__ import annotations

import json
import os

PASS_RATE_THRESHOLD = 0.875  # 7 of 8 scored cases
GROWTH_THRESHOLD = 0.10  # 10% latency/cost growth vs baseline is a regression


def compare_to_baseline(results: dict, baseline: dict | None) -> dict:
    """Compare a fresh run with the baseline; list regressions."""
    regressions = []
    if baseline is None:
        return {"baseline_present": False, "regressions": regressions}
    base_by_id = {c["id"]: c for c in baseline.get("cases", [])}
    for case in results["cases"]:
        base = base_by_id.get(case["id"])
        if base is None:
            regressions.append(f"new case with no baseline: {case['id']}")
            continue
        if base.get("passed") and not case["passed"]:
            regressions.append(f"newly failing case: {case['id']}")
        for metric in ("latency_ms", "cost_usd"):
            old = base.get(metric, 0) or 0
            new = case.get(metric, 0) or 0
            if old > 0 and (new - old) / old > GROWTH_THRESHOLD:
                regressions.append(
                    f"{case['id']}: {metric} grew "
                    f"{(new - old) / old:.0%} over baseline")
    for case_id in base_by_id:
        if case_id not in {c["id"] for c in results["cases"]}:
            regressions.append(f"missing case (was in baseline): {case_id}")
    return {"baseline_present": True, "regressions": regressions}


def release_gate(results: dict, baseline: dict | None) -> dict:
    """Decide whether this eval run may ship. Returns gate + reasons."""
    reasons = []
    if results["pass_rate"] < PASS_RATE_THRESHOLD:
        reasons.append(
            f"pass rate {results['pass_rate']:.3f} below "
            f"threshold {PASS_RATE_THRESHOLD}")
    for case in results["cases"]:
        if case["human_reviewed"] and not case["passed"]:
            reasons.append(f"human-reviewed case failed: {case['id']}")
    if not results["failure_handling"]["passed"]:
        reasons.append(
            "failure-handling case did not decline to answer "
            "(agent answered an unanswerable question)")
    comparison = compare_to_baseline(results, baseline)
    reasons.extend(comparison["regressions"])
    return {
        "gate": "PASS" if not reasons else "BLOCKED",
        "reasons": reasons,
        "pass_rate": results["pass_rate"],
        "regressions": comparison["regressions"],
    }


def load_baseline(path: str) -> dict | None:
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def save_baseline(results: dict, path: str) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(results, fh, indent=2)
