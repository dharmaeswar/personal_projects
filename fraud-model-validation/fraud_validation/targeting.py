"""Partner Decision Science targeting and approval modelling.

Extends the fraud-model validation suite with the models a partner
decision-science team runs on a marketplace like Credit Karma's
Lightbox platform, where partner banks and fintech lenders target and
approve members for credit products:

- targeting model: conversion propensity (member applies after seeing a
  partner offer), fit as a logistic-regression champion and a
  gradient-boosting challenger, scored with ROC-AUC, KS, and decile
  conversion capture / lift,
- approval model: calibrated approval probability for converted members,
  fit with Platt (sigmoid) calibration on a logistic regression, with
  calibration by decile and an approval-certainty split (high-certainty
  approve, high-certainty decline, uncertain middle),
- next-best-offer ranking: each member's three partner offers ranked by
  predicted conversion x calibrated approval probability, scored with
  NDCG@3 against a popularity baseline,
- experimentation: a seeded A/B readout for model-ranked targeting vs
  the popularity control, with a Welch t-test, a bootstrap 95% CI on
  the conversion lift, and an approval-rate guardrail.

All data is synthetic and seeded. No real member, bureau, or partner
data is used, and nothing here is a claim about any real lender or
marketplace.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from fraud_validation.metrics import calibration_by_decile, ks_statistic, roc_auc

RNG_SEED = 2026
N_OFFERS = 12_000
N_RANKING_MEMBERS = 2_000
N_EXPERIMENT = 8_000

OFFER_TYPES = ["card", "personal_loan", "line_of_credit"]
# Offer APR ranges by type (card highest, line of credit lowest).
OFFER_APR = {"card": (19.99, 29.99), "personal_loan": (9.99, 24.99),
             "line_of_credit": (12.99, 24.99)}

# Numeric columns used by the targeting / approval models.
MODEL_FEATURES = [
    "bureau_score",
    "utilisation",
    "inquiries_12m",
    "delinquencies_24m",
    "log_income",
    "prior_clicks_90d",
    "member_tenure_days",
    "offer_apr",
    "offer_clicks_90d",
]
OFFER_TYPE_DUMMIES = [f"offer_{t}" for t in OFFER_TYPES]


def _sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-x))


def _member_features(rng: np.random.Generator, n: int) -> dict:
    """Shared synthetic member / bureau features for every generator."""
    return {
        "bureau_score": np.clip(
            rng.normal(loc=685.0, scale=62.0, size=n), 300, 850
        ).astype(int),
        "utilisation": np.clip(rng.beta(a=2.0, b=5.0, size=n), 0.0, 1.0),
        "inquiries_12m": rng.poisson(lam=1.1, size=n),
        "delinquencies_24m": rng.poisson(lam=0.4, size=n),
        "annual_income": rng.lognormal(mean=11.0, sigma=0.55, size=n),
        "prior_clicks_90d": rng.poisson(lam=1.4, size=n),
        "member_tenure_days": rng.exponential(scale=420.0, size=n),
    }


def _conversion_logit(
    feats: dict,
    offer_apr: np.ndarray,
    match_bonus: np.ndarray | None = None,
    offer_clicks: np.ndarray | None = None,
) -> np.ndarray:
    """Log-odds a member applies after seeing an offer.

    Driven by prior engagement, tenure, bureau score and offer APR
    (cheaper offers convert better), plus clicks on this offer's
    product type in the last 90 days — the observable affinity signal
    a ranking model can actually use. ``match_bonus`` adds log-odds
    when the shown offer matches the member's preferred product type
    (partly latent: clicks only proxy it, so the model cannot recover
    the preference exactly).
    """
    if offer_clicks is None:
        offer_clicks = np.asarray(feats.get("offer_clicks_90d", 0))
    logit = (
        -2.7
        + 0.45 * np.clip(feats["prior_clicks_90d"], 0, 5)
        + 0.35 * np.log1p(feats["member_tenure_days"] / 180.0)
        + 0.006 * (feats["bureau_score"] - 685.0)
        - 0.05 * (offer_apr - 18.0)
        + 0.3 * np.log1p(feats["annual_income"] / 50_000.0)
        + 0.30 * np.clip(offer_clicks, 0, 5)
    )
    if match_bonus is not None:
        logit = logit + match_bonus
    return logit


def _approval_logit(feats: dict) -> np.ndarray:
    """Log-odds a converted member is approved, from bureau features."""
    return (
        -2.4
        - 0.011 * (feats["bureau_score"] - 685.0)
        + 1.4 * feats["utilisation"]
        + 0.45 * feats["delinquencies_24m"]
        + 0.18 * feats["inquiries_12m"]
        - 0.25 * np.log1p(feats["annual_income"] / 50_000.0)
    )


def generate_partner_offers(
    n: int = N_OFFERS, seed: int = RNG_SEED
) -> pd.DataFrame:
    """Generate ``n`` seeded synthetic partner-offer impressions.

    Each row is one member shown one partner offer. ``converted`` marks
    a member who applied after seeing the offer; ``approved`` marks an
    approval among converted members (0 for non-converters).
    """
    rng = np.random.default_rng(seed)
    feats = _member_features(rng, n)
    offer_type = rng.choice(OFFER_TYPES, size=n)
    offer_apr = np.array(
        [rng.uniform(*OFFER_APR[t]) for t in offer_type]
    )
    # Clicks on the shown offer's product type in the last 90 days:
    # the observable affinity signal the ranking model learns from.
    feats["offer_clicks_90d"] = rng.poisson(lam=1.2, size=n)
    p_convert = _sigmoid(_conversion_logit(feats, offer_apr))
    converted = rng.binomial(1, p_convert).astype(int)
    p_approve = _sigmoid(_approval_logit(feats))
    approved = np.where(
        converted == 1, rng.binomial(1, p_approve), 0
    ).astype(int)
    return pd.DataFrame(
        {
            **feats,
            "offer_type": offer_type,
            "offer_apr": np.round(offer_apr, 2),
            "converted": converted,
            "approved": approved,
        }
    )


def build_targeting_features(df: pd.DataFrame) -> pd.DataFrame:
    """Engineer targeting features from the raw offer columns.

    ``score_band`` is the bureau-score band label; ``utilisation_band``
    buckets revolving utilisation; ``recent_inquiries`` flags 3+
    inquiries in 12 months; ``engaged_90d`` flags any prior click in
    90 days; ``apr_band`` buckets the offer APR; ``dti_proxy`` is loan
    amount over annual income where a loan amount is present.
    """
    out = df.copy()
    out["score_band"] = pd.cut(
        out["bureau_score"],
        bins=[299, 579, 619, 659, 699, 739, 850],
        labels=["300-579", "580-619", "620-659", "660-699", "700-739", "740-850"],
    ).astype(str)
    out["utilisation_band"] = pd.cut(
        out["utilisation"],
        bins=[-0.01, 0.3, 0.6, 1.0],
        labels=["low", "medium", "high"],
    ).astype(str)
    out["recent_inquiries"] = (out["inquiries_12m"] >= 3).astype(int)
    out["engaged_90d"] = (out["prior_clicks_90d"] >= 1).astype(int)
    out["apr_band"] = pd.cut(
        out["offer_apr"],
        bins=[0, 14.99, 19.99, 24.99, 40.0],
        labels=["under-15", "15-20", "20-25", "over-25"],
    ).astype(str)
    return out


def _feature_matrix(df: pd.DataFrame) -> np.ndarray:
    """Numeric + one-hot feature matrix in a fixed column order."""
    work = df.copy()
    work["log_income"] = np.log(work["annual_income"])
    numeric = work[MODEL_FEATURES].to_numpy(dtype=float)
    dummies = pd.get_dummies(work["offer_type"]).reindex(
        columns=OFFER_TYPES, fill_value=0
    ).to_numpy(dtype=float)
    return np.hstack([numeric, dummies])


class TargetingChampion:
    """Logistic-regression conversion-propensity model (scaled features)."""

    def __init__(self) -> None:
        self.scaler = StandardScaler()
        self.model = LogisticRegression(max_iter=1000, C=1.0)

    def fit(self, df: pd.DataFrame) -> "TargetingChampion":
        x = self.scaler.fit_transform(_feature_matrix(df))
        self.model.fit(x, df["converted"].to_numpy())
        return self

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        x = self.scaler.transform(_feature_matrix(df))
        return self.model.predict_proba(x)[:, 1]


class TargetingChallenger:
    """Gradient-boosting conversion-propensity model."""

    def __init__(self) -> None:
        self.model = GradientBoostingClassifier(
            n_estimators=150, learning_rate=0.08, max_depth=3,
            subsample=0.9, random_state=42,
        )

    def fit(self, df: pd.DataFrame) -> "TargetingChallenger":
        self.model.fit(_feature_matrix(df), df["converted"].to_numpy())
        return self

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        return self.model.predict_proba(_feature_matrix(df))[:, 1]


def fit_targeting_models(train: pd.DataFrame) -> dict:
    """Fit champion, challenger, and a base-rate benchmark on conversions."""
    champion = TargetingChampion().fit(train)
    challenger = TargetingChallenger().fit(train)
    base_rate = float(train["converted"].mean())
    return {
        "champion": champion,
        "challenger": challenger,
        "benchmark_rate": base_rate,
    }


def predict_targeting(models: dict, df: pd.DataFrame) -> dict:
    """Score ``df`` with the fitted targeting models."""
    return {
        "champion": models["champion"].predict(df),
        "challenger": models["challenger"].predict(df),
        "benchmark": np.full(len(df), models["benchmark_rate"]),
    }


def decile_conversion(
    y_true: np.ndarray, y_score: np.ndarray, n_deciles: int = 10
) -> pd.DataFrame:
    """Rank-ordering: conversion rate and capture per score decile.

    Decile 1 holds the highest predicted conversion propensity.
    """
    y_true = np.asarray(y_true)
    y_score = np.asarray(y_score, dtype=float)
    order = np.argsort(-y_score)
    sorted_true = y_true[order]
    total = int(sorted_true.sum())
    rows = []
    for d in range(n_deciles):
        chunk = sorted_true[
            d * len(sorted_true) // n_deciles:(d + 1) * len(sorted_true) // n_deciles
        ]
        rows.append(
            {
                "decile": d + 1,
                "n": int(len(chunk)),
                "conversions": int(chunk.sum()),
                "conversion_rate": float(chunk.mean()) if len(chunk) else 0.0,
                "capture_rate": float(chunk.sum() / total) if total else 0.0,
            }
        )
    return pd.DataFrame(rows)


def evaluate_targeting(y_true: np.ndarray, y_score: np.ndarray) -> dict:
    """Metric bundle for one targeting model's conversion scores."""
    return {
        "roc_auc": roc_auc(y_true, y_score),
        "ks": ks_statistic(y_true, y_score),
        "decile_conversion": decile_conversion(y_true, y_score),
    }


