"""Transaction-risk scoring analytics for a Stripe Radar-style role.

Extends the fraud-model validation suite with the checks a transaction-risk
ML team runs in production:

- transaction feature engineering (velocity ratios, night/new-device flags,
  cross-border x card-not-present interaction, amount z-score),
- delayed-label evaluation (fraud labels mature only after chargebacks
  arrive, so naive evaluation on all rows understates performance),
- adversarial pattern checks (fraud-share shifts by segment between a
  baseline and a recent period, the signature of adapting fraud),
- model-quality vs latency trade-off (measured per-transaction scoring
  latency for champion vs challenger),
- model-regression monitoring (current-period metrics vs baseline, with
  per-metric tolerances and PASS/REGRESSION verdicts).

All data is synthetic and seeded. No real cardholder, merchant, or
transaction data is used, and nothing here is a claim about any real system.
"""

from __future__ import annotations

import time

import numpy as np
import pandas as pd

from fraud_validation.metrics import roc_auc

RNG_SEED = 123
N_EVENT_DAYS = 60
MATURATION_DAYS = 30

# Feature columns added by build_transaction_features.
RISK_FEATURES = [
    "log_amount",
    "night",
    "new_device",
    "velocity_ratio",
    "cross_border_cnp",
    "amount_zscore",
]


def build_transaction_features(df: pd.DataFrame) -> pd.DataFrame:
    """Engineer transaction-risk features from the raw transaction columns.

    ``log_amount`` compresses the heavy-tailed amount; ``night`` flags
    23:00-04:59 transactions; ``new_device`` flags devices under 30 days
    old; ``velocity_ratio`` is 1h velocity over 24h velocity (a burst
    signal); ``cross_border_cnp`` is the cross-border x card-not-present
    interaction; ``amount_zscore`` standardises log amount within the frame.
    """
    out = df.copy()
    log_amount = np.log1p(out["amount"].to_numpy(dtype=float))
    out["log_amount"] = np.round(log_amount, 4)
    out["night"] = ((out["hour"] < 5) | (out["hour"] >= 23)).astype(int)
    out["new_device"] = (out["device_age_days"] < 30).astype(int)
    out["velocity_ratio"] = np.round(
        out["velocity_1h"].to_numpy(dtype=float)
        / (out["velocity_24h"].to_numpy(dtype=float) + 1.0),
        4,
    )
    out["cross_border_cnp"] = (
        out["cross_border"] * (1 - out["card_present"])
    ).astype(int)
    mean, std = float(log_amount.mean()), float(log_amount.std())
    out["amount_zscore"] = np.round((log_amount - mean) / std, 4) if std else 0.0
    return out


def add_event_days(
    df: pd.DataFrame, n_days: int = N_EVENT_DAYS, seed: int = RNG_SEED
) -> pd.DataFrame:
    """Attach a seeded synthetic event day (0..n_days-1) to each row.

    Event days give the frame a time axis so delayed-label and
    adversarial-pattern checks can split baseline from recent periods.
    """
    rng = np.random.default_rng(seed)
    out = df.copy()
    out["event_day"] = rng.integers(0, n_days, size=len(out))
    return out


def delayed_label_evaluation(
    y_true: np.ndarray,
    y_score: np.ndarray,
    event_day: np.ndarray,
    latest_day: int,
    maturation_days: int = MATURATION_DAYS,
) -> dict:
    """Evaluate on matured labels only, and show the naive-evaluation bias.

    A fraud label is mature only once ``latest_day - event_day`` reaches
    ``maturation_days`` (chargebacks take weeks to arrive). Transactions
    younger than that have pending labels. The naive evaluation treats
    pending labels as legitimate, which drags measured performance down;
    the matured evaluation uses only rows whose labels are known.
    """
    y_true = np.asarray(y_true)
    y_score = np.asarray(y_score, dtype=float)
    event_day = np.asarray(event_day)
    age = latest_day - event_day
    matured = age >= maturation_days
    pending = ~matured
    naive_true = np.where(matured, y_true, 0)
    return {
        "n_total": int(len(y_true)),
        "n_matured": int(matured.sum()),
        "n_pending": int(pending.sum()),
        "matured_fraud_rate": float(y_true[matured].mean()) if matured.any() else 0.0,
        "matured_roc_auc": roc_auc(y_true[matured], y_score[matured])
        if matured.any() and len(np.unique(y_true[matured])) > 1 else 0.5,
        "naive_roc_auc": roc_auc(naive_true, y_score)
        if len(np.unique(naive_true)) > 1 else 0.5,
    }


