"""Evaluation harness: reproducibility, groundedness, and QC coverage.

Runs the workflow twice on the same seeded study and checks that the
results are identical (reproducibility), that every released claim is
grounded in computed numbers, and that QC rejects a sane share of
tiles (not everything, not nothing).
"""

from . import agent, data


def evaluate(seed=7, n_per_arm=6):
    """Run the checks. Returns a dict of named boolean checks + detail."""
    slides = data.make_study(n_per_arm=n_per_arm, seed=seed)
    first = agent.run_study(slides, "treated vs control", approve=True)
    slides2 = data.make_study(n_per_arm=n_per_arm, seed=seed)
    second = agent.run_study(slides2, "treated vs control", approve=True)

    reproducible = first["comparison"] == second["comparison"]
    grounded = len(first["rejected_claims"]) == 0
    qc_rates = []
    for s in first["summaries"].values():
        tissue = s["usable_tiles"] + s["rejected_tiles"]
        qc_rates.append(1.0 - s["rejected_tiles"] / max(tissue, 1))
    qc_sane = all(0.5 <= r <= 1.0 for r in qc_rates)
    released = first["status"] == "released"
    held = agent.run_study(
        data.make_study(n_per_arm=2, seed=seed),
        "treated vs control", approve=False)["status"] == \
        "held_for_human_review"
    checks = {
        "reproducible_same_seed": reproducible,
        "all_claims_grounded": grounded,
        "qc_pass_rate_sane": qc_sane,
        "approved_run_released": released,
        "unapproved_run_held": held,
    }
    return {"checks": checks,
            "passed": all(checks.values()),
            "comparison": first["comparison"],
            "n_claims": len(first["kept_claims"])}