class ApprovalModel:
    """Calibrated approval-probability model (Platt-scaled logistic)."""

    def __init__(self) -> None:
        self.scaler = StandardScaler()
        base = LogisticRegression(max_iter=1000, C=1.0)
        self.model = CalibratedClassifierCV(base, method="sigmoid", cv=3)

    def fit(self, df: pd.DataFrame) -> "ApprovalModel":
        """Fit on converted members only (approval is undefined otherwise)."""
        converted = df[df["converted"] == 1]
        x = self.scaler.fit_transform(_feature_matrix(converted))
        self.model.fit(x, converted["approved"].to_numpy())
        return self

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        x = self.scaler.transform(_feature_matrix(df))
        return self.model.predict_proba(x)[:, 1]


def approval_certainty(prob: np.ndarray) -> dict:
    """Approval-certainty split of calibrated approval probabilities.

    High-certainty approve: p >= 0.8. High-certainty decline: p <= 0.2.
    The rest are uncertain and need more evidence or a manual review.
    """
    prob = np.asarray(prob, dtype=float)
    n = len(prob)
    return {
        "high_certainty_approve": round(float(np.mean(prob >= 0.8)), 4),
        "high_certainty_decline": round(float(np.mean(prob <= 0.2)), 4),
        "uncertain_middle": round(
            float(np.mean((prob > 0.2) & (prob < 0.8))), 4
        ),
        "n": n,
    }


