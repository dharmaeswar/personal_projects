"""Workforce-planning forecasts.

Two pieces, both standard library only:

1. Attrition-risk model: a logistic regression (gradient descent, L2)
   on overtime, night shift, schedule changes, manager tenure, tenure
   and experience score. Scored on a held-out split with AUC, Brier
   score against the base-rate baseline, and decile calibration, so the
   model is validated the same way a production model would be.
   Known limit, stated in the report: the linear logit under-predicts
   the highest-risk quintile (predicted ~0.21 vs observed ~0.38),
   because attrition in the data jumps at low experience scores — a
   threshold effect a linear model only partly captures. Schedule
   churn's effect is likewise mediated through the experience score
   rather than direct.
2. Headcount / attrition-count forecasting: a 12-month monthly history
   simulated from each org's observed attrition rate with a mild
   seasonal pattern (seeded, reproducible), a trend forecast with 95%
   prediction intervals, and a backtest that fits on months 1-9 and
   scores months 10-12 (MAPE and interval coverage) before the model
   is trusted on the next quarter.
"""

import math
import random

from .stats import mean, std

FEATURES = [
    "overtime_hours_week",
    "night_shift",
    "schedule_changes_month",
    "manager_tenure_years",
    "tenure_years",
    "experience_score",
]


def _features(row):
    return [
        row["overtime_hours_week"],
        1.0 if row["shift"] == "Night" else 0.0,
        float(row["schedule_changes_month"]),
        row["manager_tenure_years"],
        row["tenure_years"],
        row["experience_score"],
    ]


def _sigmoid(z):
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    e = math.exp(z)
    return e / (1.0 + e)


def _standardise(xs, mus=None, sds=None):
    """Standardise columns; return (scaled, mus, sds)."""
    cols = list(zip(*xs))
    if mus is None:
        mus = [mean(c) for c in cols]
    if sds is None:
        sds = [std(c) if std(c) > 0 else 1.0 for c in cols]
    scaled = [[(x - m) / s for x, m, s in zip(row, mus, sds)] for row in xs]
    return scaled, mus, sds


def fit_logistic(xs, ys, lr=0.5, epochs=5000, l2=0.001):
    """Fit logistic regression by batch gradient descent.

    Returns {"weights": [...], "bias": float, "mus": [...], "sds": [...]}.
    Defaults are the converged settings for this dataset (larger
    learning rates / longer runs give the same weights to 3 decimals).
    """
    scaled, mus, sds = _standardise(xs)
    n = len(scaled)
    p = len(scaled[0])
    w = [0.0] * p
    b = 0.0
    for _ in range(epochs):
        gw = [0.0] * p
        gb = 0.0
        for x, y in zip(scaled, ys):
            z = b + sum(wi * xi for wi, xi in zip(w, x))
            err = _sigmoid(z) - y
            for j in range(p):
                gw[j] += err * x[j]
            gb += err
        for j in range(p):
            w[j] -= lr * (gw[j] / n + l2 * w[j])
        b -= lr * gb / n
    return {"weights": w, "bias": b, "mus": mus, "sds": sds}


def predict_proba(model, xs):
    out = []
    for row in xs:
        scaled = [(x - m) / s for x, m, s in zip(row, model["mus"], model["sds"])]
        z = model["bias"] + sum(wi * xi for wi, xi in zip(model["weights"], scaled))
        out.append(_sigmoid(z))
    return out


def train_test_split(rows, test_frac=0.2, seed=11):
    rng = random.Random(seed)
    idx = list(range(len(rows)))
    rng.shuffle(idx)
    n_test = int(len(rows) * test_frac)
    test_idx = set(idx[:n_test])
    train = [r for i, r in enumerate(rows) if i not in test_idx]
    test = [r for i, r in enumerate(rows) if i in test_idx]
    return train, test


def auc(scores, labels):
    """Mann-Whitney AUC for binary labels."""
    pos = [s for s, y in zip(scores, labels) if y == 1]
    neg = [s for s, y in zip(scores, labels) if y == 0]
    if not pos or not neg:
        return 0.5
    wins = 0.0
    for p in pos:
        for q in neg:
            if p > q:
                wins += 1.0
            elif p == q:
                wins += 0.5
    return wins / (len(pos) * len(neg))


def brier_score(probs, labels):
    return mean([(p - y) ** 2 for p, y in zip(probs, labels)])