def pattern_shift_report(
    df: pd.DataFrame,
    y_true: np.ndarray,
    y_score: np.ndarray,
    threshold: float,
    segment_col: str = "merchant_category",
    period_col: str = "period",
    flag_change_pp: float = 0.05,
) -> pd.DataFrame:
    """Flag segments whose fraud share shifted between baseline and recent.

    For each segment, compare the fraud rate among flagged transactions in
    the baseline period with the recent period. A jump above
    ``flag_change_pp`` (5pp by default) is flagged as a candidate
    adversarial adaptation: fraud moving into a segment the model scores
    lower, or a new pattern the model has not seen.
    """
    frame = df.copy()
    frame["_y_true"] = np.asarray(y_true)
    frame["_flagged"] = (np.asarray(y_score, dtype=float) >= threshold).astype(int)
    rows = []
    for segment, group in frame.groupby(segment_col):
        base = group[group[period_col] == "baseline"]
        recent = group[group[period_col] == "recent"]
        if len(base) == 0 or len(recent) == 0:
            continue
        base_rate = float(base["_y_true"].mean())
        recent_rate = float(recent["_y_true"].mean())
        change = recent_rate - base_rate
        rows.append(
            {
                "segment": segment,
                "n_baseline": int(len(base)),
                "n_recent": int(len(recent)),
                "baseline_fraud_rate": round(base_rate, 4),
                "recent_fraud_rate": round(recent_rate, 4),
                "change_pp": round(change * 100, 2),
                "flagged": bool(change > flag_change_pp),
            }
        )
    columns = [
        "segment", "n_baseline", "n_recent", "baseline_fraud_rate",
        "recent_fraud_rate", "change_pp", "flagged",
    ]
    if not rows:
        return pd.DataFrame(columns=columns)
    return (
        pd.DataFrame(rows)
        .sort_values("change_pp", ascending=False)
        .reset_index(drop=True)
    )


def latency_quality_tradeoff(
    models: dict,
    df: pd.DataFrame,
    y_true: np.ndarray,
    threshold: float,
    sample_n: int = 200,
    seed: int = RNG_SEED,
) -> pd.DataFrame:
    """Measure per-transaction scoring latency against quality per model.

    Each model scores a seeded sample of single transactions one at a time
    (the production path: one authorisation decision per call). Reports
    mean and p99 latency in milliseconds alongside ROC-AUC and fraud
    capture at the operating threshold, so the quality-vs-latency trade-off
    is a measured table, not a guess.
    """
    y_true = np.asarray(y_true)
    sample_idx = df.sample(n=min(sample_n, len(df)), random_state=seed).index
    rows = []
    for name, model in models.items():
        latencies_ms = []
        for idx in sample_idx:
            single = df.loc[[idx]]
            start = time.perf_counter()
            model.predict(single)
            latencies_ms.append((time.perf_counter() - start) * 1000.0)
        scores = model.predict(df)
        flagged = scores >= threshold
        capture = float(y_true[flagged].sum() / y_true.sum()) if y_true.sum() else 0.0
        rows.append(
            {
                "model": name,
                "roc_auc": round(roc_auc(y_true, scores), 4),
                "fraud_capture": round(capture, 4),
                "mean_ms_per_txn": round(float(np.mean(latencies_ms)), 3),
                "p99_ms_per_txn": round(float(np.percentile(latencies_ms, 99)), 3),
            }
        )
    return pd.DataFrame(rows).sort_values("mean_ms_per_txn").reset_index(drop=True)


DEFAULT_TOLERANCES = {
    "roc_auc": 0.02,
    "precision": 0.03,
    "recall": 0.05,
    "f1": 0.03,
}