def generate_offer_ranking(
    n_members: int = N_RANKING_MEMBERS, seed: int = RNG_SEED
) -> pd.DataFrame:
    """Generate a next-best-offer ranking frame: each member x 3 offers.

    Each member has one preferred product type. The shown offer converts
    more often when it matches that preference, which is what the
    ranking model has to discover. Clicks on each product type in the
    last 90 days are the observable proxy for the preference (the
    preferred type draws ~2.5 clicks, others ~0.7), so the model can
    learn affinity from clicks but cannot recover the preference
    exactly — a small latent match bonus (+0.3 log-odds) remains.
    Relevance is graded from the outcome: 2 = converted and approved,
    1 = converted but not approved, 0 = no conversion.
    """
    rng = np.random.default_rng(seed)
    feats = _member_features(rng, n_members)
    preferred = rng.choice(OFFER_TYPES, size=n_members)
    rows = []
    for i in range(n_members):
        member = {k: v[i] for k, v in feats.items()}
        for offer in OFFER_TYPES:
            apr = float(rng.uniform(*OFFER_APR[offer]))
            clicks = int(
                rng.poisson(2.5 if offer == preferred[i] else 0.7)
            )
            bonus = np.array([0.3]) if offer == preferred[i] else np.array([0.0])
            p_convert = float(
                _sigmoid(
                    _conversion_logit(
                        member,
                        np.array([apr]),
                        bonus,
                        offer_clicks=np.array([clicks]),
                    )
                )[0]
            )
            converted = int(rng.binomial(1, p_convert))
            p_approve = float(
                _sigmoid(np.asarray([_approval_logit(member)]))[0]
            )
            approved = int(rng.binomial(1, p_approve)) if converted else 0
            rows.append(
                {
                    "member_id": i,
                    "preferred_type": preferred[i],
                    **member,
                    "offer_type": offer,
                    "offer_apr": round(apr, 2),
                    "offer_clicks_90d": clicks,
                    "converted": converted,
                    "approved": approved,
                    "relevance": 2 if (converted and approved) else (
                        1 if converted else 0
                    ),
                }
            )
    return pd.DataFrame(rows)


