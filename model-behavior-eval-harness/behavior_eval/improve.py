"""Harness-improvement loop: measure, fix, re-measure, verify.

The loop a behavior team runs when evals find a gap:

1. Run the eval suite against the current model -> baseline results.
2. Apply a fix (here: swap in the prompt-fixed model; in production a
   harness change, a prompt change, or a training-data change).
3. Re-run the same suite against the fixed model.
4. Paired comparison on the same cases: did the fix actually help, and
   did it break anything? A fix ships only when the paired test says
   IMPROVEMENT and the regression check finds no newly failing case.

The loop never trusts a raw delta: with small suites, a few cases of
movement is noise, and the paired McNemar test is what separates a real
fix from luck.
"""

from behavior_eval.dataset import load_cases
from behavior_eval.graders import grade_case
from behavior_eval.metrics import paired_comparison
from behavior_eval.regression import compare_runs


def run_loop(before_respond, after_respond, cases=None):
    """Run the improvement loop over ``cases`` (default: all cases).

    Returns a dict with both runs, the paired comparison, the regression
    check, and a ship/no-ship recommendation.
    """
    cases = cases if cases is not None else load_cases()
    before = [grade_case(c, before_respond(c)) for c in cases]
    after = [grade_case(c, after_respond(c)) for c in cases]
    comparison = paired_comparison(before, after)
    regression = compare_runs(before, after)
    fixed = [c for c in regression["newly_passing"]]
    broken = [c for c in regression["newly_failing"]]
    if comparison["verdict"] == "IMPROVEMENT" and not broken:
        recommendation = "SHIP FIX"
    elif broken:
        recommendation = "DO NOT SHIP -- fix broke cases: " + ", ".join(broken)
    else:
        recommendation = "DO NOT SHIP -- no significant improvement"
    return {"before": before, "after": after,
            "comparison": comparison, "regression": regression,
            "fixed_cases": fixed, "broken_cases": broken,
            "recommendation": recommendation}
