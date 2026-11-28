"""Inbound lead scoring, MQL routing and lead value for a B2B SaaS GTM team.

This is the lead-scoring half of the GTM Data Scientist work: the production
models in the JD are lead scoring, lead value, next-best-play routing and
customer expansion — alongside the MMM, attribution and geo experiments
already in this project. This module builds the scoring model itself: a
logistic-regression scorer over synthetic inbound leads, a calibration
check (predicted vs observed conversion by score band), MQL tier bands
with routing rules and exclusions, and an expected lead value.

All data is synthetic and seeded (see ``generate_leads``). Ground truth is
a known logistic function of the features, so the fitted model can be
checked against a known answer. Nothing here is production GTM data and
nothing is a claim about any real company's leads, MQL rates or deal sizes.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import cross_val_score, train_test_split

SEED = 7
N_LEADS = 2000

CHANNELS = ["paid_search", "paid_social", "organic_search", "referral", "outbound"]
# Known-truth log-odds contributions, used only to generate the outcome.
CHANNEL_EFFECT = {
    "paid_search": 0.55,
    "paid_social": 0.10,
    "organic_search": 0.40,
    "referral": 0.70,
    "outbound": -0.35,
}
# Average first-year deal size by company-size band, used for lead value.
DEAL_SIZE = {"small": 12000.0, "mid": 45000.0, "large": 150000.0}

# MQL tier bands on the predicted score, and the routing action per tier.
TIER_BANDS = [("hot", 0.60), ("warm", 0.35), ("cold", 0.0)]
# Leads below this enrichment completeness are not MQL-ready: the score
# cannot be trusted when the enrichment feed has not filled the record.
ENRICHMENT_FLOOR = 0.50


def generate_leads(n=N_LEADS, seed=SEED):
    """Generate seeded synthetic inbound leads with a known MQL outcome."""
    rng = np.random.default_rng(seed)
    channel = rng.choice(CHANNELS, size=n, p=[0.30, 0.20, 0.25, 0.10, 0.15])
    size_band = rng.choice(["small", "mid", "large"], size=n, p=[0.55, 0.32, 0.13])
    visits = rng.poisson(4.0, size=n)
    downloads = rng.poisson(1.2, size=n)
    trial = (rng.random(n) < 0.18).astype(int)
    demo = (rng.random(n) < 0.12).astype(int)
    enrichment = np.clip(rng.beta(6.0, 2.0, size=n), 0.05, 1.0)
    competitor = (rng.random(n) < 0.03).astype(int)
    days_since_touch = rng.integers(0, 31, size=n)

    logit = (
        -2.90
        + np.array([CHANNEL_EFFECT[c] for c in channel])
        + 0.45 * np.log1p(visits)
        + 0.70 * downloads
        + 1.20 * trial
        + 1.50 * demo
        + 0.60 * enrichment
        + 0.35 * (size_band == "large")
        - 0.02 * days_since_touch
    )
    p_true = 1.0 / (1.0 + np.exp(-logit))
    mql = (rng.random(n) < p_true).astype(int)

    return pd.DataFrame({
        "lead_id": np.arange(1, n + 1),
        "channel": channel,
        "size_band": size_band,
        "website_visits": visits,
        "content_downloads": downloads,
        "trial_started": trial,
        "demo_requested": demo,
        "enrichment": np.round(enrichment, 3),
        "is_competitor": competitor,
        "days_since_touch": days_since_touch,
        "mql": mql,
    })


def _features(leads):
    """One-hot channel + numeric signals, in a fixed column order."""
    X = pd.get_dummies(leads["channel"], prefix="ch").reindex(
        columns=[f"ch_{c}" for c in CHANNELS], fill_value=0
    ).astype(float)
    X["website_visits"] = np.log1p(leads["website_visits"].astype(float))
    X["content_downloads"] = leads["content_downloads"].astype(float)
    X["trial_started"] = leads["trial_started"].astype(float)
    X["demo_requested"] = leads["demo_requested"].astype(float)
    X["enrichment"] = leads["enrichment"].astype(float)
    X["is_large"] = (leads["size_band"] == "large").astype(float)
    X["days_since_touch"] = leads["days_since_touch"].astype(float)
    return X


def fit_lead_scorer(leads, seed=SEED):
    """Fit the logistic scorer; return model, metrics and the scored frame."""
    X = _features(leads)
    y = leads["mql"].astype(int)
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.25, random_state=seed, stratify=y
    )
    model = LogisticRegression(max_iter=1000, C=1.0)
    model.fit(X_train, y_train)
    scored = leads.copy()
    scored["score"] = model.predict_proba(X)[:, 1]
    train_auc = roc_auc_score(y_train, model.predict_proba(X_train)[:, 1])
    test_auc = roc_auc_score(y_test, model.predict_proba(X_test)[:, 1])
    # 5-fold CV AUC is the stable headline: a single holdout split of 500
    # leads moves by ~0.03 from split to split, so one split is not the story.
    cv_auc = float(np.mean(cross_val_score(
        LogisticRegression(max_iter=1000, C=1.0), X, y,
        cv=5, scoring="roc_auc")))
    return {
        "model": model,
        "feature_names": list(X.columns),
        "train_auc": round(float(train_auc), 3),
        "test_auc": round(float(test_auc), 3),
        "cv_auc": round(cv_auc, 3),
        "base_rate": round(float(y.mean()), 3),
        "n_leads": int(len(leads)),
        "scored": scored,
    }


def calibration_table(scored, bins=5):
    """Observed vs predicted MQL rate per score band — the calibration check.

    A production scoring model is trusted only if a 0.6 really converts
    about 60% of the time. Bands are equal-width on the predicted score.
    """
    frame = scored.copy()
    frame["band"] = pd.cut(frame["score"], bins=bins, include_lowest=True)
    rows = []
    for band, group in frame.groupby("band", observed=True):
        rows.append({
            "band": str(band),
            "n": int(len(group)),
            "mean_predicted": round(float(group["score"].mean()), 3),
            "observed_rate": round(float(group["mql"].mean()), 3),
            "gap": round(float(group["mql"].mean() - group["score"].mean()), 3),
        })
    return rows


def assign_mql_tiers(scored):
    """Apply the MQL tier bands and the routing rules to scored leads.

    Rules, in order: competitor domains are excluded outright; leads below
    the enrichment floor go to nurture, not to sales; demo requests
    fast-track to the hot tier; otherwise the score band decides the tier.
    Returns the frame with ``tier`` and ``route`` columns.
    """
    frame = scored.copy()
    tiers, routes = [], []
    for _, row in frame.iterrows():
        if row["is_competitor"]:
            tiers.append("excluded")
            routes.append("exclude — competitor domain")
        elif row["enrichment"] < ENRICHMENT_FLOOR:
            tiers.append("nurture")
            routes.append("nurture — enrichment incomplete")
        elif row["demo_requested"]:
            tiers.append("hot")
            routes.append("route to SDR immediately — demo requested")
        else:
            tier = next(name for name, floor in TIER_BANDS if row["score"] >= floor)
            tiers.append(tier)
            routes.append({
                "hot": "route to SDR immediately",
                "warm": "route to SDR queue",
                "cold": "nurture — no SDR route",
            }[tier])
    frame["tier"] = tiers
    frame["route"] = routes
    return frame


def lead_value(routed):
    """Expected value per lead: P(MQL) x deal size for its size band."""
    frame = routed.copy()
    frame["deal_size"] = frame["size_band"].map(DEAL_SIZE)
    frame["expected_value"] = frame["score"] * frame["deal_size"]
    by_band = (
        frame.groupby("size_band")["expected_value"]
        .agg(["mean", "sum", "count"])
        .round(2)
        .to_dict("index")
    )
    return {
        "total_expected_value": round(float(frame["expected_value"].sum()), 2),
        "mean_expected_value": round(float(frame["expected_value"].mean()), 2),
        "by_size_band": {k: {kk: float(vv) for kk, vv in v.items()}
                         for k, v in by_band.items()},
        "scored": frame,
    }


def lead_scoring_summary_lines(fit, calibration, routed, value):
    """Plain-language lines for output/report.md."""
    tier_counts = routed["tier"].value_counts().to_dict()
    lines = [
        "## Lead scoring (inbound leads, synthetic data)\n",
        f"- Leads scored: {fit['n_leads']}; observed MQL rate: "
        f"{fit['base_rate']:.1%}; ROC-AUC 5-fold CV {fit['cv_auc']} "
        f"(train {fit['train_auc']}, holdout {fit['test_auc']}).",
        "- Calibration (predicted vs observed MQL rate by score band): "
        + "; ".join(
            f"{r['band']}: pred {r['mean_predicted']:.2f} vs obs "
            f"{r['observed_rate']:.2f} (n={r['n']})" for r in calibration
        ) + ".",
        "- MQL tiers: "
        + ", ".join(f"{t} {c}" for t, c in sorted(tier_counts.items()))
        + ". Competitor domains are excluded and leads below the "
        f"{ENRICHMENT_FLOOR} enrichment floor go to nurture, not to sales.",
        f"- Expected pipeline value of the scored leads: "
        f"${value['total_expected_value']:,.0f} "
        f"(mean ${value['mean_expected_value']:,.0f} per lead).",
    ]
    return lines