def _ndcg_at_k(relevances: np.ndarray, k: int = 3) -> float:
    """NDCG@k for one member's ranked relevance list (graded 0/1/2)."""
    rel = np.asarray(relevances, dtype=float)[:k]
    gains = (2.0 ** rel - 1.0) / np.log2(np.arange(2, len(rel) + 2))
    dcg = float(gains.sum())
    ideal = np.sort(rel)[::-1]
    ideal_gains = (2.0 ** ideal - 1.0) / np.log2(
        np.arange(2, len(ideal) + 2)
    )
    idcg = float(ideal_gains.sum())
    return dcg / idcg if idcg > 0 else 0.0


def rank_offers(
    ranking_df: pd.DataFrame,
    conversion_model,
    approval_model,
    popularity_rates: dict,
) -> dict:
    """Score next-best-offer ranking: model rank vs popularity baseline.

    The model ranks each member's offers by predicted conversion x
    calibrated approval probability. The baseline ranks by the
    population conversion rate of each offer type. Returns mean NDCG@3
    for both, plus the share of members whose top-ranked offer is the
    one they converted on.
    """
    conv = conversion_model.predict(ranking_df)
    appr = approval_model.predict(ranking_df)
    scored = ranking_df.assign(score=conv * appr)
    model_ndcgs, base_ndcgs = [], []
    top_converted = 0
    base_top_converted = 0
    for _, group in scored.groupby("member_id"):
        model_order = group.sort_values("score", ascending=False)
        model_ndcgs.append(_ndcg_at_k(model_order["relevance"].to_numpy()))
        base_order = group.assign(
            pop=group["offer_type"].map(popularity_rates)
        ).sort_values("pop", ascending=False)
        base_ndcgs.append(_ndcg_at_k(base_order["relevance"].to_numpy()))
        if int(model_order.iloc[0]["converted"]) == 1:
            top_converted += 1
        if int(base_order.iloc[0]["converted"]) == 1:
            base_top_converted += 1
    n_members = scored["member_id"].nunique()
    return {
        "model_ndcg3": round(float(np.mean(model_ndcgs)), 4),
        "baseline_ndcg3": round(float(np.mean(base_ndcgs)), 4),
        "top_offer_converted_share": round(top_converted / n_members, 4),
        "baseline_top_offer_converted_share": round(
            base_top_converted / n_members, 4
        ),
        "n_members": int(n_members),
    }


