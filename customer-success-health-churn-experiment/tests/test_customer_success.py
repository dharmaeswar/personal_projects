"""Tests for the customer-success health, churn and experimentation package."""
import math

import pytest

from customer_success import data, health, propensity, experiments, kpis
from customer_success.next_best_action import next_best_actions


@pytest.fixture(scope="module")
def customers():
    return data.generate()


def test_generate_is_deterministic():
    assert data.generate() == data.generate()
    assert len(data.generate()) == 2400


def test_generate_fields_and_ranges(customers):
    c = customers[0]
    assert set(c) >= {"customer_id", "retained", "expanded", "usage_pre", "usage_post"}
    assert 1 <= c["time_to_value_days"] <= 90
    assert 0 <= c["features_adopted"] <= 8
    assert 0.0 <= c["usage_pre"] <= 1.0 and 0.0 <= c["usage_post"] <= 1.0


def test_onboarding_treatment_shortens_time_to_value(customers):
    treat = [c["time_to_value_days"] for c in customers if c["onboard_treat"]]
    control = [c["time_to_value_days"] for c in customers if not c["onboard_treat"]]
    assert sum(treat) / len(treat) < sum(control) / len(control) - 3  # planted -6 days


def test_health_score_bounds_and_bands(customers):
    scored = health.score_all(customers)
    for c in scored:
        assert 0 <= c["health_score"] <= 100
        assert c["health_band"] in ("Healthy", "Watch", "At-Risk")
    assert health.health_band(80) == "Healthy"
    assert health.health_band(60) == "Watch"
    assert health.health_band(30) == "At-Risk"


def test_health_score_orders_retention(customers):
    scored = health.score_all(customers)
    by_band = health.retention_by_band(scored)
    assert by_band["Healthy"] > by_band["At-Risk"]  # score must mean something


def test_churn_model_beats_chance(customers):
    rows, labels = data.features_matrix(customers, "retained")
    labels = [1 - y for y in labels]  # 1 = churned
    tr_rows, tr_y, te_rows, te_y = propensity.train_test_split(rows, labels)
    model = propensity.train_logistic(tr_rows, tr_y)
    result = propensity.evaluate(model, te_rows, te_y)
    assert result["auc"] > 0.70, result
    assert result["log_loss"] < 0.65, result


def test_expansion_model_beats_chance(customers):
    rows, labels = data.features_matrix(customers, "expanded")
    tr_rows, tr_y, te_rows, te_y = propensity.train_test_split(rows, labels)
    model = propensity.train_logistic(tr_rows, tr_y)
    result = propensity.evaluate(model, te_rows, te_y)
    assert result["auc"] > 0.65, result


def test_ab_test_finds_onboarding_effect(customers):
    treat = [c["time_to_value_days"] for c in customers if c["onboard_treat"]]
    control = [c["time_to_value_days"] for c in customers if not c["onboard_treat"]]
    res = experiments.welch_ttest(treat, control)
    assert res["p"] < 0.001
    assert -8 < res["diff"] < -4  # planted -6 days


def test_srm_passes_on_randomized_split(customers):
    n_t = sum(1 for c in customers if c["onboard_treat"])
    res = experiments.srm_chi2(n_t, len(customers) - n_t)
    assert res["p"] > 0.05, res


def test_cuped_reduces_variance(customers):
    treat = [c for c in customers if c["onboard_treat"]]
    raw = [c["usage_post"] for c in treat]
    adj, theta = experiments.cuped_adjust(raw, [c["usage_pre"] for c in treat])
    assert theta > 0.5  # pre-period usage strongly predicts post-period usage
    assert len(adj) == len(raw)


def test_did_recovers_planted_coverage_effect(customers):
    cov = [c for c in customers if c["coverage_treat"]]
    nocov = [c for c in customers if not c["coverage_treat"]]
    did = experiments.difference_in_differences(
        [c["usage_pre"] for c in cov], [c["usage_post"] for c in cov],
        [c["usage_pre"] for c in nocov], [c["usage_post"] for c in nocov])
    assert 0.04 < did < 0.12, did  # planted +0.08


def test_synthetic_control_weights_and_effect(customers):
    series = data.weekly_series(customers)
    sc = experiments.synthetic_control(
        series["treated_pre"], series["donors_pre"],
        series["treated_post"], series["donors_post"])
    assert abs(sum(sc["weights"]) - 1.0) < 0.01
    assert all(w >= 0 for w in sc["weights"])
    assert sc["pre_rmse"] < 0.05
    assert 0.04 < sc["effect"] < 0.12, sc  # planted +0.08


def test_next_best_action_ranking(customers):
    scored = health.score_all(customers)
    at_risk = next(c for c in scored if c["health_band"] == "At-Risk")
    actions = next_best_actions(at_risk, 0.8, 0.1)
    assert actions[0][0] == "save_offer"
    healthy = next(c for c in scored if c["health_band"] == "Healthy")
    top = next_best_actions(healthy, 0.1, 0.8)[0][0]
    assert top in ("expansion_consult", "self_serve_nudge", "training_session")


def test_kpis_in_sane_ranges(customers):
    out = kpis.compute_kpis(customers)
    assert 10 < out["time_to_value_days"] < 40
    assert 0.3 < out["adoption_rate"] < 0.9
    assert 0.5 < out["retention_rate"] < 0.95
    assert out["n"] == 2400


def test_mde_shrinks_with_sample_size():
    assert experiments.mde(10.0, 100) > experiments.mde(10.0, 1000)
