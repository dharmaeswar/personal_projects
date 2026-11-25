"""Eval harness: run a self-serve eval spec against a model.

Other teams define their own evals without touching harness code: a spec
is a JSON file naming the surfaces, the case filter, the pass threshold
and the graders to run. The harness loads the spec, runs the model over
the matching cases, grades each response, and returns results plus a
summary with bootstrap confidence intervals.

Spec format (see evals/*.json)::

    {
      "name": "support-answers",
      "description": "...",
      "surfaces": ["support"],
      "case_ids": null,            // null = all cases on those surfaces
      "min_pass_rate": 0.9,        // launch gate threshold
      "graders": ["groundedness", "completeness", "refusal",
                  "format", "llm_judge"]
    }
"""

import json

from behavior_eval.dataset import load_cases
from behavior_eval.graders import grade_case
from behavior_eval.metrics import summarize


def load_spec(path):
    """Load and validate a self-serve eval spec from JSON."""
    with open(path) as f:
        spec = json.load(f)
    required = ("name", "surfaces", "min_pass_rate")
    for key in required:
        if key not in spec:
            raise ValueError(f"spec {path} is missing required key: {key}")
    spec.setdefault("case_ids", None)
    spec.setdefault("graders", ["groundedness", "completeness", "refusal",
                                "format", "llm_judge"])
    spec.setdefault("description", "")
    return spec


def run_eval(spec, respond):
    """Run one spec: call ``respond(case)`` per case, grade, summarize.

    ``respond`` is any callable taking a case dict and returning a
    response string -- a stand-in model here, a real model client in
    production. Returns (results, summary, gate) where gate is PASS/FAIL
    against the spec's min_pass_rate.
    """
    cases = load_cases()
    wanted_surfaces = set(spec["surfaces"])
    cases = [c for c in cases if c["surface"] in wanted_surfaces]
    if spec.get("case_ids"):
        wanted = set(spec["case_ids"])
        cases = [c for c in cases if c["id"] in wanted]
    results = []
    for case in cases:
        response = respond(case)
        graded = grade_case(case, response)
        wanted_graders = set(spec["graders"])
        graded["graders"] = {k: v for k, v in graded["graders"].items()
                             if k in wanted_graders}
        graded["passed"] = all(r["passed"]
                               for r in graded["graders"].values())
        results.append(graded)
    summary = summarize(results)
    gate = "PASS" if summary["pass_rate"] >= spec["min_pass_rate"] else "FAIL"
    return results, summary, gate


def report_text(name, summary, gate, min_pass_rate):
    """Plain-text summary of one eval run."""
    lines = [f"Eval: {name}  (gate: min pass rate {min_pass_rate:.2f})",
             f"Gate: {gate}",
             f"Overall: {summary['n']} cases, "
             f"pass rate {summary['pass_rate']:.3f}, "
             f"95% CI {summary['ci_95']}"]
    for surface, s in sorted(summary["surfaces"].items()):
        lines.append(f"  {surface}: {s['n']} cases, "
                     f"pass rate {s['pass_rate']:.3f}, CI {s['ci_95']}, "
                     f"failed: {s['failed'] or 'none'}")
    return "\n".join(lines)