def generate_targeting_experiment(
    n: int = N_EXPERIMENT, seed: int = RNG_SEED
) -> pd.DataFrame:
    """Generate a seeded A/B test: model-ranked targeting vs popularity.

    Control members see the most popular offer (personal loan, the
    highest base conversion type in this simulation). Treated members
    see the model-picked offer, which matches their preferred type 80%
    of the time and a random other type otherwise. A matched offer
    converts better (+0.6 log-odds), so the lift measures targeting
    quality. Approval is drawn among converters from bureau features.
    """
    rng = np.random.default_rng(seed)
    feats = _member_features(rng, n)
    preferred = rng.choice(OFFER_TYPES, size=n)
    arm = rng.choice(["control", "treated"], size=n)
    # Popularity control: personal loan converts best at baseline APRs.
    popular = "personal_loan"
    shown = np.where(arm == "control", popular, preferred)
    model_pick = rng.binomial(1, 0.8, size=n).astype(bool)
    shown = np.where(
        (arm == "treated") & ~model_pick,
        rng.choice([t for t in OFFER_TYPES if t != popular], size=n),
        shown,
    )
    offer_apr = np.array(
        [rng.uniform(*OFFER_APR[t]) for t in shown]
    )
    match = (shown == preferred).astype(float)
    p_convert = _sigmoid(
        _conversion_logit(feats, offer_apr, match_bonus=0.6 * match)
    )
    converted = rng.binomial(1, p_convert).astype(int)
    p_approve = _sigmoid(_approval_logit(feats))
    approved = np.where(
        converted == 1, rng.binomial(1, p_approve), 0
    ).astype(int)
    return pd.DataFrame(
        {
            **feats,
            "preferred_type": preferred,
            "arm": arm,
            "shown_offer": shown,
            "offer_apr": np.round(offer_apr, 2),
            "converted": converted,
            "approved": approved,
        }
    )


def ab_readout(df: pd.DataFrame, seed: int = RNG_SEED) -> dict:
    """A/B readout: conversion lift, Welch t-test, bootstrap 95% CI.

    The approval-rate guardrail flags if the treated arm's approval
    rate among converters falls more than 1 point below control. A
    breach is expected when targeting expands the funnel: conversion
    lifts come from more marginal members, so the approval rate among
    converters can fall even as conversions rise. Approvals per 1,000
    members in each arm are reported alongside, so the net effect is
    visible rather than hidden behind the conversion lift.
    """
    control = df[df["arm"] == "control"]
    treated = df[df["arm"] == "treated"]
    c_conv = control["converted"].to_numpy(dtype=float)
    t_conv = treated["converted"].to_numpy(dtype=float)
    c_rate = float(c_conv.mean())
    t_rate = float(t_conv.mean())
    lift_pp = round((t_rate - c_rate) * 100, 2)
    lift_pct = round((t_rate / c_rate - 1.0) * 100, 1) if c_rate else 0.0
    _, p_value = stats.ttest_ind(t_conv, c_conv, equal_var=False)
    rng = np.random.default_rng(seed)
    diffs = []
    for _ in range(2000):
        t_boot = rng.choice(t_conv, size=len(t_conv), replace=True).mean()
        c_boot = rng.choice(c_conv, size=len(c_conv), replace=True).mean()
        diffs.append((t_boot - c_boot) * 100)
    ci_low, ci_high = np.percentile(diffs, [2.5, 97.5])
    c_appr = float(
        control.loc[control["converted"] == 1, "approved"].mean()
    )
    t_appr = float(
        treated.loc[treated["converted"] == 1, "approved"].mean()
    )
    appr_gap_pp = round((t_appr - c_appr) * 100, 2)
    return {
        "control_n": int(len(control)),
        "treated_n": int(len(treated)),
        "control_conversion": round(c_rate, 4),
        "treated_conversion": round(t_rate, 4),
        "lift_pp": lift_pp,
        "lift_pct": lift_pct,
        "p_value": round(float(p_value), 4),
        "ci_low_pp": round(float(ci_low), 2),
        "ci_high_pp": round(float(ci_high), 2),
        "control_approval": round(c_appr, 4),
        "treated_approval": round(t_appr, 4),
        "approval_gap_pp": appr_gap_pp,
        "guardrail_breached": bool(appr_gap_pp < -1.0),
        "control_approvals_per_1000": round(c_rate * c_appr * 1000, 1),
        "treated_approvals_per_1000": round(t_rate * t_appr * 1000, 1),
    }


