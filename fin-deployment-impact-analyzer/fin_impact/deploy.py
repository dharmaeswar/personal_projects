"""Deployment readiness + measurement best practices.

Scores a customer's readiness for an enterprise Fin deployment from
checkable facts (volume, knowledge-base coverage, escalation paths,
measurement baseline), and produces the measurement plan the customer
is steered toward: which metrics, which baseline, and what "good"
looks like — the best-practice guidance a forward-deployed data
scientist gives on site.
"""

READINESS_CHECKS = (
    ("volume_baseline", "At least 4 weeks of pre-deployment volume logged", 25),
    ("kb_coverage", "Knowledge base covers the top 20 intents", 25),
    ("escalation_path", "Human escalation path defined and staffed", 20),
    ("csat_baseline", "CSAT baseline measured before go-live", 15),
    ("owner_named", "A customer owner is named for the deployment", 15),
)


def readiness_score(facts):
    """Score 0-100 from a dict of check name -> bool.

    Returns the score, the grade, and the checks still missing.
    """
    score = sum(w for name, _, w in READINESS_CHECKS if facts.get(name))
    missing = [label for name, label, _ in READINESS_CHECKS
               if not facts.get(name)]
    grade = ("ready" if score >= 80 else
             "ready_with_gaps" if score >= 60 else "not_ready")
    return {"score": score, "grade": grade, "missing": missing}


def measurement_plan(customer, baseline_weeks=4):
    """The measurement plan handed to the customer at kickoff."""
    return {
        "customer": customer,
        "baseline_weeks": baseline_weeks,
        "primary_metrics": ["resolution_rate", "mean_handle_minutes",
                            "escalation_rate"],
        "guardrail_metrics": ["mean_csat", "reopen_rate"],
        "cadence": "weekly for the first 8 weeks, then monthly",
        "success_rule": ("resolution_rate uplift with a 95% interval "
                         "above zero AND no CSAT drop"),
    }
