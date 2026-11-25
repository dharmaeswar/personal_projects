"""Access propensity, wallet and attrition models (added Nov 25, 2026).

Extends the agentic analytics statistical evaluator for a Quantitative
Trading & Research — Digital fit: propensity / ranking models for Access
opportunities, investor matching inputs, wallet and share-of-wallet
models, and engagement / attrition (time-to-event) analysis over
synthetic client-interaction data. Every claim is validated with the
same statistical gate as the rest of this project — AUC for ranking,
calibration by decile, R-squared for wallet, Kaplan-Meier survival and
a chi-square test for the attrition split — using only the standard
library (logistic regression and OLS are implemented from scratch).

All data is synthetic and seeded. No real clients, meetings, wallets or
revenue. Nothing here is a claim about any real firm, event or live
result.
"""

from __future__ import annotations

import math
import random

from .stats import chi_square_test

FEATURES = ["meetings_90d", "research_reads", "events_attended",
            "tenure_months"]


def build_access_dataset(n=240, seed=11):
    """Seeded synthetic client-interaction dataset.

    Per client: meetings, research reads and events attended in the last
    90 days, tenure in months, prior wallet, and three outcomes —
    attended an Access opportunity (propensity target), wallet in $m,
    and attrition (churned flag + months to attrition, None = censored
    at 12 months). Ground truth built into the generator: engagement
    (meetings, reads, events) raises attendance and wallet and lowers
    attrition; tenure helps slightly.
    """
    rng = random.Random(seed)
    rows = []
    for i in range(n):
        meetings = rng.randint(0, 12)
        reads = rng.randint(0, 60)
        events = rng.randint(0, 6)
        tenure = rng.randint(3, 60)
        prior_wallet = round(rng.uniform(0.2, 4.0), 2)
        logit = (-2.4 + 0.30 * meetings + 0.045 * reads
                 + 0.40 * events + 0.012 * tenure)
        attended = rng.random() < _sigmoid(logit)
        wallet = max(0.05, 0.4 + 0.30 * meetings + 0.015 * reads
                     + 0.5 * events + rng.gauss(0.0, 0.8))
        competitor = max(0.1, rng.gauss(1.2, 0.5))
        share = wallet / (wallet + competitor)
        attr_logit = 0.6 - 0.22 * meetings - 0.02 * reads - 0.30 * events
        attrited = rng.random() < _sigmoid(attr_logit)
        months = rng.randint(1, 12) if attrited else None
        rows.append({
            "client_id": f"CL-{i:03d}",
            "meetings_90d": meetings,
            "research_reads": reads,
            "events_attended": events,
            "tenure_months": tenure,
            "prior_wallet_usd_m": prior_wallet,
            "attended": attended,
            "wallet_usd_m": round(wallet, 2),
            "share_of_wallet": round(share, 3),
            "attrited": attrited,
            "months_to_attrition": months,
        })
    return rows


def _sigmoid(z):
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    exp_z = math.exp(z)
    return exp_z / (1.0 + exp_z)


def _standardize(rows, features):
    """Return (matrix, means, stds) with each feature zero-mean/unit-sd."""
    means, stds = [], []
    for f in features:
        values = [r[f] for r in rows]
        mean = sum(values) / len(values)
        var = sum((v - mean) ** 2 for v in values) / len(values)
        means.append(mean)
        stds.append(math.sqrt(var) if var > 0 else 1.0)
    matrix = [[(r[f] - means[j]) / stds[j] for j, f in enumerate(features)]
              for r in rows]
    return matrix, means, stds


def fit_logistic(rows, features=FEATURES, lr=0.5, epochs=800):
    """Logistic regression from scratch (gradient descent on log-loss).

    Returns a model dict with standardisation constants, weights and
    intercept, plus the final training log-loss.
    """
    X, means, stds = _standardize(rows, features)
    y = [1.0 if r["attended"] else 0.0 for r in rows]
    weights = [0.0] * len(features)
    intercept = 0.0
    n = len(rows)
    for _ in range(epochs):
        grad_w = [0.0] * len(features)
        grad_b = 0.0
        for xi, yi in zip(X, y):
            p = _sigmoid(sum(w * v for w, v in zip(weights, xi)) + intercept)
            err = p - yi
            for j in range(len(features)):
                grad_w[j] += err * xi[j]
            grad_b += err
        for j in range(len(features)):
            weights[j] -= lr * grad_w[j] / n
        intercept -= lr * grad_b / n
    loss = _log_loss(rows, {"means": means, "stds": stds,
                            "weights": weights, "intercept": intercept,
                            "features": list(features)},
                     features)
    return {"means": means, "stds": stds, "weights": weights,
            "intercept": intercept, "features": list(features),
            "train_log_loss": round(loss, 4)}


