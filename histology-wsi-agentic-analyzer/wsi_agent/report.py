"""Formal analytic protocol + findings report for a study run."""

PROTOCOL_TEMPLATE = """ANALYTIC PROTOCOL — {question}
Study arms: treated (n={n_treated}) vs control (n={n_control})
Steps: {steps}
Preprocessing: tissue detection, stain normalisation to reference {reference},
QC rejects out-of-focus, empty, or stain-outlier tiles.
Features: deterministic 6-feature tile vector (stand-in for a vision
foundation model embedding; a model plugs into extract_features()).
Statistics: Welch's t-test on per-slide mean tile scores, Cohen's d.
Release rule: findings release only after human approval; the reviewer
rejects any claim whose numbers are not in the computed results.
"""


def protocol_text(question, n_treated, n_control, steps):
    """The formal protocol text for a run (authored before analysis)."""
    return PROTOCOL_TEMPLATE.format(
        question=question, n_treated=n_treated, n_control=n_control,
        steps=", ".join(steps), reference="(128.0, 148.0)")


def report_text(question, result):
    """Plain-language findings report from a completed run."""
    comp = result["comparison"]
    lines = [
        f"Findings — {question}",
        f"Slides analysed: {len(result['summaries'])}.",
        f"Mean tile score: treated {comp['mean_a']} vs control "
        f"{comp['mean_b']}.",
        f"Welch t={comp['t']}, df={comp['df']}, p={comp['p_value']}; "
        f"Cohen's d={comp['cohens_d']}.",
        f"Claims kept after review: {len(result['kept_claims'])}; "
        f"rejected as ungrounded: {len(result['rejected_claims'])}.",
        f"Release status: {result['status']}.",
        "",
        "Kept claims:",
    ]
    lines += [f"- {c}" for c in result["kept_claims"]]
    return "\n".join(lines) + "\n"
