import json
from pathlib import Path

import pandas as pd

from ep_data.cleaning import clean_production
from ep_data.data import generate_dataset
from ep_data.deployment import load_and_predict, package_model, validate
from ep_data.features import FEATURE_COLUMNS, add_features
from ep_data.forecast import backtest


def test_validation_report_passes():
    raw = generate_dataset(n_wells=40, n_months=36, seed=42, with_issues=True)
    clean, log = clean_production(raw)
    feat = add_features(clean)
    report = validate(feat, log)
    assert report["all_checks_pass"] is True
    assert report["backtest"]["beats_baseline"] is True
    assert report["decline_fit_median_r2_log"] > 0.80


def test_packaged_artifact_roundtrip(tmp_path):
    raw = generate_dataset(n_wells=40, n_months=36, seed=42, with_issues=True)
    clean, _ = clean_production(raw)
    feat = add_features(clean)
    bt = backtest(feat)
    artifact = package_model(bt["model"], tmp_path / "model_artifact.json")
    data = json.loads(Path(artifact).read_text())
    assert data["version"] == "1.0.0"
    assert data["features"] == FEATURE_COLUMNS
    row = feat[feat["month_index"] == 30].iloc[0]
    pred = load_and_predict(artifact, [float(row[c]) for c in FEATURE_COLUMNS])
    assert pred >= 0
    # Prediction should be in the same ballpark as the well's recent rate.
    assert 0.3 * row["oil_bbl"] < pred < 3.0 * row["oil_bbl"]
