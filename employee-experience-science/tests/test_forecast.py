"""Tests for the workforce-planning forecasting module."""

from experience_science.data import generate
from experience_science.forecast import (
    attrition_model,
    backtest,
    forecast_counts,
    monthly_history,
    workforce_plan,
)


def test_attrition_model_beats_base_rate():
    rows = generate()
    m = attrition_model(rows)
    assert m["n_train"] == 960
    assert m["n_test"] == 240
    # Ranked risk must separate leavers from stayers better than chance.
    assert m["auc"] > 0.60
    # Calibrated probabilities must beat always predicting the base rate.
    assert m["brier"] < m["base_brier"]


def test_attrition_model_recovers_planted_drivers():
    rows = generate()
    m = attrition_model(rows)
    coefs = m["coefficients"]
    # Planted effects that survive in the fitted model: overtime raises
    # attrition risk, a higher experience score lowers it, night shift
    # raises it, and longer manager tenure lowers it. Schedule churn's
    # effect is mediated through the experience score (it lowers the
    # score, and low scores drive attrition), so its direct coefficient
    # is near zero — that mediation is documented, not hidden.
    assert coefs["overtime_hours_week"] > 0
    assert coefs["experience_score"] < 0
    assert coefs["night_shift"] > 0
    assert coefs["manager_tenure_years"] < 0


def test_attrition_model_calibration_is_sane():
    rows = generate()
    m = attrition_model(rows)
    gaps = [abs(b["mean_predicted"] - b["observed_rate"])
            for b in m["calibration"]]
    # Mean absolute calibration error stays small; the known limit is
    # the top quintile, where the linear logit under-predicts the
    # threshold-driven tail (predicted ~0.21 vs observed ~0.38).
    assert sum(gaps) / len(gaps) < 0.10
    # Predicted risk must rise across the bins.
    preds = [b["mean_predicted"] for b in m["calibration"]]
    assert preds == sorted(preds)


def test_monthly_history_shape():
    rows = generate()
    history = monthly_history(rows)
    orgs = {r["org"] for r in rows}
    assert len(history) == 12 * len(orgs)
    for h in history:
        assert 1 <= h["month"] <= 12
        assert h["headcount"] > 0
        assert 0 <= h["attritions"] <= h["headcount"]
    # Reproducible with the same seed.
    assert history == monthly_history(rows)


def test_forecast_counts_shape():
    rows = generate()
    fc = forecast_counts(monthly_history(rows), horizon=3)
    assert len(fc) == 3
    assert [f["month"] for f in fc] == [13, 14, 15]
    for f in fc:
        assert f["lo"] <= f["forecast"] <= f["hi"]
        assert f["lo"] >= 0


def test_backtest_scores_are_bounded():
    rows = generate()
    bt = backtest(monthly_history(rows))
    assert 0.0 <= bt["mape"] <= 1.0
    assert 0.0 <= bt["coverage"] <= 1.0
    assert len(bt["detail"]) == 3
    # The trend forecast must track the held-out months reasonably.
    assert bt["mape"] < 0.50
    assert bt["coverage"] >= 1 / 3


def test_workforce_plan_runs_end_to_end():
    rows = generate()
    plan = workforce_plan(rows)
    assert plan["months"] == 12
    assert plan["total_attritions_12m"] > 0
    assert len(plan["forecast_next_3m"]) == 3
    assert plan["attrition_model"]["auc"] > 0.60