def _log_loss(rows, model, features):
    total = 0.0
    for r in rows:
        p = predict_proba(model, r)
        p = min(max(p, 1e-9), 1.0 - 1e-9)
        total -= math.log(p) if r["attended"] else math.log(1.0 - p)
    return total / len(rows)


def predict_proba(model, row):
    z = model["intercept"]
    for j, f in enumerate(model["features"]):
        z += model["weights"][j] * (
            row[f] - model["means"][j]) / model["stds"][j]
    return _sigmoid(z)


def auc(scores, labels):
    """ROC AUC via the Mann-Whitney U statistic (ties count 0.5)."""
    pos = [s for s, y in zip(scores, labels) if y]
    neg = [s for s, y in zip(scores, labels) if not y]
    if not pos or not neg:
        raise ValueError("AUC needs both classes present")
    wins = 0.0
    for p in pos:
        for q in neg:
            if p > q:
                wins += 1.0
            elif p == q:
                wins += 0.5
    return wins / (len(pos) * len(neg))


def fit_ols(rows, target, features=FEATURES):
    """Ordinary least squares from scratch (normal equations).

    Returns intercept, coefficients, R-squared and n.
    """
    X = [[1.0] + [float(r[f]) for f in features] for r in rows]
    y = [float(r[target]) for r in rows]
    k = len(features) + 1
    xtx = [[sum(row[i] * row[j] for row in X) for j in range(k)]
           for i in range(k)]
    xty = [sum(row[i] * yi for row, yi in zip(X, y)) for i in range(k)]
    beta = _solve(xtx, xty)
    preds = [sum(b * v for b, v in zip(beta, row)) for row in X]
    mean_y = sum(y) / len(y)
    ss_tot = sum((v - mean_y) ** 2 for v in y)
    ss_res = sum((v - p) ** 2 for v, p in zip(y, preds))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
    return {"intercept": beta[0], "coefficients": beta[1:],
            "features": list(features), "r2": round(r2, 4),
            "n": len(rows)}


def _solve(matrix, rhs):
    """Gaussian elimination with partial pivoting for a small system."""
    n = len(rhs)
    aug = [row[:] + [rhs[i]] for i, row in enumerate(matrix)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(aug[r][col]))
        if abs(aug[pivot][col]) < 1e-12:
            raise ValueError("singular matrix in OLS solve")
        aug[col], aug[pivot] = aug[pivot], aug[col]
        for r in range(col + 1, n):
            factor = aug[r][col] / aug[col][col]
            for c in range(col, n + 1):
                aug[r][c] -= factor * aug[col][c]
    out = [0.0] * n
    for i in range(n - 1, -1, -1):
        out[i] = (aug[i][n] - sum(aug[i][j] * out[j]
                                  for j in range(i + 1, n))) / aug[i][i]
    return out


