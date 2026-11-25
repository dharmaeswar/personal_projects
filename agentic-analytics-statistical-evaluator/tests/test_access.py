"""Tests for the Access propensity, wallet & attrition models."""

import math

from agentic_stats.access import (
    attrition_by_engagement, auc, build_access_dataset, calibration,
    fit_logistic, fit_ols, kaplan_meier, predict_proba, render_access_report,
    run_access_eval,
)


def test_dataset_is_deterministic_and_complete():
    first = build_access_dataset()
    second = build_access_dataset()
    assert first == second
    assert len(first) == 240
    for row in first:
        for field in ("client_id", "meetings_90d", "research_reads",
                      "events_attended", "tenure_months",
                      "prior_wallet_usd_m", "attended", "wallet_usd_m",
                      "share_of_wallet", "attrited", "months_to_attrition"):
            assert field in row
        assert 0.0 <= row["share_of_wallet"] <= 1.0
        if not row["attrited"]:
            assert row["months_to_attrition"] is None
        else:
            assert 1 <= row["months_to_attrition"] <= 12


def test_outcome_rates_are_informative_not_degenerate():
    rows = build_access_dataset()
    attended = sum(1 for r in rows if r["attended"]) / len(rows)
    attrited = sum(1 for r in rows if r["attrited"]) / len(rows)
    assert 0.1 < attended < 0.9
    assert 0.05 < attrited < 0.6


def test_auc_known_cases():
    assert auc([0.9, 0.8, 0.2, 0.1], [1, 1, 0, 0]) == 1.0
    assert auc([0.1, 0.2, 0.8, 0.9], [1, 1, 0, 0]) == 0.0
    assert auc([0.5, 0.5, 0.5, 0.5], [1, 1, 0, 0]) == 0.5


def test_auc_needs_both_classes():
    try:
        auc([0.1, 0.2], [1, 1])
    except ValueError:
        return
    raise AssertionError("expected ValueError for single-class labels")


def test_logistic_fit_beats_intercept_only():
    rows = build_access_dataset()
    model = fit_logistic(rows)
    assert model["train_log_loss"] < 0.65  # intercept-only is ~0.67
    assert all(math.isfinite(w) for w in model["weights"])
    # Meetings help attendance: its weight is positive and largest.
    idx = model["features"].index("meetings_90d")
    assert model["weights"][idx] > 0
    assert model["weights"][idx] == max(model["weights"])


def test_predict_proba_in_range():
    rows = build_access_dataset()
    model = fit_logistic(rows)
    for row in rows[:20]:
        p = predict_proba(model, row)
        assert 0.0 <= p <= 1.0


def test_ols_recovers_known_coefficients():
    rows = [{"meetings_90d": i, "research_reads": 2 * i,
             "events_attended": 0, "tenure_months": 10,
             "wallet_usd_m": 2.0 + 3.0 * i} for i in range(1, 11)]
    result = fit_ols(rows, "wallet_usd_m",
                     features=["meetings_90d"])
    assert math.isclose(result["intercept"], 2.0, abs_tol=1e-6)
    assert math.isclose(result["coefficients"][0], 3.0, abs_tol=1e-6)
    assert math.isclose(result["r2"], 1.0, abs_tol=1e-6)


def test_calibration_bins_cover_all_rows():
    rows = build_access_dataset()
    model = fit_logistic(rows)
    scores = [predict_proba(model, r) for r in rows]
    labels = [1 if r["attended"] else 0 for r in rows]
    bins = calibration(scores, labels, bins=5)
    assert sum(b["n"] for b in bins) == len(rows)
    for b in bins:
        assert 0.0 <= b["mean_predicted"] <= 1.0
        assert 0.0 <= b["observed_rate"] <= 1.0


def test_kaplan_meier_shape():
    rows = build_access_dataset()
    curve = kaplan_meier(rows)
    assert curve[1] <= 1.0
    assert 0.0 < curve[12] < 1.0
    months = sorted(curve)
    values = [curve[m] for m in months]
    assert values == sorted(values, reverse=True)  # non-increasing


def test_kaplan_meier_no_events_stays_at_one():
    rows = [{"months_to_attrition": None} for _ in range(10)]
    curve = kaplan_meier(rows)
    assert all(v == 1.0 for v in curve.values())


def test_attrition_split_shows_engagement_effect():
    rows = build_access_dataset()
    result = attrition_by_engagement(rows)
    assert result["high_attrition_rate"] < result["low_attrition_rate"]
    assert result["p"] < 0.05
    total = sum(sum(r) for r in result["table"])
    assert total == len(rows)


def test_full_eval_passes():
    result = run_access_eval()
    assert result["verdict"] == "PASS"
    assert result["propensity"]["test_auc"] >= 0.65
    assert result["wallet"]["train_r2"] >= 0.2
    assert result["attrition"]["p"] < 0.05
    assert result["n_train"] == 180
    assert result["n_test"] == 60


def test_report_renders():
    text = render_access_report(run_access_eval())
    assert "PASS" in text
    assert "Propensity model" in text
    assert "Wallet model" in text
    assert "Attrition by engagement" in text
