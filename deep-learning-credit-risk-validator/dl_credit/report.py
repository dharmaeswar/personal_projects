"""Validation report: severity-rated findings and a PASS / FAIL verdict."""
import json


def build_report(candidate, challenger, benchmark, backtest, drift, integrity,
                 importance, n_train, n_test, segments=None,
                 implementation=None):
    """Assemble the report dict from the validation evidence."""
    findings = []

    if candidate["roc_auc"] < challenger["roc_auc"]:
        findings.append({
            "id": "F-01", "severity": "High",
            "text": "Deep-learning candidate does not beat the logistic challenger "
                    "on test ROC-AUC; a simpler model performs as well.",
        })
    if candidate["max_calibration_gap"] > 0.10:
        findings.append({
            "id": "F-02", "severity": "Medium",
            "text": "Largest decile calibration gap is above 0.10 — predicted "
                    "rates do not track realised rates in at least one decile.",
        })
    breached = [b for b in backtest if b["breach"]]
    if breached:
        findings.append({
            "id": "F-03", "severity": "High",
            "text": "Vintage backtest breach in "
                    + ", ".join(b["quarter"] for b in breached)
                    + " — predicted/observed default ratio outside [0.80, 1.25].",
        })
    worst_drift = max(drift, key=lambda r: r["psi"])
    if worst_drift["psi"] > 0.25:
        findings.append({
            "id": "F-04", "severity": "Medium",
            "text": "Score/feature drift PSI above 0.25 on "
                    + worst_drift["feature"]
                    + " between validation and later population.",
        })
    for issue in integrity:
        findings.append({
            "id": "F-05", "severity": issue["severity"],
            "text": "Data integrity: " + issue["check"] + " — "
                    + str(issue["count"]) + " rows affected.",
        })
    if candidate["roc_auc"] - benchmark["roc_auc"] < 0.05:
        findings.append({
            "id": "F-06", "severity": "Medium",
            "text": "Candidate barely beats the base-rate benchmark; check "
                    "whether the model adds real signal.",
        })

    impl = implementation or {}
    if impl.get("max_score_diff_vs_training_model", 0.0) > 1e-9:
        findings.append({
            "id": "F-07", "severity": "High",
            "text": "Implementation check failed: scores from the serialised "
                    "model artifact differ from the training model by %.2e — "
                    "the deployed artifact is not the validated model."
                    % impl["max_score_diff_vs_training_model"],
        })
    if impl.get("batch_rejected", 0) > 0:
        findings.append({
            "id": "F-08", "severity": "Medium",
            "text": "Implementation check: %d of %d batch records were "
                    "rejected by the input schema and not scored."
                    % (impl["batch_rejected"], impl.get("batch_n", 0)),
        })

    verdict = "PASS" if not any(f["severity"] == "High" for f in findings) else "FAIL"
    return {
        "model": "MLP deep-learning classifier (NumPy, 2 hidden layers) vs "
                 "logistic challenger vs base-rate benchmark",
        "n_train": n_train,
        "n_test": n_test,
        "candidate": candidate,
        "challenger": challenger,
        "benchmark": benchmark,
        "backtest": backtest,
        "drift": drift,
        "permutation_importance_top5": importance[:5],
        "segments": list(segments or []),
        "implementation": impl,
        "findings": findings,
        "verdict": verdict,
    }


def render_text(report):
    """Plain-text report, written to validation_report.txt."""
    lines = ["DEEP-LEARNING CREDIT-RISK MODEL — VALIDATION REPORT", ""]
    lines.append("Model: " + report["model"])
    lines.append("Train rows: %d   Test rows: %d" % (report["n_train"], report["n_test"]))
    lines.append("")
    lines.append("Outcomes (test split, threshold 0.5):")
    for label in ("candidate", "challenger", "benchmark"):
        m = report[label]
        lines.append(
            "  %-11s AUC %.4f  KS %.4f  Gini %.4f  Brier %.4f  "
            "precision %.3f  recall %.3f  F1 %.3f  top-decile capture %.1f%%"
            % (label, m["roc_auc"], m["ks"], m["gini"], m["brier"],
               m["precision"], m["recall"], m["f1"],
               100 * m["top_decile_capture"]))
    lines.append("")
    lines.append("Vintage backtest (predicted vs observed default rate):")
    for b in report["backtest"]:
        lines.append(
            "  %s  n=%d  predicted %.4f  observed %.4f  ratio %.2f%s"
            % (b["quarter"], b["n"], b["predicted_rate"], b["observed_rate"],
               b["ratio"], "  BREACH" if b["breach"] else ""))
    lines.append("")
    lines.append("Drift (PSI, validation vs later population):")
    for d in report["drift"]:
        flag = "  <-- above 0.25" if d["psi"] > 0.25 else ""
        lines.append("  %-24s %.4f%s" % (d["feature"], d["psi"], flag))
    lines.append("")
    lines.append("Top features by permutation importance (test AUC drop):")
    for row in report["permutation_importance_top5"]:
        lines.append("  %-24s %.4f" % (row["feature"], row["auc_drop"]))
    lines.append("")
    if report.get("segments"):
        lines.append("Segment backtest (k-means clusters, gap flagged above 0.10):")
        for s in report["segments"]:
            lines.append(
                "  segment %d  n=%d  mean score %d  predicted %.4f  observed %.4f  gap %.4f%s"
                % (s["segment"], s["n"], s["mean_credit_score"],
                   s["predicted_rate"], s["observed_rate"],
                   s["calibration_gap"], "  FLAGGED" if s["flagged"] else ""))
        lines.append("")
    impl = report.get("implementation") or {}
    if impl:
        lines.append("Implementation check (serialised artifact scoring path):")
        lines.append(
            "  batch of %d applications: %d scored, %d rejected by schema"
            % (impl["batch_n"], impl["batch_scored"], impl["batch_rejected"]))
        lines.append(
            "  max score diff vs training model: %.6f"
            % impl["max_score_diff_vs_training_model"])
        lines.append("  score bands (batch share vs reference book share):")
        for b in impl["bands"]:
            lines.append(
                "    %s  batch %.3f  reference %.3f  gap %.3f"
                % (b["band"], b["batch_share"], b["reference_share"],
                   b["share_gap"]))
        lines.append("")
    lines.append("Findings (%d):" % len(report["findings"]))
    if not report["findings"]:
        lines.append("  None — no finding breached a gate.")
    for f in report["findings"]:
        lines.append("  %s [%s] %s" % (f["id"], f["severity"], f["text"]))
    lines.append("")
    lines.append("Verdict: " + report["verdict"])
    return "\n".join(lines) + "\n"


def write_report(report, path_txt, path_json):
    with open(path_txt, "w", encoding="utf-8") as fh:
        fh.write(render_text(report))
    with open(path_json, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
