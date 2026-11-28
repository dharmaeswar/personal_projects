"""Tests for the partner decision science targeting module."""

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

from fraud_validation.data import train_test_split
from fraud_validation.targeting import (
    ApprovalModel,
    OFFER_TYPES,
    ab_readout,
    approval_certainty,
    build_targeting_features,
    decile_conversion,
    evaluate_targeting,
    fit_targeting_models,
    generate_offer_ranking,
    generate_partner_offers,
    generate_targeting_experiment,
    predict_targeting,
    rank_offers,
)


def _offers():
    return generate_partner_offers(n=3000, seed=7)


def test_generation_is_deterministic_and_shaped():
    a = generate_partner_offers(n=500, seed=7)
    b = generate_partner_offers(n=500, seed=7)
    assert a.equals(b)
    assert len(a) == 500
    assert a["bureau_score"].between(300, 850).all()
    assert a["offer_type"].isin(OFFER_TYPES).all()
    assert a["converted"].isin([0, 1]).all()
    assert a["approved"].isin([0, 1]).all()
    # Nobody is approved without converting.
    assert a.loc[a["converted"] == 0, "approved"].sum() == 0
    assert 0.01 < a["converted"].mean() < 0.5
    assert 0.01 < a.loc[a["converted"] == 1, "approved"].mean() < 0.99


def test_targeting_features_cover_all_bands():
    feats = build_targeting_features(_offers())
    assert set(feats["score_band"].unique()) <= {
        "300-579", "580-619", "620-659", "660-699", "700-739", "740-850"
    }
    assert feats["utilisation_band"].isin(["low", "medium", "high"]).all()
    assert feats["engaged_90d"].isin([0, 1]).all()
    assert feats["apr_band"].isin(
        ["under-15", "15-20", "20-25", "over-25"]
    ).all()


def test_targeting_models_beat_base_rate():
    offers = _offers()
    train, test = train_test_split(offers, seed=7)
    models = fit_targeting_models(train)
    scores = predict_targeting(models, test)
    y = test["converted"].to_numpy()
    for name in ("champion", "challenger"):
        ev = evaluate_targeting(y, scores[name])
        assert 0.5 < ev["roc_auc"] < 1.0
        assert 0.0 < ev["ks"] < 1.0
    # Base-rate benchmark has no ranking power.
    assert evaluate_targeting(y, scores["benchmark"])["roc_auc"] == 0.5


def test_decile_conversion_top_beats_base():
    offers = _offers()
    train, test = train_test_split(offers, seed=7)
    models = fit_targeting_models(train)
    scores = predict_targeting(models, test)
    deciles = decile_conversion(
        test["converted"].to_numpy(), scores["champion"]
    )
    assert len(deciles) == 10
    assert abs(deciles["capture_rate"].sum() - 1.0) < 1e-6
    top = deciles.iloc[0]["conversion_rate"]
    base = test["converted"].mean()
    assert top > base


def test_approval_model_calibrated_and_certainty_splits():
    offers = generate_partner_offers(n=6000, seed=7)
    train, test = train_test_split(offers, seed=7)
    approval = ApprovalModel().fit(train)
    converted_test = test[test["converted"] == 1]
    prob = approval.predict(converted_test)
    assert len(prob) == len(converted_test)
    assert ((prob >= 0) & (prob <= 1)).all()
    # Calibration by quintile: worst gap stays small for a calibrated model.
    from fraud_validation.metrics import calibration_by_decile

    cal = calibration_by_decile(
        converted_test["approved"].to_numpy(), prob, n_deciles=5
    )
    worst = (cal["mean_predicted"] - cal["observed_rate"]).abs().max()
    assert worst < 0.15
    certainty = approval_certainty(prob)
    total = (
        certainty["high_certainty_approve"]
        + certainty["high_certainty_decline"]
        + certainty["uncertain_middle"]
    )
    assert abs(total - 1.0) < 0.01
    assert certainty["uncertain_middle"] > 0.0


def test_offer_ranking_beats_popularity_baseline():
    offers = _offers()
    train, _ = train_test_split(offers, seed=7)
    models = fit_targeting_models(train)
    approval = ApprovalModel().fit(train)
    ranking = generate_offer_ranking(n_members=500, seed=7)
    popularity = (
        offers.groupby("offer_type")["converted"].mean().to_dict()
    )
    result = rank_offers(
        ranking, models["champion"], approval, popularity
    )
    assert result["n_members"] == 500
    # Personalised ranking must beat the one-size-fits-all popularity
    # order on both NDCG and on the top pick actually converting.
    assert result["model_ndcg3"] > result["baseline_ndcg3"]
    assert (
        result["top_offer_converted_share"]
        > result["baseline_top_offer_converted_share"]
    )
    assert 0.0 <= result["top_offer_converted_share"] <= 1.0


def test_ranking_generation_is_deterministic():
    a = generate_offer_ranking(n_members=100, seed=7)
    b = generate_offer_ranking(n_members=100, seed=7)
    assert a.equals(b)
    assert len(a) == 300  # 100 members x 3 offers
    assert set(a["relevance"].unique()) <= {0, 1, 2}


def test_experiment_readout_lift_is_positive_and_significant():
    exp = generate_targeting_experiment(n=4000, seed=7)
    readout = ab_readout(exp, seed=7)
    assert readout["control_n"] + readout["treated_n"] == 4000
    assert readout["lift_pp"] > 0
    assert readout["p_value"] < 0.05
    assert readout["ci_low_pp"] > 0
    assert readout["control_approval"] > 0
    assert readout["treated_approval"] > 0
    # The guardrail flag must match the gap, and approvals per 1,000
    # members must be reported for both arms so a conversion lift that
    # pulls in marginal members is never hidden behind the lift alone.
    # Whether the guardrail fires is seed-dependent: the approval-rate
    # gap is a noisy selection effect, so the test asserts mechanics,
    # not a particular breach.
    assert readout["guardrail_breached"] == (
        readout["approval_gap_pp"] < -1.0
    )
    assert readout["control_approvals_per_1000"] > 0
    assert readout["treated_approvals_per_1000"] > 0
