"""Credit-risk analytics for a Prosper-style credit/fraud data science role.

Extends the fraud-model validation suite with the checks a credit risk
analytics team runs on personal-loan decisions:

- credit bureau feature engineering (score bands, utilisation bands,
  inquiry flags, debt-to-income proxy, loan-to-income ratio),
- score-band performance (bad rate and population share per bureau band,
  plus the Gini coefficient of the bureau score against the bad label),
- decision-cutoff analysis (approval rate, bad rate among approved, and
  the share of bads a cutoff declines, at several candidate cutoffs),
- vintage analysis (bad rate by origination month, so a worsening
  vintage is visible before the whole book seasons),
- roll-rate analysis (early delinquency, 30 days past due, rolling to
  90 days past due, the transition a credit team monitors monthly).

All data is synthetic and seeded. No real borrower, bureau, or loan data
is used, and nothing here is a claim about any real lender.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

RNG_SEED = 2026
N_APPLICATIONS = 12_000

# Bureau score bands (FICO-style ranges).
SCORE_BANDS = [(300, 579), (580, 619), (620, 659), (660, 699), (700, 739), (740, 850)]
SCORE_BAND_LABELS = ["300-579", "580-619", "620-659", "660-699", "700-739", "740-850"]

# Feature columns added by build_credit_features.
CREDIT_FEATURES = [
    "score_band",
    "utilisation_band",
    "recent_inquiries",
    "dti_proxy",
    "loan_to_income",
]


def _sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-x))


def generate_credit_applications(
    n: int = N_APPLICATIONS, seed: int = RNG_SEED
) -> pd.DataFrame:
    """Generate ``n`` seeded synthetic personal-loan applications.

    ``is_bad`` marks a loan that defaults within 12 months of booking.
    Its probability is driven by bureau score, utilisation, delinquencies
    and inquiries, so the bureau score carries real rank-ordering signal.
    ``dpd_30`` / ``dpd_90`` mark early and severe delinquency for the
    roll-rate check, and ``vintage_month`` (0..11) is the booking month.
    """
    rng = np.random.default_rng(seed)
    bureau_score = np.clip(
        rng.normal(loc=685.0, scale=62.0, size=n), 300, 850
    ).astype(int)
    utilisation = np.clip(rng.beta(a=2.0, b=5.0, size=n), 0.0, 1.0)
    inquiries_12m = rng.poisson(lam=1.1, size=n)
    delinquencies_24m = rng.poisson(lam=0.4, size=n)
    annual_income = rng.lognormal(mean=11.0, sigma=0.55, size=n)
    loan_amount = rng.lognormal(mean=9.6, sigma=0.6, size=n)
    term_months = rng.choice([36, 60], size=n, p=[0.65, 0.35])
    vintage_month = rng.integers(0, 12, size=n)

    logit = (
        -2.9
        - 0.011 * (bureau_score - 685.0)
        + 1.6 * utilisation
        + 0.45 * delinquencies_24m
        + 0.18 * inquiries_12m
        - 0.25 * np.log1p(annual_income / 50_000.0)
    )
    p_bad = _sigmoid(logit)
    is_bad = rng.binomial(1, p_bad).astype(int)

    # Early delinquency is a noisy precursor of a bad loan; 90 DPD is rarer.
    dpd_30 = rng.binomial(1, np.clip(p_bad * 0.55 + 0.01, 0, 1)).astype(int)
    dpd_90 = np.where(
        dpd_30 == 1,
        rng.binomial(1, np.clip(p_bad * 0.9 + 0.05, 0, 1)),
        rng.binomial(1, 0.002, size=n),
    ).astype(int)

    return pd.DataFrame(
        {
            "bureau_score": bureau_score,
            "utilisation": np.round(utilisation, 4),
            "inquiries_12m": inquiries_12m,
            "delinquencies_24m": delinquencies_24m,
            "annual_income": np.round(annual_income, 2),
            "loan_amount": np.round(loan_amount, 2),
            "term_months": term_months,
            "vintage_month": vintage_month,
            "dpd_30": dpd_30,
            "dpd_90": dpd_90,
            "is_bad": is_bad,
        }
    )


def build_credit_features(df: pd.DataFrame) -> pd.DataFrame:
    """Engineer credit-risk features from the raw application columns.

    ``score_band`` is the bureau-score band label; ``utilisation_band``
    buckets revolving utilisation into low / medium / high;
    ``recent_inquiries`` flags 3+ inquiries in 12 months;
    ``dti_proxy`` is loan amount over annual income (a debt-to-income
    proxy); ``loan_to_income`` is the same ratio as a plain float.
    """
    out = df.copy()
    bands = pd.cut(
        out["bureau_score"],
        bins=[299, 579, 619, 659, 699, 739, 850],
        labels=SCORE_BAND_LABELS,
    )
    out["score_band"] = bands.astype(str)
    out["utilisation_band"] = pd.cut(
        out["utilisation"],
        bins=[-0.01, 0.3, 0.6, 1.0],
        labels=["low", "medium", "high"],
    ).astype(str)
    out["recent_inquiries"] = (out["inquiries_12m"] >= 3).astype(int)
    out["dti_proxy"] = np.round(
        out["loan_amount"] / out["annual_income"], 4
    )
    out["loan_to_income"] = out["dti_proxy"]
    return out


def gini_coefficient(y_true: np.ndarray, score: np.ndarray) -> float:
    """Gini coefficient of ``score`` (higher = lower risk) vs ``y_true``.

    Computed as 2 * ROC-AUC - 1, where the AUC is for the score ranking
    good loans above bad loans. sklearn's AUC handles tied scores, so a
    constant score yields AUC 0.5 and Gini 0.
    """
    if len(np.unique(y_true)) < 2:
        return 0.0
    auc = roc_auc_score(1 - y_true, score)
    return float(round(2.0 * auc - 1.0, 4))


def score_band_performance(df: pd.DataFrame) -> pd.DataFrame:
    """Bad rate and population share per bureau-score band."""
    rows = []
    for label, (low, high) in zip(SCORE_BAND_LABELS, SCORE_BANDS):
        mask = (df["bureau_score"] >= low) & (df["bureau_score"] <= high)
        sub = df[mask]
        rows.append(
            {
                "score_band": label,
                "n": int(len(sub)),
                "share": round(float(len(sub) / max(len(df), 1)), 4),
                "bad_rate": (
                    round(float(sub["is_bad"].mean()), 4) if len(sub) else 0.0
                ),
            }
        )
    return pd.DataFrame(rows)


def decision_cutoff_analysis(
    df: pd.DataFrame, cutoffs: tuple[int, ...] = (620, 640, 660, 680)
) -> pd.DataFrame:
    """Approval outcomes at candidate bureau-score cutoffs.

    For each cutoff, approve applications at or above the score: the
    approval rate, the bad rate among approved loans, and the share of
    all bads the cutoff declines (bad capture).
    """
    rows = []
    total_bad = int(df["is_bad"].sum())
    for cutoff in cutoffs:
        approved = df[df["bureau_score"] >= cutoff]
        declined = df[df["bureau_score"] < cutoff]
        rows.append(
            {
                "cutoff": cutoff,
                "approval_rate": round(float(len(approved) / len(df)), 4),
                "approved_bad_rate": (
                    round(float(approved["is_bad"].mean()), 4)
                    if len(approved)
                    else 0.0
                ),
                "bad_capture": (
                    round(float(declined["is_bad"].sum() / total_bad), 4)
                    if total_bad
                    else 0.0
                ),
            }
        )
    return pd.DataFrame(rows)


def vintage_analysis(df: pd.DataFrame) -> pd.DataFrame:
    """Bad rate by origination (vintage) month, with booked counts."""
    rows = []
    for month in sorted(df["vintage_month"].unique()):
        sub = df[df["vintage_month"] == month]
        rows.append(
            {
                "vintage_month": int(month),
                "n": int(len(sub)),
                "bad_rate": round(float(sub["is_bad"].mean()), 4),
            }
        )
    return pd.DataFrame(rows)


def roll_rate(df: pd.DataFrame) -> dict:
    """Roll rate: share of 30-DPD loans that reach 90 DPD, and base rates."""
    n_30 = int(df["dpd_30"].sum())
    rolled = int(((df["dpd_30"] == 1) & (df["dpd_90"] == 1)).sum())
    return {
        "n_30dpd": n_30,
        "dpd_30_rate": round(float(n_30 / max(len(df), 1)), 4),
        "dpd_90_rate": round(float(df["dpd_90"].mean()), 4),
        "roll_30_to_90": round(float(rolled / n_30), 4) if n_30 else 0.0,
    }


def build_credit_risk_section(
    bands: pd.DataFrame,
    gini: float,
    cutoffs: pd.DataFrame,
    vintages: pd.DataFrame,
    rolls: dict,
) -> str:
    """Render the credit-risk section of the validation report."""
    lines = [
        "",
        "=" * 70,
        "10. CREDIT RISK ANALYTICS (Prosper-style personal-loan decisions)",
        "=" * 70,
        f"Bureau score Gini vs 12-month bad label: {gini:.4f}",
        "",
        "Score-band performance (bad rate falls as bureau score rises):",
    ]
    for _, row in bands.iterrows():
        lines.append(
            f"  {row['score_band']:>7}: n={row['n']:>5}  share={row['share']:.1%}  "
            f"bad_rate={row['bad_rate']:.1%}"
        )
    lines.append("")
    lines.append("Decision cutoffs (approve at or above the score):")
    for _, row in cutoffs.iterrows():
        lines.append(
            f"  cutoff {row['cutoff']}: approval={row['approval_rate']:.1%}  "
            f"approved bad rate={row['approved_bad_rate']:.1%}  "
            f"bad capture={row['bad_capture']:.1%}"
        )
    worst = vintages.loc[vintages["bad_rate"].idxmax()]
    best = vintages.loc[vintages["bad_rate"].idxmin()]
    lines.append("")
    lines.append(
        "Vintage bad rates range "
        f"{best['bad_rate']:.1%} (month {int(best['vintage_month'])}) to "
        f"{worst['bad_rate']:.1%} (month {int(worst['vintage_month'])}); "
        f"spread {worst['bad_rate'] - best['bad_rate']:.1%}."
    )
    lines.append(
        f"Roll rate: {rolls['dpd_30_rate']:.1%} of loans hit 30 DPD; "
        f"{rolls['roll_30_to_90']:.1%} of those roll to 90 DPD "
        f"(90 DPD base rate {rolls['dpd_90_rate']:.1%})."
    )
    return "\n".join(lines)
