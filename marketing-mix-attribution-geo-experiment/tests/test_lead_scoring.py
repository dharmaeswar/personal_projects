"""Tests for the lead scoring module: generation, fit, calibration, routing."""

import numpy as np
import pandas as pd

from mmm_geo.lead_scoring import (
    ENRICHMENT_FLOOR,
    assign_mql_tiers,
    calibration_table,
    fit_lead_scorer,
    generate_leads,
    lead_scoring_summary_lines,
    lead_value,
)


def test_generate_leads_is_seeded_and_shaped():
    a = generate_leads()
    b = generate_leads()
    assert len(a) == 2000
    assert a.equals(b)
    assert set(a["channel"].unique()) <= {
        "paid_search", "paid_social", "organic_search", "referral", "outbound"}
    assert a["mql"].isin([0, 1]).all()
    assert 0.05 < a["mql"].mean() < 0.45


def test_fit_scores_are_probabilities_with_real_signal():
    leads = generate_leads()
    fit = fit_lead_scorer(leads)
    scored = fit["scored"]
    assert scored["score"].between(0, 1).all()
    # The known-truth signal is strong: 5-fold CV AUC must clear 0.72.
    # (A single holdout split moves by ~0.03, so CV is the stable check.)
    assert fit["cv_auc"] > 0.72
    assert abs(fit["train_auc"] - fit["test_auc"]) < 0.10


def test_demo_and_trial_raise_the_score():
    leads = generate_leads()
    fit = fit_lead_scorer(leads)
    scored = fit["scored"]
    assert scored.loc[scored["demo_requested"] == 1, "score"].mean() > \
        scored.loc[scored["demo_requested"] == 0, "score"].mean()
    assert scored.loc[scored["trial_started"] == 1, "score"].mean() > \
        scored.loc[scored["trial_started"] == 0, "score"].mean()


def test_calibration_bands_are_monotone_and_close():
    leads = generate_leads()
    fit = fit_lead_scorer(leads)
    table = calibration_table(fit["scored"], bins=5)
    assert len(table) == 5
    observed = [r["observed_rate"] for r in table]
    assert observed == sorted(observed)
    # No band's observed rate may be more than 15 points from predicted.
    assert all(abs(r["gap"]) < 0.15 for r in table)


def test_competitor_leads_are_excluded():
    leads = generate_leads()
    fit = fit_lead_scorer(leads)
    routed = assign_mql_tiers(fit["scored"])
    comp = routed[routed["is_competitor"] == 1]
    assert len(comp) > 0
    assert (comp["tier"] == "excluded").all()


def test_low_enrichment_goes_to_nurture_not_sales():
    leads = generate_leads()
    fit = fit_lead_scorer(leads)
    routed = assign_mql_tiers(fit["scored"])
    thin = routed[(routed["enrichment"] < ENRICHMENT_FLOOR)
                  & (routed["is_competitor"] == 0)]
    assert len(thin) > 0
    assert (thin["tier"] == "nurture").all()


def test_demo_request_fast_tracks_to_hot():
    leads = generate_leads()
    fit = fit_lead_scorer(leads)
    routed = assign_mql_tiers(fit["scored"])
    demo = routed[(routed["demo_requested"] == 1)
                  & (routed["is_competitor"] == 0)
                  & (routed["enrichment"] >= ENRICHMENT_FLOOR)]
    assert len(demo) > 0
    assert (demo["tier"] == "hot").all()


def test_lead_value_is_positive_and_scales_with_size():
    leads = generate_leads()
    fit = fit_lead_scorer(leads)
    routed = assign_mql_tiers(fit["scored"])
    value = lead_value(routed)
    assert value["total_expected_value"] > 0
    assert value["mean_expected_value"] > 0
    bands = value["by_size_band"]
    assert bands["large"]["mean"] > bands["small"]["mean"]


def test_summary_lines_mention_key_results():
    leads = generate_leads()
    fit = fit_lead_scorer(leads)
    routed = assign_mql_tiers(fit["scored"])
    value = lead_value(routed)
    lines = lead_scoring_summary_lines(
        fit, calibration_table(fit["scored"]), routed, value)
    text = "\n".join(lines)
    assert "Lead scoring" in text
    assert "ROC-AUC" in text
    assert "MQL tiers" in text
    assert "Expected pipeline value" in text