def build_targeting_section(
    champion_eval: dict,
    challenger_eval: dict,
    calibration: pd.DataFrame,
    certainty: dict,
    ranking: dict,
    experiment: dict,
) -> str:
    """Render the targeting & approval section of the validation report."""
    top = champion_eval["decile_conversion"].iloc[0]
    base_rate = champion_eval["decile_conversion"]["conversion_rate"].mean()
    lines = [
        "",
        "=" * 70,
        "13. PARTNER DECISION SCIENCE - TARGETING & APPROVAL MODELS",
        "=" * 70,
        "Targeting model (conversion propensity, champion logistic vs "
        "gradient-boosting challenger):",
        f"  champion ROC-AUC {champion_eval['roc_auc']:.3f}  KS "
        f"{champion_eval['ks']:.3f}",
        f"  challenger ROC-AUC {challenger_eval['roc_auc']:.3f}  KS "
        f"{challenger_eval['ks']:.3f}",
        f"  top decile converts at {top['conversion_rate']:.1%} "
        f"(base rate {base_rate:.1%}), capturing {top['capture_rate']:.1%} "
        f"of all conversions.",
        "",
        "Approval model (Platt-calibrated logistic, fit on converters):",
        f"  worst decile calibration gap "
        f"{(calibration['mean_predicted'] - calibration['observed_rate']).abs().max():.3f} "
        f"(mean predicted vs observed approval per decile).",
        f"  approval certainty: {certainty['high_certainty_approve']:.1%} "
        f"high-certainty approve, {certainty['high_certainty_decline']:.1%} "
        f"high-certainty decline, {certainty['uncertain_middle']:.1%} "
        f"uncertain middle (n={certainty['n']:,}).",
        "",
        "Next-best-offer ranking (conversion x calibrated approval prob):",
        f"  model NDCG@3 {ranking['model_ndcg3']:.3f} vs popularity "
        f"baseline {ranking['baseline_ndcg3']:.3f}; top-ranked offer "
        f"converted for {ranking['top_offer_converted_share']:.1%} of "
        f"members vs {ranking['baseline_top_offer_converted_share']:.1%} "
        f"for the popularity top pick (n={ranking['n_members']:,}).",
        "",
        "A/B readout (model-ranked targeting vs popularity control):",
        f"  conversion {experiment['control_conversion']:.1%} control vs "
        f"{experiment['treated_conversion']:.1%} treated: "
        f"lift {experiment['lift_pp']:+.2f}pp ({experiment['lift_pct']:+.1f}%), "
        f"Welch p={experiment['p_value']:.4f}, "
        f"bootstrap 95% CI ({experiment['ci_low_pp']:+.2f}, "
        f"{experiment['ci_high_pp']:+.2f})pp.",
        f"  approval guardrail: treated approval "
        f"{experiment['treated_approval']:.1%} vs control "
        f"{experiment['control_approval']:.1%} "
        f"({experiment['approval_gap_pp']:+.2f}pp) - "
        f"{'BREACHED' if experiment['guardrail_breached'] else 'within guardrail'}. "
        f"Approvals per 1,000 members: {experiment['control_approvals_per_1000']:.1f} "
        f"control vs {experiment['treated_approvals_per_1000']:.1f} treated - "
        f"conversion-only targeting pulled in more marginal members, so rank "
        f"offers by conversion x approval probability instead.",
    ]
    return "\n".join(lines)
