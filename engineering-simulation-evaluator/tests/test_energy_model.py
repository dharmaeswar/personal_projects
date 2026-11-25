import numpy as np
import pandas as pd
import pytest

from eng_sim_evaluator.deployment import (
    deployment_checklist,
    export_model_artifact,
    predict_from_artifact,
    rebuild_ols_from_artifact,
)
from eng_sim_evaluator.energy_data import (
    DATA_DICTIONARY,
    DICTIONARY_VERSION,
    analytic_rop,
    clean_and_validate,
    eda_summary,
    generate_drilling_data,
    load_data_dictionary,
)
from eng_sim_evaluator.energy_model import (
    FEATURES,
    OlsModel,
    build_features,
    fit_random_forest,
    model_card,
    sensitivity_analysis,
    train_holdout_split,
    validate_models,
)


@pytest.fixture(scope="module")
def cleaned():
    raw = generate_drilling_data(n_rows=400, seed=7)
    frame, _ = clean_and_validate(raw)
    return frame


def test_generation_is_seeded_and_shaped():
    a = generate_drilling_data(n_rows=400, seed=7)
    b = generate_drilling_data(n_rows=400, seed=7)
    pd.testing.assert_frame_equal(a, b)
    assert len(a) == 404  # 400 rows + 4 injected duplicates
    for col in DATA_DICTIONARY:
        assert col in a.columns


def test_data_dictionary_covers_every_column():
    dictionary = load_data_dictionary()
    assert dictionary["version"] == DICTIONARY_VERSION
    for col in DATA_DICTIONARY:
        entry = dictionary["fields"][col]
        assert entry["meaning"] and entry["unit"]
        assert "valid_range" in entry or "valid_values" in entry
    for name in ("specific_energy", "wob_per_depth"):
        assert name in dictionary["features_engineered"]


def test_cleaning_removes_injected_problems():
    raw = generate_drilling_data(n_rows=400, seed=7)
    cleaned, report = clean_and_validate(raw)
    assert report["rows_in"] == 404
    assert report["rows_dropped_total"] > 0
    assert report["duplicate_rows"] == 4
    assert cleaned.isna().sum().sum() == 0
    assert cleaned.duplicated().sum() == 0
    for field, (lo, hi) in {
        f: e["valid_range"]
        for f, e in DATA_DICTIONARY.items() if "valid_range" in e
    }.items():
        assert cleaned[field].between(lo, hi).all()


def test_analytic_rop_rises_with_wob_and_rpm():
    base = analytic_rop(20.0, 100.0, 500.0, 5000.0)
    assert analytic_rop(30.0, 100.0, 500.0, 5000.0) > base
    assert analytic_rop(20.0, 150.0, 500.0, 5000.0) > base
    assert analytic_rop(20.0, 100.0, 500.0, 11000.0) < base
    with pytest.raises(ValueError):
        analytic_rop(0.0, 100.0, 500.0, 5000.0)


def test_features_are_computed_and_clean(cleaned):
    featured = build_features(cleaned)
    for col in FEATURES:
        assert col in featured.columns
    assert featured[FEATURES].isna().sum().sum() == 0
    assert (featured["specific_energy"] > 0).all()
    assert (featured["flow_per_rpm"] > 0).all()


def test_eda_flags_anomalies_and_reports_stats(cleaned):
    summary = eda_summary(cleaned)
    assert summary["rows"] == len(cleaned)
    assert summary["fields"]["rop_ft_hr"]["mean"] > 0
    assert summary["fields"]["rop_ft_hr"]["missing"] == 0
    assert isinstance(summary["anomalies_flagged"], list)


def test_ols_beats_naive_baseline(cleaned):
    validation = validate_models(cleaned, seed=7)
    assert validation["ols"]["mae"] < validation["naive_mean_baseline"]["mae"]
    assert validation["ols"]["r2"] > 0.5
    assert validation["n_train"] + validation["n_holdout"] == len(cleaned)


