"""Seeded synthetic credit-card applicant data for the deep-learning validator.

All data is synthetic and seeded. No real borrower, bank, or customer data
is used, and nothing here is a claim about any real institution.

Each row is one credit-card application: numeric fields (credit score,
income, utilisation, history length, delinquencies, inquiries, balances)
plus a short free-text employment note. The text field is encoded as
keyword-count features, the way a data scientist turns a short text
field into model inputs without an external NLP library.
"""
import numpy as np
import pandas as pd

SEED = 20261127
N_ROWS = 6000

NUMERIC_FEATURES = [
    "credit_score",
    "annual_income",
    "debt_to_income",
    "revolving_utilization",
    "history_years",
    "delinquencies_12m",
    "inquiries_6m",
    "open_accounts",
    "requested_limit",
]

# Keywords counted in the free-text employment note.
TEXT_KEYWORDS = [
    "full-time",
    "part-time",
    "self-employed",
    "contractor",
    "retired",
    "student",
]

EMPLOYMENT_NOTES = [
    "employed full-time retail",
    "employed full-time healthcare",
    "employed full-time warehouse",
    "employed part-time food service",
    "employed part-time retail",
    "self-employed contractor",
    "self-employed consultant",
    "employed full-time office",
    "retired pension income",
    "student part-time campus job",
    "employed full-time manufacturing",
    "contractor gig work",
]

# Origination quarters, oldest first, for vintage backtesting.
QUARTERS = ["2024Q1", "2024Q2", "2024Q3", "2024Q4",
            "2025Q1", "2025Q2", "2025Q3", "2025Q4"]


def generate(n=N_ROWS, seed=SEED):
    """Return a DataFrame of synthetic applications with a default flag."""
    rng = np.random.default_rng(seed)
    credit_score = rng.normal(690, 70, n).clip(300, 850)
    annual_income = rng.lognormal(np.log(62000), 0.55, n).clip(12000, 400000)
    debt_to_income = rng.beta(2.2, 5.0, n) * 0.9
    revolving_utilization = rng.beta(2.0, 4.0, n)
    history_years = rng.gamma(4.0, 2.5, n).clip(0.2, 40)
    delinquencies_12m = rng.poisson(0.35, n).clip(0, 8)
    inquiries_6m = rng.poisson(1.1, n).clip(0, 10)
    open_accounts = rng.poisson(6, n).clip(1, 25)
    requested_limit = rng.lognormal(np.log(6000), 0.7, n).clip(500, 50000)
    notes = rng.choice(EMPLOYMENT_NOTES, size=n)
    quarter = rng.choice(QUARTERS, size=n)

    # Latent default log-odds: worse score / higher utilisation / higher
    # debt load / more delinquencies raise risk; longer history lowers it.
    logit = (
        -1.9
        - 0.011 * (credit_score - 690)
        + 1.6 * revolving_utilization
        + 2.2 * debt_to_income
        + 0.55 * delinquencies_12m
        + 0.18 * inquiries_6m
        - 0.05 * history_years
        + 0.25 * (notes == "self-employed contractor")
        + 0.20 * (notes == "contractor gig work")
        - 0.30 * (notes == "retired pension income")
    )
    prob = 1.0 / (1.0 + np.exp(-logit))
    defaulted = (rng.random(n) < prob).astype(int)

    df = pd.DataFrame({
        "credit_score": np.round(credit_score).astype(int),
        "annual_income": np.round(annual_income).astype(int),
        "debt_to_income": np.round(debt_to_income, 4),
        "revolving_utilization": np.round(revolving_utilization, 4),
        "history_years": np.round(history_years, 1),
        "delinquencies_12m": delinquencies_12m.astype(int),
        "inquiries_6m": inquiries_6m.astype(int),
        "open_accounts": open_accounts.astype(int),
        "requested_limit": np.round(requested_limit).astype(int),
        "employment_note": notes,
        "origination_quarter": quarter,
        "defaulted": defaulted,
    })
    return df


def encode_text(df):
    """Count each keyword in the employment note; returns a DataFrame."""
    text = df["employment_note"].astype(str).str.lower()
    out = {}
    for kw in TEXT_KEYWORDS:
        out["txt_" + kw.replace("-", "_")] = text.str.contains(kw, regex=False).astype(int)
    return pd.DataFrame(out, index=df.index)


def feature_matrix(df):
    """Numeric + text-keyword features as a float NumPy array."""
    num = df[NUMERIC_FEATURES].astype(float)
    txt = encode_text(df)
    X = pd.concat([num, txt], axis=1)
    return X.to_numpy(dtype=float), list(X.columns)


def time_split(df, train_quarters=QUARTERS[:5], val_quarters=QUARTERS[5:6],
               test_quarters=QUARTERS[6:]):
    """Split by origination quarter: train on the past, test on the future.

    Time-ordered splits only — a model is never tested on applications
    originated before the ones it trained on, so there is no look-ahead.
    """
    train = df[df["origination_quarter"].isin(train_quarters)]
    val = df[df["origination_quarter"].isin(val_quarters)]
    test = df[df["origination_quarter"].isin(test_quarters)]
    return train, val, test


def standardize(X_train, X):
    """Z-score using train means/stds; returns scaled X, mean, std."""
    mean = X_train.mean(axis=0)
    std = X_train.std(axis=0)
    std = np.where(std == 0, 1.0, std)
    return (X - mean) / std, mean, std
