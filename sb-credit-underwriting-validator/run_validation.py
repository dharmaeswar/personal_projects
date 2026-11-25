"""Run the independent validation of the small-business underwriting model.

Prints the SR 26-2-style validation report and writes validation_report.txt.
All data is synthetic and seeded.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sb_credit_validator.data import generate_portfolio
from sb_credit_validator.models import LogisticModel
from sb_credit_validator.outcomes import (
    roc_auc, ks_statistic, gini, decile_capture, confusion_at_threshold)
from sb_credit_validator.validation import (
    vintage_backtest, psi, score_drift, data_completeness_checks,
    reproduction_check)
from sb_credit_validator.report import (
    build_findings, recommend_rating, render_report)


def run():
    loans = generate_portfolio(n=4000, seed=42)
    production = generate_portfolio(n=2000, seed=7, drift=True)
    y = [l["defaulted"] for l in loans]

    champion = LogisticModel(interactions=False).fit(loans)
    challenger = LogisticModel(interactions=True).fit(loans)
    champ_scores = champion.predict_proba(loans)
    chal_scores = challenger.predict_proba(loans)

    # Independent reproduction: re-fit the developer model from scratch.
    refit = LogisticModel(interactions=False).fit(loans)
    repro = reproduction_check(champ_scores, refit.predict_proba(loans))

    backtest = vintage_backtest(loans, champ_scores)
    prod_scores = champion.predict_proba(production)
    psi_value = psi(champ_scores, prod_scores)
    drift = score_drift(champ_scores, prod_scores)
    data_issues = data_completeness_checks(loans)

    outcomes = {
        "auc": roc_auc(y, champ_scores),
        "ks": ks_statistic(y, champ_scores),
        "gini": gini(y, champ_scores),
        "challenger_auc": roc_auc(y, chal_scores),
        "challenger_ks": ks_statistic(y, chal_scores),
    }
    challenger_better = outcomes["challenger_auc"] > outcomes["auc"] + 0.005
    findings = build_findings(outcomes, backtest, psi_value, drift,
                              data_issues, repro["reproduced"],
                              challenger_better)
    rating = recommend_rating(findings)
    high = any(s == "High" for s, _ in findings)
    verdict = ("CONDITIONAL PASS — approve for use once High findings are "
               "remediated" if high else "PASS — approve for use")

    results = {
        "n": len(loans),
        "auc": outcomes["auc"],
        "ks": outcomes["ks"],
        "gini": outcomes["gini"],
        "challenger_auc": outcomes["challenger_auc"],
        "challenger_ks": outcomes["challenger_ks"],
        "deciles": decile_capture(y, champ_scores),
        "confusion": confusion_at_threshold(y, champ_scores),
        "backtest": backtest,
        "psi": psi_value,
        "drift": drift,
        "data_issues": data_issues,
        "reproduced": repro["reproduced"],
        "max_diff": repro["max_abs_diff"],
        "findings": findings,
        "rating": rating,
        "owner_rating": "Medium",
        "verdict": verdict,
    }
    text = render_report(results)
    print(text)
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "validation_report.txt"), "w") as f:
        f.write(text)
    return results


if __name__ == "__main__":
    run()