def test_random_forest_challenger_fits(cleaned):
    featured = build_features(cleaned)
    train, holdout = train_holdout_split(featured, seed=7)
    model = fit_random_forest(train[FEATURES].to_numpy(dtype=float),
                              train["rop_ft_hr"].to_numpy(dtype=float))
    pred = model.predict(holdout[FEATURES].to_numpy(dtype=float))
    assert len(pred) == len(holdout)
    assert np.isfinite(pred).all()
    mae = float(np.mean(np.abs(pred - holdout["rop_ft_hr"].to_numpy())))
    naive = float(np.mean(np.abs(
        holdout["rop_ft_hr"].to_numpy() - train["rop_ft_hr"].mean())))
    assert mae < naive


def test_ols_tracks_analytic_truth(cleaned):
    validation = validate_models(cleaned, seed=7)
    # The OLS model should stay close to the analytic ground truth on
    # holdout — well inside the noise the data carries.
    assert validation["ols_vs_analytic_truth"]["mae"] < 5.0
    assert validation["ols_vs_analytic_truth"]["mae"] < \
        validation["analytic_truth_vs_observed"]["mae"] + 5.0


def test_artifact_round_trip_matches_model(cleaned):
    featured = build_features(cleaned)
    train, holdout = train_holdout_split(featured, seed=7)
    ols = OlsModel().fit(train[FEATURES].to_numpy(dtype=float),
                         train["rop_ft_hr"].to_numpy(dtype=float))
    validation = validate_models(cleaned, seed=7)
    artifact = export_model_artifact(ols, validation, DICTIONARY_VERSION)
    rebuilt = rebuild_ols_from_artifact(artifact)
    direct = ols.predict(holdout[FEATURES].to_numpy(dtype=float))
    via_artifact = np.array([
        predict_from_artifact(artifact, row.to_dict())
        for _, row in holdout.iterrows()
    ])
    via_rebuilt = rebuilt.predict(holdout[FEATURES].to_numpy(dtype=float))
    assert np.max(np.abs(direct - via_rebuilt)) < 1e-9
    # Artifact predictions are clipped the same way as the model path.
    assert np.max(np.abs(np.clip(direct, 0.5, 120.0) - via_artifact)) < 1e-9
    assert artifact["data_dictionary_version"] == DICTIONARY_VERSION


def test_sensitivity_names_every_feature(cleaned):
    featured = build_features(cleaned)
    train, _ = train_holdout_split(featured, seed=7)
    ols = OlsModel().fit(train[FEATURES].to_numpy(dtype=float),
                         train["rop_ft_hr"].to_numpy(dtype=float))
    rows = sensitivity_analysis(ols, train[FEATURES].to_numpy(dtype=float))
    assert [r["feature"] for r in rows] == FEATURES
    assert all(np.isfinite(r["mean_predicted_change_ft_hr"]) for r in rows)
    # Weight on bit and rotary speed should move ROP up when bumped.
    by_name = {r["feature"]: r["mean_predicted_change_ft_hr"] for r in rows}
    assert by_name["wob_klbf"] > 0
    assert by_name["rpm"] > 0


def test_deployment_checklist_has_gates():
    steps = deployment_checklist()
    assert len(steps) >= 5
    assert [s["step"] for s in steps] == list(range(1, len(steps) + 1))
    assert all(s["action"] and s["gate"] for s in steps)
    text = " ".join(s["action"] for s in steps)
    assert "Shadow" in text and "monitor" in text.lower()


def test_model_card_states_limits(cleaned):
    validation = validate_models(cleaned, seed=7)
    _, report = clean_and_validate(generate_drilling_data(n_rows=400, seed=7))
    card = model_card(validation, report, DICTIONARY_VERSION)
    assert card["data_dictionary_version"] == DICTIONARY_VERSION
    assert card["holdout_metrics_ols"]["mae"] == validation["ols"]["mae"]
    assert any("Synthetic" in item for item in card["limitations"])
    assert any("unseen" in item for item in card["limitations"])
