"""Severity-rated findings, risk-rating recommendation, SR 26-2 report."""

FINDING_SEVERITY = {"High": 3, "Medium": 2, "Low": 1}


def build_findings(outcomes, backtest, psi_value, drift, data_issues,
                   reproduced, challenger_better, gbm_better=False,
                   experiment_significant=False):
    """Findings follow SR 26-2 validation practice: each finding names the
    evidence, the impact, and a severity the model owner must remediate."""
    findings = []
    if outcomes["auc"] < 0.70:
        findings.append(("High", "Weak rank-ordering: champion AUC %.3f is "
                         "below the 0.70 floor for an underwriting model."
                         % outcomes["auc"]))
    elif outcomes["auc"] < 0.75:
        findings.append(("Medium", "Modest rank-ordering: champion AUC %.3f; "
                         "challenger reaches %.3f, so the methodology leaves "
                         "discrimination on the table."
                         % (outcomes["auc"], outcomes["challenger_auc"])))
    breached = [q for q, v in backtest.items() if v["breach"]]
    if breached:
        findings.append(("High", "Backtest breach in %s: predicted-to-observed "
                         "default ratio outside [0.80, 1.25]; loss forecasts "
                         "built on these PDs would misstate reserves."
                         % ", ".join(breached)))
    if psi_value >= 0.25:
        findings.append(("High", "Material population shift: PSI %.3f (>= 0.25); "
                         "the production book no longer matches validation."
                         % psi_value))
    elif psi_value >= 0.10:
        findings.append(("Medium", "Moderate population shift: PSI %.3f; "
                         "monitoring should move to monthly until it settles."
                         % psi_value))
    if abs(drift) >= 0.10:
        findings.append(("Medium", "Mean score drift %.1f%% vs validation; "
                         "re-check the score distribution before the next "
                         "quarterly review." % (drift * 100)))
    if data_issues:
        findings.append(("Medium", "Input data gaps: " + "; ".join(data_issues)))
    if not reproduced:
        findings.append(("High", "Developer code does not reproduce: refit "
                         "outputs differ beyond tolerance; implementation "
                         "evidence is incomplete."))
    if challenger_better:
        findings.append(("Low", "Challenger beats champion on AUC; consider "
                         "adopting the interaction terms at the next "
                         "redevelopment, not as a blocking change."))
    if gbm_better:
        if experiment_significant:
            findings.append(("Low", "Gradient-boosting challenger beats the "
                             "champion on AUC and the bootstrap 95% CI for the "
                             "gain excludes zero; evaluate it for adoption at "
                             "the next redevelopment."))
        else:
            findings.append(("Low", "Gradient-boosting challenger beats the "
                             "champion on AUC, but the bootstrap 95% CI for the "
                             "gain includes zero, so the gain is not proven."))
    if not findings:
        findings.append(("Low", "No material findings: outcomes, backtest, "
                         "monitoring and data checks all pass."))
    return findings


def recommend_rating(findings):
    """Independent risk-rating recommendation from finding severities."""
    worst = max((FINDING_SEVERITY[s] for s, _ in findings), default=1)
    if worst >= 3:
        return "High"
    if worst == 2:
        return "Medium"
    return "Low"


def render_report(results):
    lines = []
    lines.append("INDEPENDENT MODEL VALIDATION REPORT")
    lines.append("Small-Business Credit Underwriting Model (champion: logistic regression)")
    lines.append("Framework: interagency model risk management guidance (SR 26-2)")
    lines.append("Scope: conceptual soundness, outcomes analysis, backtesting,")
    lines.append("  monitoring, data integrity, implementation reproduction, challenger model.")
    lines.append("")
    lines.append("1. CONCEPTUAL SOUNDNESS")
    lines.append("   Methodology: logistic regression on revenue, years in business,")
    lines.append("   cash-flow coverage, credit score, loan amount, industry risk.")
    lines.append("   Limitation: no interaction terms; coverage and score effects are")
    lines.append("   assumed additive. Management adjustment: none applied.")
    lines.append("")
    lines.append("2. OUTCOMES ANALYSIS (validation sample, n=%d)" % results["n"])
    lines.append("   Champion AUC %.3f | KS %.3f | Gini %.3f"
                 % (results["auc"], results["ks"], results["gini"]))
    lines.append("   Challenger AUC %.3f | KS %.3f"
                 % (results["challenger_auc"], results["challenger_ks"]))
    if "gbm_auc" in results:
        lines.append("   Gradient-boosting challenger AUC %.3f | KS %.3f"
                     % (results["gbm_auc"], results["gbm_ks"]))
    if "experiment" in results:
        exp = results["experiment"]
        ll = results["logloss"]
        lines.append("   Experiment: GBM vs champion AUC diff %.3f "
                     "(95%% CI %.3f to %.3f, %d bootstrap draws)"
                     % (exp["mean_diff"], exp["ci_lo"], exp["ci_hi"],
                        exp["n_boot"]))
        lines.append("   Paired log-loss test: mean diff %.4f, z %.3f, "
                     "p %.4f; rollout needs %d loans per arm to detect a "
                     "1pp default-rate change"
                     % (ll["mean_diff"], ll["z"], ll["p_value"],
                        results["rollout_n"]))
    lines.append("   Top decile captures %.1f%% of defaults; bottom decile %.1f%%."
                 % (results["deciles"][0] * 100, results["deciles"][-1] * 100))
    lines.append("   At t=0.5: precision %.3f, recall %.3f, F1 %.3f"
                 % (results["confusion"]["precision"], results["confusion"]["recall"],
                    results["confusion"]["f1"]))
    lines.append("")
    lines.append("3. BACKTESTING (vintage, by origination quarter)")
    for q, v in results["backtest"].items():
        flag = " BREACH" if v["breach"] else ""
        lines.append("   %s n=%d predicted %.3f observed %.3f ratio %.2f%s"
                     % (q, v["n"], v["predicted"], v["observed"], v["ratio"], flag))
    lines.append("")
    lines.append("4. ONGOING MONITORING")
    lines.append("   PSI %.3f (0.10 watch, 0.25 action); mean score drift %.1f%%"
                 % (results["psi"], results["drift"] * 100))
    lines.append("")
    lines.append("5. DATA INTEGRITY & IMPLEMENTATION")
    lines.append("   Data issues: %s" % (", ".join(results["data_issues"])
                                          or "none found"))
    lines.append("   Developer code reproduced: %s (max abs diff %.4f)"
                 % (results["reproduced"], results["max_diff"]))
    lines.append("")
    lines.append("6. FINDINGS (severity-rated)")
    for sev, text in results["findings"]:
        lines.append("   [%s] %s" % (sev, text))
    lines.append("")
    lines.append("7. RISK RATING & VERDICT")
    lines.append("   Recommended risk rating: %s (owner proposed: %s)"
                 % (results["rating"], results["owner_rating"]))
    lines.append("   Verdict: %s" % results["verdict"])
    return "\n".join(lines) + "\n"
