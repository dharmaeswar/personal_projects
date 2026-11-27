import numpy as np
import pandas as pd

from dl_credit.data import (NUMERIC_FEATURES, TEXT_KEYWORDS, encode_text,
                            feature_matrix, generate, standardize, time_split)


def test_generate_is_seeded_and_shaped():
    a = generate()
    b = generate()
    assert a.equals(b)
    assert len(a) == 6000
    assert set(a["defaulted"].unique()) <= {0, 1}
    assert 0.05 < a["defaulted"].mean() < 0.4


def test_generate_ranges():
    df = generate()
    assert df["credit_score"].between(300, 850).all()
    assert df["revolving_utilization"].between(0, 1).all()
    assert df["debt_to_income"].between(0, 1).all()
    assert df["delinquencies_12m"].ge(0).all()


def test_text_encoding_counts_keywords():
    df = pd.DataFrame({"employment_note": [
        "employed full-time retail",
        "self-employed contractor",
        "retired pension income",
    ]})
    enc = encode_text(df)
    assert list(enc.columns) == ["txt_" + k.replace("-", "_") for k in TEXT_KEYWORDS]
    assert enc.iloc[0]["txt_full_time"] == 1
    assert enc.iloc[1]["txt_self_employed"] == 1
    assert enc.iloc[1]["txt_contractor"] == 1
    assert enc.iloc[2]["txt_retired"] == 1
    assert enc.iloc[2]["txt_full_time"] == 0


def test_feature_matrix_width():
    df = generate(n=200)
    X, names = feature_matrix(df)
    assert X.shape == (200, len(NUMERIC_FEATURES) + len(TEXT_KEYWORDS))
    assert names[: len(NUMERIC_FEATURES)] == NUMERIC_FEATURES
    assert np.isfinite(X).all()


def test_time_split_is_ordered_and_complete():
    df = generate()
    train, val, test = time_split(df)
    assert len(train) + len(val) + len(test) == len(df)
    assert set(train["origination_quarter"]) <= set(["2024Q1", "2024Q2", "2024Q3", "2024Q4", "2025Q1"])
    assert set(test["origination_quarter"]) == {"2025Q3", "2025Q4"}
    assert not set(train["origination_quarter"]) & set(test["origination_quarter"])


def test_standardize_uses_train_stats():
    rng = np.random.default_rng(0)
    Xtr = rng.normal(10, 2, (50, 3))
    X, mean, std = standardize(Xtr, Xtr)
    assert np.allclose(mean, 10, atol=0.6)
    assert np.allclose(X.mean(axis=0), 0, atol=1e-10)
    assert np.allclose(X.std(axis=0), 1, atol=1e-10)
