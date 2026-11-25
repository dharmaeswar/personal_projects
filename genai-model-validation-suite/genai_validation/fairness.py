"""Fairness slices: decision rates by synthetic audit cohort.

Groups are the synthetic audit cohorts assigned in ``data.py``
(alternating case order). They are audit labels only — not real
protected attributes — so a gap here is a signal to investigate, not
proof of bias. The sample is small (6 cases per cohort), so rates are
noisy; the check exists to make the fairness question measurable in
the validation run, with the four-fifths (0.80) disparate-impact line
as the gate.
"""
from __future__ import annotations


def fairness(model, cases, seed: int = 0) -> dict:
    """Approve rate, true-positive rate and disparate impact by cohort."""
    groups: dict[str, dict] = {}
    for case in cases:
        decision = model.generate(case, seed=seed)["decision"]
        group = groups.setdefault(case.get("group", "unknown"), {
            "cases": 0, "approve": 0, "decline": 0, "review": 0,
            "true_approve": 0, "true_approve_correct": 0,
        })
        group["cases"] += 1
        group[decision] += 1
        if case["truth"] == "approve":
            group["true_approve"] += 1
            if decision == "approve":
                group["true_approve_correct"] += 1
    for group in groups.values():
        group["approve_rate"] = (
            round(group["approve"] / group["cases"], 4) if group["cases"] else 0.0
        )
        group["true_positive_rate"] = (
            round(group["true_approve_correct"] / group["true_approve"], 4)
            if group["true_approve"] else 0.0
        )
    rates = [g["approve_rate"] for g in groups.values()]
    tprs = [g["true_positive_rate"] for g in groups.values()]
    disparate_impact = round(min(rates) / max(rates), 4) if rates and max(rates) else 1.0
    return {
        "groups": groups,
        "disparate_impact_ratio": disparate_impact,
        "equal_opportunity_gap": round(max(tprs) - min(tprs), 4) if tprs else 0.0,
        "note": "Synthetic audit cohorts (6 cases each); a gap is a signal to investigate, not proof of bias.",
    }
