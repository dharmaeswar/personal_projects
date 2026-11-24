#!/usr/bin/env python3
"""Run the evidence-grounded draft evaluation scenarios.

Usage:
    python run_evidence_eval.py [--report evidence_report.json]

Evaluates each draft scenario in agent_eval.evidence.DRAFT_SCENARIOS
against a fresh evidence store, then demonstrates the review-feedback
loop: a reviewer correction boosts the corrected source, and a second
retrieval for the same query ranks that source first.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agent_eval.evidence import (DRAFT_SCENARIOS, DraftEvaluator,
                                 ReviewFeedback, build_store)

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", default="evidence_report.json")
    args = parser.parse_args()

    store = build_store()
    evaluator = DraftEvaluator(store, role="drafter")
    scenarios = {}
    for name, claims in DRAFT_SCENARIOS.items():
        result = evaluator.evaluate(claims)
        scenarios[name] = {
            "total": result["total"], "supported": result["supported"],
            "groundedness": result["groundedness"],
            "verdicts": [v.to_dict() for v in result["verdicts"]]}

    # Review-feedback loop: a reviewer correction approves SRC-STUDY-202;
    # retrieval for a query both sources match must now rank it first.
    before = [r["source_id"] for r in store.search(
        "BrandA tablets patients trial", role="drafter")]
    feedback = ReviewFeedback(
        "C1", "68 percent of patients reached the primary endpoint",
        "reviewer approved the trial citation for this brand",
        "SRC-STUDY-202", "BrandA")
    applied = feedback.apply(store)
    after = [r["source_id"] for r in store.search(
        "BrandA tablets patients trial", role="drafter")]

    report = {"scenarios": scenarios,
              "feedback_loop": {"retrieval_before": before,
                                "retrieval_after": after,
                                "applied": applied}}
    with open(os.path.join(HERE, args.report), "w") as fh:
        json.dump(report, fh, indent=2)

    for name, data in scenarios.items():
        print(f"{name}: {data['supported']}/{data['total']} supported, "
              f"groundedness {data['groundedness']}")
        for v in data["verdicts"]:
            print(f"  {v['claim_id']}: {v['verdict']} — {v['detail']}")
    print(f"feedback loop: retrieval before {before}, after {after}")
    print(f"report written to {args.report}")


if __name__ == "__main__":
    main()
