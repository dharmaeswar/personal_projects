"""Tests for the production scoring path (dl_credit/scoring.py)."""
import numpy as np
import pytest

from dl_credit.data import generate
from dl_credit.mlp import MLPClassifier
from dl_credit.scoring import (band_distribution, check_record,
                               export_artifact, load_artifact, save_artifact,
                               score_batch)


def _fitted():
    rng = np.random.default_rng(3)
    X = rng.normal(size=(120, 6))
    y = (X[:, 0] + X[:, 1] > 0).astype(int)
    model = MLPClassifier(hidden=(8, 4), epochs=30, patience=10)
    model.fit(X, y)
    names = ["f%d" % i for i in range(6)]
    artifact = export_artifact(model, X.mean(axis=0), X.std(axis=0), names)
    return model, artifact, X


def _valid_record():
    row = generate(n=200).iloc[0]
    record = {k: row[k] for k in
              ["credit_score", "annual_income", "debt_to_income",
               "revolving_utilization", "history_years", "delinquencies_12m",
               "inquiries_6m", "open_accounts", "requested_limit",
               "employment_note"]}
    return {k: (v.item() if hasattr(v, "item") else v)
            for k, v in record.items()}


def test_export_load_roundtrip_scores_match():
    model, artifact, X = _fitted()
    loaded, art = load_artifact(artifact)
    mean = np.array(art["mean"])
    std = np.array(art["std"])
    expected = model.predict_proba((X - mean) / std)
    got = loaded.predict_proba((X - mean) / std)
    assert np.array_equal(expected, got)


def test_artifact_survives_disk_roundtrip(tmp_path):
    _, artifact, _ = _fitted()
    path = tmp_path / "model.json"
    save_artifact(artifact, str(path))
    loaded, art = load_artifact(str(path))
    assert art["feature_names"] == artifact["feature_names"]
    assert loaded.weights_[0].shape == np.array(artifact["weights"][0]).shape


def test_load_artifact_rejects_wrong_format():
    with pytest.raises(ValueError):
        load_artifact({"format": "something-else/9"})


def test_export_unfitted_model_raises():
    with pytest.raises(ValueError):
        export_artifact(MLPClassifier(), np.zeros(3), np.ones(3),
                        ["a", "b", "c"])


def test_check_record_accepts_valid_record():
    assert check_record(_valid_record()) == []


def test_check_record_flags_missing_field():
    record = _valid_record()
    del record["credit_score"]
    assert "missing field: credit_score" in check_record(record)


def test_check_record_flags_out_of_range():
    record = _valid_record()
    record["credit_score"] = 200
    problems = check_record(record)
    assert any(p.startswith("out of range") and "credit_score" in p
               for p in problems)


def test_check_record_flags_non_numeric_and_non_text():
    record = _valid_record()
    record["annual_income"] = "unknown"
    record["employment_note"] = 42
    problems = check_record(record)
    assert "not a number: annual_income" in problems
    assert "not text: employment_note" in problems


def test_score_batch_scores_valid_and_rejects_invalid():
    _, artifact, _ = _fitted()
    # Artifact was fitted on 6 generic features, so use the real data
    # pipeline instead: rebuild an artifact over the real feature set.
    from dl_credit.data import feature_matrix, standardize, time_split
    df = generate(n=600)
    train, _, _ = time_split(df)
    X, names = feature_matrix(train)
    Xs, mean, std = standardize(X, X)
    y = train["defaulted"].to_numpy()
    model = MLPClassifier(hidden=(8, 4), epochs=20, patience=8)
    model.fit(Xs, y)
    real_artifact = export_artifact(model, mean, std, names)

    good = _valid_record()
    bad = _valid_record()
    bad["revolving_utilization"] = 7.5
    scores, rejections = score_batch(real_artifact, [good, bad, good])
    assert len(scores) == 2
    assert len(rejections) == 1
    assert rejections[0]["index"] == 1
    assert np.all((scores >= 0.0) & (scores <= 1.0))
    # Same record in, same score out — the artifact path is deterministic.
    assert scores[0] == scores[1]


def test_score_batch_all_invalid_returns_empty():
    _, artifact, _ = _fitted()
    scores, rejections = score_batch(artifact, [{"credit_score": "x"}])
    assert len(scores) == 0
    assert len(rejections) == 1


def test_band_distribution_shares_sum_to_one():
    rng = np.random.default_rng(0)
    scores = rng.random(500)
    reference = rng.random(500)
    bands = band_distribution(scores, reference)
    assert len(bands) == 4
    assert abs(sum(b["batch_share"] for b in bands) - 1.0) < 1e-9
    assert abs(sum(b["reference_share"] for b in bands) - 1.0) < 1e-9
    assert all(b["share_gap"] >= 0.0 for b in bands)