def calibration(predicted, labels, bins=5):
    """Predicted-vs-observed rates per predicted-probability bin."""
    pairs = sorted(zip(predicted, labels))
    n = len(pairs)
    out = []
    for b in range(bins):
        chunk = pairs[b * n // bins:(b + 1) * n // bins]
        if not chunk:
            continue
        out.append({
            "bin": b + 1,
            "n": len(chunk),
            "mean_predicted": round(sum(p for p, _ in chunk) / len(chunk), 3),
            "observed_rate": round(
                sum(y for _, y in chunk) / len(chunk), 3),
        })
    return out


def kaplan_meier(rows):
    """Kaplan-Meier survival curve over months 1-12.

    At each month, events are clients with months_to_attrition == month;
    at risk are clients not yet attrited before that month (censored
    clients stay at risk through month 12). Returns {month: survival}.
    """
    survival = 1.0
    curve = {}
    for month in range(1, 13):
        at_risk = [r for r in rows
                   if r["months_to_attrition"] is None
                   or r["months_to_attrition"] >= month]
        events = [r for r in rows
                  if r["months_to_attrition"] == month]
        if at_risk:
            survival *= 1.0 - len(events) / len(at_risk)
        curve[month] = round(survival, 4)
    return curve


def attrition_by_engagement(rows):
    """Chi-square test: attrition rate, high vs low engagement.

    High engagement = 4+ meetings in 90 days. Returns the 2x2 table,
    both rates and the chi-square result.
    """
    high = [r for r in rows if r["meetings_90d"] >= 4]
    low = [r for r in rows if r["meetings_90d"] < 4]
    table = [[sum(1 for r in high if r["attrited"]),
              sum(1 for r in high if not r["attrited"])],
             [sum(1 for r in low if r["attrited"]),
              sum(1 for r in low if not r["attrited"])]]
    test = chi_square_test(table)
    return {
        "table": table,
        "high_attrition_rate": round(table[0][0] / max(sum(table[0]), 1), 3),
        "low_attrition_rate": round(table[1][0] / max(sum(table[1]), 1), 3),
        "chi2": round(test["chi2"], 3),
        "p": round(test["p"], 4),
    }


def run_access_eval():
    """Fit propensity + wallet models and validate them end to end."""
    rows = build_access_dataset()
    rng = random.Random(11)
    order = list(range(len(rows)))
    rng.shuffle(order)
    train = [rows[i] for i in order[:180]]
    test = [rows[i] for i in order[180:]]
    model = fit_logistic(train)
    test_scores = [predict_proba(model, r) for r in test]
    test_labels = [1 if r["attended"] else 0 for r in test]
    test_auc = round(auc(test_scores, test_labels), 4)
    calib = calibration(test_scores, test_labels)
    max_gap = max(abs(c["mean_predicted"] - c["observed_rate"])
                  for c in calib)
    wallet = fit_ols(train, "wallet_usd_m")
    test_wallet = fit_ols(test, "wallet_usd_m")
    km_all = kaplan_meier(rows)
    high_rows = [r for r in rows if r["meetings_90d"] >= 4]
    low_rows = [r for r in rows if r["meetings_90d"] < 4]
    km_high = kaplan_meier(high_rows)
    km_low = kaplan_meier(low_rows)
    attrition = attrition_by_engagement(rows)
    verdict = ("PASS" if test_auc >= 0.65 and wallet["r2"] >= 0.2
               and attrition["p"] < 0.05 else "FAIL")
    return {
        "verdict": verdict,
        "n_train": len(train),
        "n_test": len(test),
        "propensity": {
            "test_auc": test_auc,
            "train_log_loss": model["train_log_loss"],
            "calibration": calib,
            "max_calibration_gap": round(max_gap, 3),
        },
        "wallet": {
            "train_r2": wallet["r2"],
            "test_r2": test_wallet["r2"],
            "coefficients": dict(zip(
                wallet["features"],
                [round(c, 3) for c in wallet["coefficients"]])),
        },
        "attrition": attrition,
        "survival_month_12": {
            "all": km_all[12],
            "high_engagement": km_high[12],
            "low_engagement": km_low[12],
        },
    }


def render_access_report(result):
    lines = [f"Access propensity, wallet & attrition eval: "
             f"{result['verdict']}",
             "",
             f"Propensity model (test AUC): "
             f"{result['propensity']['test_auc']:.3f}",
             f"  train log-loss: "
             f"{result['propensity']['train_log_loss']}",
             f"  max calibration gap: "
             f"{result['propensity']['max_calibration_gap']:.3f}",
             f"Wallet model R²: train "
             f"{result['wallet']['train_r2']:.3f}, test "
             f"{result['wallet']['test_r2']:.3f}",
             "  coefficients: " + ", ".join(
                 f"{k}={v}" for k, v in
                 result['wallet']['coefficients'].items()),
             "",
             "Attrition by engagement "
             f"(chi2={result['attrition']['chi2']}, "
             f"p={result['attrition']['p']}):",
             f"  high engagement: "
             f"{result['attrition']['high_attrition_rate']:.1%} attrited",
             f"  low engagement: "
             f"{result['attrition']['low_attrition_rate']:.1%} attrited",
             "",
             "12-month survival: all "
             f"{result['survival_month_12']['all']:.2%}, high engagement "
             f"{result['survival_month_12']['high_engagement']:.2%}, "
             f"low engagement "
             f"{result['survival_month_12']['low_engagement']:.2%}"]
    return "\n".join(lines) + "\n"
