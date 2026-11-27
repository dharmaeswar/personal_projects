"""Tests for the paid-amount ML scoring: training, scoring, flagging."""
import numpy as np
import pandas as pd
import pytest

from claims_platform.data import make_claims, make_members
from claims_platform.ml import score_claims, train_paid_model
from claims_platform.transforms import (
    dedupe_latest, filter_valid, join_member_dim, with_derived,
)


@pytest.fixture(scope="module")
def cleansed():
    raw = make_claims()
    joined = join_member_dim(dedupe_latest(raw), make_members())
    clean, _ = filter_valid(joined)
    return with_derived(clean)


@pytest.fixture(scope="module")
def trained(cleansed):
    model, metrics, residual_std = train_paid_model(cleansed)
    return {"model": model, "metrics": metrics, "residual_std": residual_std}


def test_model_trains_with_sane_metrics(trained):
    m = trained["metrics"]
    assert 0 < m["test_mae"] < 1000  # paid amounts run $100-$8,500
    assert 0.5 < m["test_r2"] < 1.0
    assert m["train_residual_std"] > 0
    assert m["train_rows"] + m["test_rows"] == 296


def test_training_is_deterministic(cleansed):
    _, m1, _ = train_paid_model(cleansed)
    _, m2, _ = train_paid_model(cleansed)
    assert m1 == m2


def test_scores_cover_every_cleansed_claim(cleansed, trained):
    scores = score_claims(trained["model"], trained["residual_std"], cleansed)
    assert len(scores) == 296
    assert scores["claim_id"].is_unique
    assert scores["predicted_paid"].notna().all()
    assert scores["residual_z"].notna().all()
    assert np.isfinite(scores["residual_z"]).all()
    assert set(scores.columns) == {
        "claim_id", "member_id", "service_date", "plan", "diag_group",
        "billed_amount", "paid_amount", "predicted_paid", "residual",
        "residual_z", "model_flag"}


def test_flagged_claims_are_real_outliers(cleansed, trained):
    scores = score_claims(trained["model"], trained["residual_std"], cleansed)
    flagged = scores[scores["model_flag"] == "high_residual"]
    assert (flagged["residual_z"].abs() >= 3.0).all()
    assert len(flagged) < 15  # a handful of review candidates, not a flood
    unflagged = scores[scores["model_flag"] == ""]
    assert (unflagged["residual_z"].abs() < 3.0).all()


def test_planted_outlier_gets_flagged(cleansed, trained):
    row = cleansed.iloc[[0]].copy()
    # Paid 5x the billed amount: no legitimate adjustment explains this.
    row["paid_amount"] = row["billed_amount"] * 5
    scores = score_claims(trained["model"], trained["residual_std"], row)
    assert scores.iloc[0]["model_flag"] == "high_residual"
    assert scores.iloc[0]["residual_z"] > 3.0


def test_scoring_is_deterministic(cleansed, trained):
    a = score_claims(trained["model"], trained["residual_std"], cleansed)
    b = score_claims(trained["model"], trained["residual_std"], cleansed)
    pd.testing.assert_frame_equal(a, b)
