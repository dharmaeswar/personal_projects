"""Regression detection against a recorded baseline.

A launch gate needs a yes/no answer: did this model change make behavior
worse anywhere? This module compares a fresh run with a stored baseline
run (same cases, same order) and reports, per surface and overall:

- newly failing cases (passed in baseline, fail now) -> REGRESSION
- newly passing cases (failed in baseline, pass now) -> IMPROVEMENT
- per-surface pass-rate deltas with the paired verdict from metrics

A single newly failing case is a regression even if the overall rate went
up: aggregate rates hide per-case breakage, and a launch gate must not.
"""

import json

from behavior_eval.metrics import paired_comparison


def compare_runs(baseline_results, current_results):
    """Compare two runs over the same cases.

    Each run is a list of graded-case dicts (see graders.grade_case).
    Returns a dict with the verdict, case-level flips and per-surface
    paired comparisons.
    """
    base = {r["case_id"]: r for r in baseline_results}
    curr = {r["case_id"]: r for r in current_results}
    common = sorted(set(base) & set(curr))
    if not common:
        return {"verdict": "NO OVERLAP", "n_common": 0,
                "newly_failing": [], "newly_passing": [],
                "missing_in_current": sorted(set(base) - set(curr)),
                "new_in_current": sorted(set(curr) - set(base)),
                "surfaces": {}}
    newly_failing = [cid for cid in common
                     if base[cid]["passed"] and not curr[cid]["passed"]]
    newly_passing = [cid for cid in common
                     if not base[cid]["passed"] and curr[cid]["passed"]]
    surfaces = {}
    for surface in sorted({base[c]["surface"] for c in common}):
        ids = [c for c in common if base[c]["surface"] == surface]
        surfaces[surface] = paired_comparison(
            [base[c] for c in ids], [curr[c] for c in ids])
        surfaces[surface]["newly_failing"] = [c for c in newly_failing
                                              if base[c]["surface"] == surface]
        surfaces[surface]["newly_passing"] = [c for c in newly_passing
                                              if base[c]["surface"] == surface]
    overall = paired_comparison([base[c] for c in common],
                                [curr[c] for c in common])
    if newly_failing:
        verdict = "REGRESSION"
    elif overall["verdict"] == "IMPROVEMENT":
        verdict = "IMPROVEMENT"
    else:
        verdict = overall["verdict"]
    return {"verdict": verdict, "n_common": len(common),
            "newly_failing": newly_failing,
            "newly_passing": newly_passing,
            "missing_in_current": sorted(set(base) - set(curr)),
            "new_in_current": sorted(set(curr) - set(base)),
            "overall": overall, "surfaces": surfaces}


def load_baseline(path):
    """Load a baseline run file written by run_evaluation.py."""
    with open(path) as f:
        data = json.load(f)
    return data["results"]


def save_baseline(path, results, summary):
    """Write a baseline run file (results + summary)."""
    with open(path, "w") as f:
        json.dump({"results": results, "summary": summary}, f, indent=2)
