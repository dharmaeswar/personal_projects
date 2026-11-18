"""Three agents that run the analytics pipeline, plus the validator.

* PlannerAgent — turns the analysis question into an ordered plan of steps.
* AnalystAgent — executes the plan with fast, naive statistics and states
  claims (the way an unchecked agent would: one p-value per claim, no
  correction, no power check).
* ValidatorAgent — independently re-tests every claim with the full
  statistical toolkit: Welch's t-test, chi-square, bootstrap CIs, effect
  sizes, Bonferroni correction across all claims, and a power check. A claim
  only passes when it survives all of that.
"""

from . import stats


class PlannerAgent:
    """Plans the analysis: which outcomes, which tests, in which order."""

    def plan(self, question):
        steps = [
            {"step": 1, "action": "summarise",
             "detail": "Descriptive statistics per arm for each outcome."},
            {"step": 2, "action": "primary-test",
             "detail": "Welch t-test on the primary outcome, treatment vs control."},
            {"step": 3, "action": "secondary-test",
             "detail": "Welch t-test on the secondary outcome, treatment vs control."},
            {"step": 4, "action": "responder-test",
             "detail": "Chi-square test on responder rates by arm."},
            {"step": 5, "action": "subgroup-test",
             "detail": "Welch t-test on the primary outcome within the high-baseline subgroup."},
            {"step": 6, "action": "validate",
             "detail": "Re-test every claim with corrections, CIs and power checks."},
        ]
        return {"question": question, "steps": steps}


class AnalystAgent:
    """Runs the plan and states claims from uncorrected p-values."""

    def analyse(self, rows):
        from .data import split_arms

        control, treatment = split_arms(rows)
        claims = []

        primary_c = [r["primary"] for r in control]
        primary_t = [r["primary"] for r in treatment]
        test = stats.welch_t_test(primary_t, primary_c)
        claims.append({
            "id": "C1", "text": "Treatment improves the primary outcome.",
            "p": test["p"], "test": "welch-t", "statistic": test["t"],
        })

        secondary_c = [r["secondary"] for r in control]
        secondary_t = [r["secondary"] for r in treatment]
        test = stats.welch_t_test(secondary_t, secondary_c)
        claims.append({
            "id": "C2", "text": "Treatment improves the secondary outcome.",
            "p": test["p"], "test": "welch-t", "statistic": test["t"],
        })

        resp_t = sum(1 for r in treatment if r["responder"])
        resp_c = sum(1 for r in control if r["responder"])
        table = [[resp_t, len(treatment) - resp_t],
                 [resp_c, len(control) - resp_c]]
        test = stats.chi_square_test(table)
        claims.append({
            "id": "C3", "text": "Treatment raises the responder rate.",
            "p": test["p"], "test": "chi-square", "statistic": test["chi2"],
        })

        sub_c = [r["primary"] for r in control if r["subgroup"] == "high-baseline"]
        sub_t = [r["primary"] for r in treatment if r["subgroup"] == "high-baseline"]
        test = stats.welch_t_test(sub_t, sub_c)
        claims.append({
            "id": "C4",
            "text": "Treatment helps high-baseline participants even more.",
            "p": test["p"], "test": "welch-t", "statistic": test["t"],
        })
        return claims


class ValidatorAgent:
    """Re-tests each claim with corrections, CIs, effect sizes and power."""

    def __init__(self, alpha=0.05):
        self.alpha = alpha

    def validate(self, rows, claims):
        from .data import split_arms

        control, treatment = split_arms(rows)
        decisions = stats.bonferroni([c["p"] for c in claims], self.alpha)
        results = []

        for claim, survives in zip(claims, decisions):
            detail = {"id": claim["id"], "text": claim["text"],
                      "raw_p": claim["p"], "bonferroni_pass": survives,
                      "verdict": "PASS" if survives else "FAIL"}
            if claim["id"] in ("C1", "C2"):
                key = "primary" if claim["id"] == "C1" else "secondary"
                a = [r[key] for r in treatment]
                b = [r[key] for r in control]
                lo, hi = stats.bootstrap_ci_mean_diff(a, b)
                d = stats.cohens_d(a, b)
                power = stats.power_two_sample(abs(d), len(a))
                detail["ci_95"] = (round(lo, 2), round(hi, 2))
                detail["cohens_d"] = round(d, 3)
                detail["power"] = round(power, 3)
                # A claim also fails if the CI includes zero or power is low.
                if lo <= 0 <= hi:
                    detail["verdict"] = "FAIL"
                    detail["reason"] = "95% CI includes zero"
                elif power < 0.80:
                    detail["verdict"] = "FAIL"
                    detail["reason"] = "underpowered (power < 0.80)"
                elif not survives:
                    detail["reason"] = "fails Bonferroni correction"
            if claim["id"] == "C4":
                # "Even more" is an interaction claim: the subgroup effect must
                # exceed the effect in the rest of the sample. Test it directly.
                th = [r["primary"] for r in treatment if r["subgroup"] == "high-baseline"]
                ch = [r["primary"] for r in control if r["subgroup"] == "high-baseline"]
                tl = [r["primary"] for r in treatment if r["subgroup"] == "low-baseline"]
                cl = [r["primary"] for r in control if r["subgroup"] == "low-baseline"]
                inter = stats.interaction_t_test(th, ch, tl, cl)
                detail["interaction_p"] = round(inter["p"], 4)
                detail["interaction"] = round(inter["interaction"], 2)
                if inter["p"] >= self.alpha:
                    detail["verdict"] = "FAIL"
                    detail["reason"] = "no interaction: subgroup effect matches the overall effect"
                elif not survives:
                    detail["reason"] = "fails Bonferroni correction"
            if claim["id"] == "C3":
                resp_t = sum(1 for r in treatment if r["responder"]) / len(treatment)
                resp_c = sum(1 for r in control if r["responder"]) / len(control)
                detail["responder_rate_treatment"] = round(resp_t, 3)
                detail["responder_rate_control"] = round(resp_c, 3)
                if not survives:
                    detail["reason"] = "fails Bonferroni correction"
            results.append(detail)
        return results
