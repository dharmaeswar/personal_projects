"""Model monitoring for the marketing mix model: drift and error checks.

A production ML system is not done when it is fit — it has to be watched.
This module is the monitoring half of the T-Ads Senior Data Scientist work:
it checks whether new weeks still look like the weeks the MMM was trained
on (distribution shift) and whether the model's predictions on new weeks
are still as good as they were on the holdout (prediction drift). Either
kind of drift is flagged with the evidence, and the verdict is one of
OK / WATCH / RETRAIN — never a silent pass.

The demo runs this on the MMM's own 12 holdout weeks standing in for new
production weeks, so the numbers below are a monitoring dry run on known
data, not a claim about a live system. In production the same functions
would run on genuinely new weeks.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

# A standardised mean shift this large, or a t-test this significant, is a
# distribution flag. The prediction flag fires when new-week MAPE is more
# than twice the holdout MAPE, or above 5% in absolute terms.
SHIFT_THRESHOLD = 0.5
P_VALUE_THRESHOLD = 0.05
MAPE_RATIO_THRESHOLD = 2.0
MAPE_ABSOLUTE_THRESHOLD = 0.05


def compare_distributions(reference, current, columns):
    """Compare one column at a time between reference and current weeks.

    Returns a list of per-column dicts: means, standardised shift
    (Cohen's d style, pooled standard deviation), Welch's t-test p-value,
    and whether the column is flagged.
    """
    rows = []
    for col in columns:
        ref = np.asarray(reference[col], dtype=float)
        cur = np.asarray(current[col], dtype=float)
        ref_mean, cur_mean = float(np.mean(ref)), float(np.mean(cur))
        ref_std, cur_std = float(np.std(ref, ddof=1)), float(np.std(cur, ddof=1))
        pooled = float(np.sqrt((ref_std ** 2 + cur_std ** 2) / 2))
        shift = (cur_mean - ref_mean) / pooled if pooled > 0 else 0.0
        _, p_value = stats.ttest_ind(ref, cur, equal_var=False)
        flagged = abs(shift) > SHIFT_THRESHOLD or p_value < P_VALUE_THRESHOLD
        rows.append({
            "column": col,
            "reference_mean": round(ref_mean, 2),
            "current_mean": round(cur_mean, 2),
            "standardised_shift": round(float(shift), 3),
            "p_value": round(float(p_value), 4),
            "flagged": bool(flagged),
        })
    return rows


def monitor_predictions(y_true, y_pred, holdout_mape):
    """Check new-week prediction error against the holdout baseline."""
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    mape = float(np.mean(np.abs(y_true - y_pred) / np.abs(y_true)))
    ratio = mape / holdout_mape if holdout_mape > 0 else float("inf")
    flagged = ratio > MAPE_RATIO_THRESHOLD or mape > MAPE_ABSOLUTE_THRESHOLD
    return {
        "new_mape": round(mape, 4),
        "holdout_mape": round(float(holdout_mape), 4),
        "mape_ratio": round(float(ratio), 2),
        "flagged": bool(flagged),
    }


def monitor_mmm(mmm_result, train_df, new_df):
    """Run both drift checks for the fitted MMM on new weeks.

    ``train_df`` is the training window, ``new_df`` the new weeks, both
    with the same weekly columns. Returns the distribution rows, the
    prediction check, and a verdict: OK (no flags), WATCH (distribution
    flags only), RETRAIN (prediction error has drifted).
    """
    from .mmm import build_features

    spend_cols = [f"spend_{ch}" for ch in
                  ["paid_search", "paid_social", "display", "video", "email"]]
    columns = spend_cols + ["seasonality", "sales"]
    distribution = compare_distributions(train_df, new_df, columns)

    # Build features on the concatenated series, not on the new weeks alone:
    # adstock carries spend over from earlier weeks, so slicing first would
    # silently reset the carryover and misstate the predictions.
    combined = pd.concat([train_df, new_df], ignore_index=True)
    X_all, y_all = build_features(combined)
    n_train = len(train_df)
    X_new, y_new = X_all.iloc[n_train:], y_all[n_train:]
    y_pred = mmm_result["model"].predict(X_new)
    predictions = monitor_predictions(y_new, y_pred, mmm_result["mape_holdout"])

    n_dist_flags = sum(1 for r in distribution if r["flagged"])
    if predictions["flagged"]:
        verdict = "RETRAIN"
    elif n_dist_flags:
        verdict = "WATCH"
    else:
        verdict = "OK"
    return {
        "distribution": distribution,
        "distribution_flags": n_dist_flags,
        "predictions": predictions,
        "verdict": verdict,
    }


def monitoring_summary_lines(result):
    """Render the monitoring result as report lines."""
    pred = result["predictions"]
    lines = [
        f"Verdict: {result['verdict']} — "
        f"{result['distribution_flags']} distribution flag(s), "
        f"new-week MAPE {pred['new_mape']:.1%} vs holdout "
        f"{pred['holdout_mape']:.1%} (ratio {pred['mape_ratio']}x).",
    ]
    for row in result["distribution"]:
        mark = "FLAG" if row["flagged"] else "ok"
        lines.append(
            f"- {row['column']}: {row['reference_mean']} -> "
            f"{row['current_mean']} (shift {row['standardised_shift']}, "
            f"p = {row['p_value']}) [{mark}]"
        )
    return lines