def regression_check(
    baseline: dict, current: dict, tolerances: dict | None = None
) -> pd.DataFrame:
    """Compare current-period metrics with baseline; flag regressions.

    A metric is a REGRESSION when it fell by more than its tolerance.
    Returns one row per metric plus an overall verdict in the frame's
    ``attrs`` (``overall``: PASS or REGRESSION).
    """
    tolerances = dict(DEFAULT_TOLERANCES if tolerances is None else tolerances)
    rows = []
    any_regression = False
    for metric, tolerance in tolerances.items():
        base = float(baseline[metric])
        cur = float(current[metric])
        change = cur - base
        is_regression = change < -tolerance
        any_regression = any_regression or is_regression
        rows.append(
            {
                "metric": metric,
                "baseline": round(base, 4),
                "current": round(cur, 4),
                "change": round(change, 4),
                "tolerance": tolerance,
                "status": "REGRESSION" if is_regression else "PASS",
            }
        )
    frame = pd.DataFrame(rows)
    frame.attrs["overall"] = "REGRESSION" if any_regression else "PASS"
    return frame


def build_transaction_risk_section(
    delayed: dict,
    shifts: pd.DataFrame,
    tradeoff: pd.DataFrame,
    regression: pd.DataFrame,
    n_features: int,
) -> str:
    """Assemble the transaction-risk report section (section 9)."""
    lines = []
    lines.append("9. Transaction Risk Scoring")
    lines.append("-" * 72)
    lines.append(
        f"{n_features} engineered risk features: log amount, night flag, "
        "new-device flag, 1h/24h velocity ratio, cross-border x "
        "card-not-present interaction, amount z-score."
    )
    lines.append("")
    lines.append("Delayed labels (fraud labels mature after chargebacks arrive):")
    lines.append(
        f"  {delayed['n_matured']:,} of {delayed['n_total']:,} labels matured; "
        f"{delayed['n_pending']:,} still pending. Matured fraud rate "
        f"{delayed['matured_fraud_rate']:.2%}."
    )
    lines.append(
        f"  ROC-AUC on matured labels: {delayed['matured_roc_auc']:.4f}; "
        f"naive evaluation (pending treated as legitimate): "
        f"{delayed['naive_roc_auc']:.4f}. Evaluating before labels mature "
        "understates the model."
    )
    lines.append("")
    lines.append("Adversarial pattern checks (fraud-rate shift, baseline vs recent):")
    flagged = shifts[shifts["flagged"]] if len(shifts) else shifts
    for _, row in shifts.iterrows():
        lines.append(
            f"  {str(row['segment']):<14} baseline {row['baseline_fraud_rate']:.2%} -> "
            f"recent {row['recent_fraud_rate']:.2%} "
            f"({row['change_pp']:+.2f}pp) "
            f"{'FLAGGED' if row['flagged'] else ''}"
        )
    if len(flagged) == 0:
        lines.append("  No segment shifted by more than 5pp: no adaptation signal.")
    lines.append("")
    lines.append("Model quality vs latency (measured single-transaction scoring):")
    lines.append(
        f"  {'Model':<12}{'ROC-AUC':>9}{'Capture':>9}{'Mean ms':>9}{'p99 ms':>8}"
    )
    for _, row in tradeoff.iterrows():
        lines.append(
            f"  {row['model']:<12}{row['roc_auc']:>9.4f}{row['fraud_capture']:>9.4f}"
            f"{row['mean_ms_per_txn']:>9.3f}{row['p99_ms_per_txn']:>8.3f}"
        )
    lines.append("")
    lines.append(
        f"Model-regression monitoring (recent vs baseline period): "
        f"{regression.attrs.get('overall', 'PASS')}."
    )
    for _, row in regression.iterrows():
        lines.append(
            f"  {row['metric']:<10} {row['baseline']:.4f} -> {row['current']:.4f} "
            f"({row['change']:+.4f}, tolerance {row['tolerance']}) {row['status']}"
        )
    lines.append("")
    return "\n".join(lines)