def calibration_bins(probs, labels, n_bins=5):
    """Per-bin (mean predicted, observed rate, n), sorted by predicted risk."""
    pairs = sorted(zip(probs, labels))
    n = len(pairs)
    bins = []
    for i in range(n_bins):
        chunk = pairs[i * n // n_bins:(i + 1) * n // n_bins]
        if not chunk:
            continue
        bins.append({
            "mean_predicted": round(mean([p for p, _ in chunk]), 3),
            "observed_rate": round(mean([y for _, y in chunk]), 3),
            "n": len(chunk),
        })
    return bins


def attrition_model(rows):
    """Fit on 80%, evaluate on the held-out 20%. Returns a result dict."""
    train, test = train_test_split(rows)
    x_train = [_features(r) for r in train]
    y_train = [r["attrition"] for r in train]
    model = fit_logistic(x_train, y_train)
    x_test = [_features(r) for r in test]
    y_test = [r["attrition"] for r in test]
    probs = predict_proba(model, x_test)
    base_rate = mean(y_train)
    base_brier = brier_score([base_rate] * len(y_test), y_test)
    return {
        "model": model,
        "n_train": len(train),
        "n_test": len(test),
        "auc": round(auc(probs, y_test), 3),
        "brier": round(brier_score(probs, y_test), 4),
        "base_brier": round(base_brier, 4),
        "base_rate": round(base_rate, 3),
        "calibration": calibration_bins(probs, y_test),
        "coefficients": {
            name: round(w, 3)
            for name, w in zip(FEATURES, model["weights"])
        },
    }


# --- Monthly headcount / attrition-count history and forecasting ---

# Mild seasonal pattern: attrition runs hotter in January and June.
SEASONAL = [1.25, 0.95, 1.0, 0.95, 1.0, 1.2, 0.95, 0.9, 1.0, 0.95, 1.0, 1.1]


def monthly_history(rows, months=12, seed=99):
    """Monthly attrition counts per org, simulated from observed rates.

    Each org's monthly attrition probability is its observed attrition
    rate treated as an ANNUAL rate (divided by 12) times the seasonal
    factor; counts are binomial draws with a fixed seed, so the history
    is reproducible. Headcount is held steady at the observed size
    (replacement hiring offsets leavers), so this is a flow model for
    the forecasting method — not a claim about any real headcount plan.
    Returns a list of
    {"month": int, "org": str, "headcount": int, "attritions": int}.
    """
    rng = random.Random(seed)
    history = []
    orgs = sorted({r["org"] for r in rows})
    for org in orgs:
        org_rows = [r for r in rows if r["org"] == org]
        headcount = len(org_rows)
        rate = mean([r["attrition"] for r in org_rows]) / 12.0
        for m in range(1, months + 1):
            p = min(0.9, rate * SEASONAL[m - 1])
            attr = sum(1 for _ in range(headcount) if rng.random() < p)
            history.append({
                "month": m, "org": org,
                "headcount": headcount, "attritions": attr,
            })
    return history


def _fit_trend(xs, ys):
    """Ordinary least squares line; returns (intercept, slope, resid_sd)."""
    mx, my = mean(xs), mean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    den = sum((x - mx) ** 2 for x in xs)
    slope = num / den if den > 0 else 0.0
    intercept = my - slope * mx
    resid = [y - (intercept + slope * x) for x, y in zip(xs, ys)]
    sd = std(resid) if len(resid) > 1 else 0.0
    return intercept, slope, sd


def forecast_counts(history, horizon=3):
    """Trend forecast of total monthly attritions with 95% intervals.

    Fits on the full history; returns [{"month", "forecast", "lo", "hi"}].
    """
    months = sorted({h["month"] for h in history})
    totals = [sum(h["attritions"] for h in history if h["month"] == m)
              for m in months]
    intercept, slope, sd = _fit_trend(months, totals)
    out = []
    for m in range(max(months) + 1, max(months) + 1 + horizon):
        f = intercept + slope * m
        out.append({
            "month": m,
            "forecast": round(f, 1),
            "lo": round(max(0.0, f - 1.96 * sd), 1),
            "hi": round(f + 1.96 * sd, 1),
        })
    return out


def backtest(history, train_months=9, horizon=3):
    """Fit on months 1..train_months, score the next `horizon` months.

    Returns {"mape", "coverage", "detail": [...]} where coverage is the
    share of held-out months whose actual count fell inside the 95%
    prediction interval.
    """
    months = sorted({h["month"] for h in history})
    totals = {m: sum(h["attritions"] for h in history if h["month"] == m)
              for m in months}
    train_m = months[:train_months]
    intercept, slope, sd = _fit_trend(
        train_m, [totals[m] for m in train_m])
    detail = []
    for m in months[train_months:train_months + horizon]:
        f = intercept + slope * m
        lo = max(0.0, f - 1.96 * sd)
        hi = f + 1.96 * sd
        actual = totals[m]
        detail.append({
            "month": m,
            "forecast": round(f, 1),
            "actual": actual,
            "lo": round(lo, 1),
            "hi": round(hi, 1),
            "in_interval": lo <= actual <= hi,
            "ape": round(abs(actual - f) / actual, 3) if actual else 0.0,
        })
    mape = round(mean([d["ape"] for d in detail]), 3) if detail else 0.0
    coverage = round(
        mean([1.0 if d["in_interval"] else 0.0 for d in detail]), 3
    ) if detail else 0.0
    return {"mape": mape, "coverage": coverage, "detail": detail}


def workforce_plan(rows):
    """Run the full planning analysis; returns one result dict."""
    model = attrition_model(rows)
    history = monthly_history(rows)
    fc = forecast_counts(history)
    bt = backtest(history)
    total_attr = sum(h["attritions"] for h in history)
    return {
        "attrition_model": model,
        "months": 12,
        "total_attritions_12m": total_attr,
        "forecast_next_3m": fc,
        "backtest": bt,
    }
